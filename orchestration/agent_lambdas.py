"""
Adapta cada agente para a interface LambdaHandler.

LambdaHandler = Callable[[MCPContext], MCPResponse]

Cada função aqui é um handler isolado — equivale a uma função AWS Lambda.
Lê seus inputs do MCPContext e escreve seu output em MCPResponse.

Contexto MCP acumulado entre lambdas pelo StepFunctionsRuntime:
  - ctx.input             -> dados iniciais: cloud_providers, cultura_text, llm_provider
  - ctx.context["planner"]        -> output do PlannerAgent
  - ctx.context["finops"]         -> output do FinOpsAgent
  - ctx.context["data_governance"]-> output do DataGovernanceAgent
  - ctx.context["cultura"]        -> output do CulturaAgent

Nota sobre providers na payload:
  Em AWS Lambda real, os providers seriam referências a serviços externos
  (ex: ARN do bucket S3, endpoint de API). Localmente, passamos as instâncias
  Python diretamente via MCPContext — o contrato de interface é o mesmo.
"""

from __future__ import annotations

from mcp.context import MCPContext, MCPResponse
from logger import get_logger

log = get_logger("agent_lambdas")


# Lambda — Planner


def lambda_planner(ctx: MCPContext) -> MCPResponse:
    """
    Analisa os dados disponíveis e decide quais agentes executar.
    Input:  ctx.input -> { cloud_providers, cultura_text }
    Output: MCPResponse.output -> ExecutionPlan.to_dict()
    """
    from agents.planner_agent import PlannerAgent

    cloud_providers = ctx.input.get("cloud_providers", [])
    cultura_text = ctx.input.get("cultura_text", "")

    log.info("lambda_planner_start", execution_id=ctx.execution_id)

    try:
        agent = PlannerAgent()
        plan = agent.run(cloud_providers=cloud_providers, cultura_text=cultura_text)
        output = plan.to_dict()

        log.info(
            "lambda_planner_done",
            active_agents=plan.active_agents,
            priority=plan.priority,
            execution_id=ctx.execution_id,
        )
        return MCPResponse(
            agent="planner",
            status="success",
            output=output,
            execution_id=ctx.execution_id,
        )

    except Exception as exc:
        log.error("lambda_planner_error", error=str(exc), execution_id=ctx.execution_id)
        return MCPResponse(
            agent="planner",
            status="error",
            output={"active_agents": ["finops", "data_governance", "cultura"]},
            error=str(exc),
            execution_id=ctx.execution_id,
        )


# Lambda — FinOps


def lambda_finops(ctx: MCPContext) -> MCPResponse:
    """
    Processa custos e ociosidade de recursos multi-cloud.
    Input:  ctx.input -> { cloud_providers }
    Output: MCPResponse.output -> FinOpsReport.to_dict()
    """
    from agents.finops_agent import FinOpsAgent

    cloud_providers = ctx.input.get("cloud_providers", [])
    log.info("lambda_finops_start", execution_id=ctx.execution_id)

    try:
        agent = FinOpsAgent(providers=cloud_providers)
        report = agent.run()

        log.info(
            "lambda_finops_done",
            total_cost=report.total_cost,
            idle_count=len(report.idle_resources),
            execution_id=ctx.execution_id,
        )
        return MCPResponse(
            agent="finops",
            status="success",
            output=report.to_dict(),
            execution_id=ctx.execution_id,
        )

    except Exception as exc:
        log.error("lambda_finops_error", error=str(exc), execution_id=ctx.execution_id)
        return MCPResponse(
            agent="finops",
            status="error",
            output={"error": str(exc)},
            error=str(exc),
            execution_id=ctx.execution_id,
        )


# Lambda — Data Governance


