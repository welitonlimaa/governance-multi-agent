"""
orchestration/step_functions.py
Simula AWS Step Functions localmente:
  - Execução sequencial
  - Execução paralela (asyncio.gather)
  - Definição de fluxo via dicionário (similar à ASL)
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
    """Resultado de uma step de execução."""

    step_name: str
    responses: list[MCPResponse] = field(default_factory=list)
    parallel: bool = False

    def all_success(self) -> bool:
        return all(r.status == "success" for r in self.responses)


class StepFunctionsRuntime:
    """
    Orquestra steps sequencialmente.
    Cada step pode conter múltiplos lambdas (executados em paralelo).

    Definição de fluxo:
    [
        {"name": "planner",   "functions": ["planner_fn"],                  "parallel": False},
        {"name": "executors", "functions": ["finops_fn","data_fn","cult_fn"], "parallel": True},
        {"name": "analyzer",  "functions": ["analyzer_fn"],                 "parallel": False},
    ]
    """

    def __init__(
        self,
        flow_definition: list[dict[str, Any]],
        runtimes: dict[str, LambdaRuntime],
    ) -> None:
        self.flow_definition = flow_definition
        self.runtimes = runtimes

    async def execute(self, ctx: MCPContext) -> list[StepResult]:
        """Executa o fluxo completo e retorna resultados por step."""
        execution_results: list[StepResult] = []
        accumulated_ctx = ctx

        for step_def in self.flow_definition:
            step_name: str = step_def["name"]
            function_names: list[str] = step_def["functions"]
            parallel: bool = step_def.get("parallel", False)

            log.info(
                "step_start",
                step=step_name,
                functions=function_names,
                parallel=parallel,
                execution_id=ctx.execution_id,
            )

            runtimes = [
                self.runtimes[fn]
                for fn in function_names
                if fn in self.runtimes
            ]

            if parallel:
                responses = await asyncio.gather(
                    *[rt.invoke(accumulated_ctx) for rt in runtimes]
                )
                responses = list(responses)
            else:
                responses = []
                for rt in runtimes:
                    resp = await rt.invoke(accumulated_ctx)
                    responses.append(resp)

            step_result = StepResult(
                step_name=step_name,
                responses=responses,
                parallel=parallel,
            )
            execution_results.append(step_result)

            # Enriquece contexto com outputs para próxima step
            for resp in responses:
                accumulated_ctx = accumulated_ctx.enrich(
                    **{resp.agent: resp.output}
                )

            log.info(
                "step_complete",
                step=step_name,
                success=step_result.all_success(),
                execution_id=ctx.execution_id,
            )

        return execution_results
