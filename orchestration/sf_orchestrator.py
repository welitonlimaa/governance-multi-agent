"""
Pipeline completo no modo Step Functions local.

Este módulo monta e executa o fluxo usando LambdaRuntime + StepFunctionsRuntime,
retornando o mesmo dict de estado que o LangGraph produziria — garantindo que
main.py, report_writer e o restante do sistema não precisam saber qual
orquestrador está ativo.
"""

from __future__ import annotations

import asyncio
from typing import Any
from uuid import uuid4

from config import FAILURE_RATE
from logger import get_logger
from mcp.context import MCPContext
from orchestration.lambda_sim import LambdaRuntime
from orchestration.step_functions import StepFunctionsRuntime
from orchestration.agent_lambdas import (
    lambda_planner,
    lambda_finops,
    lambda_data_governance,
    lambda_cultura,
    lambda_analyzer,
)

log = get_logger("sf_orchestrator")

# Definição do fluxo
#
# Cada dict representa um State:
#   name       -> identificador do state
#   functions  -> lambdas elegíveis para execução neste state
#   parallel   -> True = Parallel State | False = Task State sequencial
#   filter_by  -> Choice State implícito: filtra `functions` com base no
#                output de um state anterior antes de executar
#
FLOW_DEFINITION: list[dict[str, Any]] = [
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
            "step": "planner",
            "key": "active_agents",
        },
    },
    {
        "name": "analyzer",
        "functions": ["analyzer"],
        "parallel": False,
    },
]


def _build_runtimes() -> dict[str, LambdaRuntime]:
    """
    Instancia um LambdaRuntime para cada handler.
    Cada runtime carrega configurações independentes de retry/timeout —
    replicando o comportamento de funções Lambda distintas na AWS.
    """
    configs: dict[str, dict[str, Any]] = {
        "planner": {"max_retries": 1, "timeout_seconds": 15.0},
        "finops": {"max_retries": 2, "timeout_seconds": 30.0},
        "data_governance": {"max_retries": 2, "timeout_seconds": 30.0},
        "cultura": {"max_retries": 1, "timeout_seconds": 60.0},  # RAG é mais lento
        "analyzer": {"max_retries": 1, "timeout_seconds": 45.0},
    }
    handlers = {
        "planner": lambda_planner,
        "finops": lambda_finops,
        "data_governance": lambda_data_governance,
        "cultura": lambda_cultura,
        "analyzer": lambda_analyzer,
    }
    return {
        name: LambdaRuntime(
            handler=handler,
            function_name=name,
            max_retries=configs[name]["max_retries"],
            timeout_seconds=configs[name]["timeout_seconds"],
        )
        for name, handler in handlers.items()
    }


def _build_initial_ctx(
    cloud_providers: list,
    cultura_text: str,
    llm_provider: Any,
    execution_id: str,
) -> MCPContext:
    """
    Constrói o MCPContext inicial.

    Em AWS Lambda real, `cloud_providers` e `llm_provider` seriam referências
    a serviços externos (ARNs, endpoints). Localmente, passamos as instâncias
    Python diretamente — o contrato de interface MCPContext é idêntico.
    """
    return MCPContext(
        input={
            "cloud_providers": cloud_providers,
            "cultura_text": cultura_text,
            "llm_provider": llm_provider,
        },
        context={},
        memory={},
        execution_id=execution_id,
    )


def _step_results_to_state(
    step_results: list,
    execution_id: str,
    errors: list[str],
) -> dict[str, Any]:
    """
    Converte os StepResults do runtime em um dict de estado compatível
    com o formato produzido pelo LangGraph.

    O report_writer e o print_summary esperam chaves fixas:
      execution_plan, finops_result, governance_result,
      cultura_result, analyzer_result

    O StepFunctionsRuntime nomeia as respostas pelo nome do agente
    (planner, finops, data_governance, cultura, analyzer).
    Este mapeamento garante que o restante do sistema funcione
    sem alteração independente do orquestrador ativo.
    """
    # Mapeamento: nome do agente lambda -> chave esperada pelo report_writer
    KEY_MAP: dict[str, str] = {
        "planner": "execution_plan",
        "finops": "finops_result",
        "data_governance": "governance_result",
        "cultura": "cultura_result",
        "analyzer": "analyzer_result",
    }

    state: dict[str, Any] = {
        "execution_id": execution_id,
        "errors": errors,
        "orchestrator": "step_functions",
    }

    for step in step_results:
        for response in step.responses:
            target_key = KEY_MAP.get(response.agent, response.agent)
            state[target_key] = response.output
            if response.status == "error" and response.error:
                errors.append(f"{response.agent}: {response.error}")

        if step.skipped:
            state.setdefault("skipped_agents", []).extend(step.skipped)

    return state


async def _run_async(
    cloud_providers: list,
    cultura_text: str,
    llm_provider: Any,
    execution_id: str,
) -> dict[str, Any]:
    """Execução assíncrona interna."""
    errors: list[str] = []
    ctx = _build_initial_ctx(cloud_providers, cultura_text, llm_provider, execution_id)

    runtimes = _build_runtimes()
    runtime = StepFunctionsRuntime(
        flow_definition=FLOW_DEFINITION,
        runtimes=runtimes,
    )

    log.info(
        "sf_execution_start",
        execution_id=execution_id,
        steps=[s["name"] for s in FLOW_DEFINITION],
        failure_rate=FAILURE_RATE,
    )

    step_results = await runtime.execute(ctx)

    log.info(
        "sf_execution_complete",
        execution_id=execution_id,
        steps_completed=len(step_results),
        all_success=all(sr.all_success() for sr in step_results),
    )

    return _step_results_to_state(step_results, execution_id, errors)


def run(
    cloud_providers: list,
    cultura_text: str,
    llm_provider: Any,
    execution_id: str | None = None,
) -> dict[str, Any]:
    """
    Ponto de entrada síncrono do orquestrador Step Functions.
    Compatível com a assinatura de graph.invoke() do LangGraph.
    """
    eid = execution_id or str(uuid4())[:8]
    return asyncio.run(_run_async(cloud_providers, cultura_text, llm_provider, eid))