def lambda_data_governance(ctx: MCPContext) -> MCPResponse:
    """
    Classifica riscos LGPD nos recursos cloud.
    Input:  ctx.input -> { cloud_providers }
    Output: MCPResponse.output -> DataGovernanceReport.to_dict()
    """
    from agents.data_governance_agent import DataGovernanceAgent

    cloud_providers = ctx.input.get("cloud_providers", [])
    log.info("lambda_data_governance_start", execution_id=ctx.execution_id)

    try:
        agent = DataGovernanceAgent(providers=cloud_providers)
        report = agent.run()

        log.info(
            "lambda_data_governance_done",
            compliance_score=report.compliance_score,
            critical=report.risk_summary.get("critical", 0),
            execution_id=ctx.execution_id,
        )
        return MCPResponse(
            agent="data_governance",
            status="success",
            output=report.to_dict(),
            execution_id=ctx.execution_id,
        )

    except Exception as exc:
        log.error(
            "lambda_data_governance_error",
            error=str(exc),
            execution_id=ctx.execution_id,
        )
        return MCPResponse(
            agent="data_governance",
            status="error",
            output={"error": str(exc)},
            error=str(exc),
            execution_id=ctx.execution_id,
        )


# Lambda — Cultura


def lambda_cultura(ctx: MCPContext) -> MCPResponse:
    """
    Analisa cultura organizacional via RAG + LLM narrativa.
    Input:  ctx.input -> { cultura_text, llm_provider }
    Output: MCPResponse.output -> CulturaReport.to_dict()
    """
    from agents.cultura_agent import CulturaAgent

    cultura_text = ctx.input.get("cultura_text", "")
    llm_provider = ctx.input.get("llm_provider")
    log.info("lambda_cultura_start", execution_id=ctx.execution_id)

    try:
        agent = CulturaAgent(cultura_text=cultura_text, llm_provider=llm_provider)
        report = agent.run()

        log.info(
            "lambda_cultura_done",
            culture_type=report.culture_type,
            maturity_score=report.maturity_score,
            execution_id=ctx.execution_id,
        )
        return MCPResponse(
            agent="cultura",
            status="success",
            output=report.to_dict(),
            execution_id=ctx.execution_id,
        )

    except Exception as exc:
        log.error("lambda_cultura_error", error=str(exc), execution_id=ctx.execution_id)
        return MCPResponse(
            agent="cultura",
            status="error",
            output={
                "culture_type": "Análise indisponível",
                "maturity_score": 0,
                "digital_readiness": "desconhecida",
                "traits": [],
                "bottlenecks": [],
                "strengths": [],
                "error": str(exc)[:200],
            },
            error=str(exc),
            execution_id=ctx.execution_id,
        )


# Lambda — Analyzer


def lambda_analyzer(ctx: MCPContext) -> MCPResponse:
    """
    Correlaciona outputs de todos os agentes e gera insights via LLM.
    Input:  ctx.context -> { finops, data_governance, cultura } (acumulados pelo SF runtime)
            ctx.input   -> { llm_provider }
    Output: MCPResponse.output -> AnalyzerReport.to_dict()
    """
    from agents.analyzer_agent import AnalyzerAgent

    finops_data = ctx.context.get("finops")
    governance_data = ctx.context.get("data_governance")
    cultura_data = ctx.context.get("cultura")
    llm_provider = ctx.input.get("llm_provider")

    log.info(
        "lambda_analyzer_start",
        has_finops=finops_data is not None,
        has_governance=governance_data is not None,
        has_cultura=cultura_data is not None,
        execution_id=ctx.execution_id,
    )

    try:
        agent = AnalyzerAgent(llm_provider=llm_provider)
        report = agent.run(
            finops_data=finops_data,
            governance_data=governance_data,
            cultura_data=cultura_data,
        )

        log.info(
            "lambda_analyzer_done",
            risk_score=round(report.overall_risk_score, 1),
            correlations=len(report.correlated_issues),
            execution_id=ctx.execution_id,
        )
        return MCPResponse(
            agent="analyzer",
            status="success",
            output=report.to_dict(),
            execution_id=ctx.execution_id,
        )

    except Exception as exc:
        log.error(
            "lambda_analyzer_error", error=str(exc), execution_id=ctx.execution_id
        )
        return MCPResponse(
            agent="analyzer",
            status="error",
            output={"error": str(exc)},
            error=str(exc),
            execution_id=ctx.execution_id,
        )
