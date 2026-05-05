"""
Simula AWS Step Functions localmente.

Funcionalidades:
  - Execução sequencial de steps
  - Execução paralela dentro de um step (asyncio.gather)
  - Routing condicional via `filter_by`:
      quando definido, o runtime lê o output de um step anterior
      para decidir quais funções do step atual executar de fato.
      Isso replica o comportamento de Choice States no ASL real.
  - Retry via LambdaRuntime (configurado por função)
  - Contexto MCP acumulado entre steps

Definição de fluxo (equivalente ao ASL — Amazon States Language):

    [
        {
            "name": "planner",
            "functions": ["planner"],
            "parallel": False,
        },
        {
            "name": "executors",
            "functions": ["finops", "data_governance", "cultura"],
            "parallel": True,
            "filter_by": {
                "step":  "planner",          # nome do step que produziu o plano
                "key":   "active_agents",    # chave dentro do output desse step
            }
        },
        {
            "name": "analyzer",
            "functions": ["analyzer"],
            "parallel": False,
        },
    ]
"""

from __future__ import annotations

import asyncio
from dataclasses import dataclass, field
from typing import Any

from logger import get_logger
from mcp.context import MCPContext, MCPResponse
from orchestration.lambda_sim import LambdaRuntime

log = get_logger("step_functions")


@dataclass
class StepResult:
    """Resultado de um step de execução."""

    step_name: str
    responses: list[MCPResponse] = field(default_factory=list)
    parallel: bool = False
    skipped: list[str] = field(default_factory=list)

    def all_success(self) -> bool:
        return all(r.status == "success" for r in self.responses)

    def to_dict(self) -> dict[str, Any]:
        return {
            "step_name": self.step_name,
            "parallel": self.parallel,
            "skipped": self.skipped,
            "responses": [r.to_dict() for r in self.responses],
            "all_success": self.all_success(),
        }


class StepFunctionsRuntime:
    """
    Orquestra steps sequencialmente seguindo a definição de fluxo.

    Cada step pode:
      - ter múltiplas funções executadas em sequência ou em paralelo
      - filtrar funções dinamicamente com base no output de um step anterior
        (equivalente a Choice State no ASL real)
    """

    def __init__(
        self,
        flow_definition: list[dict[str, Any]],
        runtimes: dict[str, LambdaRuntime],
    ) -> None:
        self.flow_definition = flow_definition
        self.runtimes = runtimes

        # Acumula outputs de cada step para permitir `filter_by`
        self._step_outputs: dict[str, dict[str, Any]] = {}

    async def execute(self, ctx: MCPContext) -> list[StepResult]:
        """
        Executa o fluxo completo e retorna os resultados por step.
        O MCPContext é acumulado entre steps — cada step enxerga os outputs anteriores.
        """
        execution_results: list[StepResult] = []
        accumulated_ctx = ctx

        for step_def in self.flow_definition:
            step_name: str = step_def["name"]
            all_functions: list[str] = step_def["functions"]
            parallel: bool = step_def.get("parallel", False)
            filter_by: dict | None = step_def.get("filter_by")

            # Routing condicional
            # Se `filter_by` está definido, restringe as funções a executar
            # com base no output de um step anterior (ex: plano do Planner).
            active_functions = self._resolve_functions(
                all_functions, filter_by, accumulated_ctx
            )
            skipped = [f for f in all_functions if f not in active_functions]

            log.info(
                "step_start",
                step=step_name,
                functions=active_functions,
                skipped=skipped,
                parallel=parallel,
                execution_id=ctx.execution_id,
            )

            runtimes_to_run = [
                self.runtimes[fn] for fn in active_functions if fn in self.runtimes
            ]

            if not runtimes_to_run:
                log.warning("step_no_functions", step=step_name)
                execution_results.append(
                    StepResult(
                        step_name=step_name,
                        responses=[],
                        parallel=parallel,
                        skipped=skipped,
                    )
                )
                continue

            if parallel:
                responses = list(
                    await asyncio.gather(
                        *[rt.invoke(accumulated_ctx) for rt in runtimes_to_run]
                    )
                )
            else:
                responses = []
                for rt in runtimes_to_run:
                    resp = await rt.invoke(accumulated_ctx)
                    responses.append(resp)

            step_result = StepResult(
                step_name=step_name,
                responses=responses,
                parallel=parallel,
                skipped=skipped,
            )
            execution_results.append(step_result)

            # Acumular outputs no contexto MCP
            # Cada response enriquece o contexto para o próximo step.
            # Também salva o output agregado do step para uso em `filter_by`.
            step_output_agg: dict[str, Any] = {}
            for resp in responses:
                accumulated_ctx = accumulated_ctx.enrich(**{resp.agent: resp.output})
                step_output_agg[resp.agent] = resp.output

            self._step_outputs[step_name] = step_output_agg

            log.info(
                "step_complete",
                step=step_name,
                success=step_result.all_success(),
                skipped=skipped,
                execution_id=ctx.execution_id,
            )

        return execution_results

    def _resolve_functions(
        self,
        all_functions: list[str],
        filter_by: dict | None,
        ctx: MCPContext,
    ) -> list[str]:
        """
        Determina quais funções do step devem ser executadas.

        Se `filter_by` não está definido -> executa todas.
        Se está definido -> lê o output do step referenciado e filtra.

        filter_by schema:
            {
                "step": "<nome do step anterior>",
                "key":  "<chave dentro do output desse step>"
            }

        Exemplo:
            filter_by = {"step": "planner", "key": "active_agents"}
            -> lê ctx.context["planner"]["active_agents"] -> ["finops", "cultura"]
            -> executa apenas finops e cultura, pula data_governance
        """
        if not filter_by:
            return all_functions

        ref_step = filter_by.get("step", "")
        ref_key = filter_by.get("key", "")

        step_data = ctx.context.get(ref_step, {})

        if isinstance(step_data, dict) and ref_step in step_data:
            step_data = step_data[ref_step]

        allowed: list[str] | None = (
            step_data.get(ref_key) if isinstance(step_data, dict) else None
        )

        if not allowed:
            log.warning(
                "filter_by_resolution_failed",
                ref_step=ref_step,
                ref_key=ref_key,
                fallback="executing_all",
            )
            return all_functions

        filtered = [fn for fn in all_functions if fn in allowed]
        log.info(
            "filter_by_applied",
            allowed=allowed,
            resolved=filtered,
            step=ref_step,
        )
        return filtered
