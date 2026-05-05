"""
Orquestração do fluxo multi-agent via LangGraph.

Fluxo definido:
  planner ──► [finops || data_governance || cultura] ──► analyzer

O paralelismo dos executors é gerenciado pelo LangGraph
através de Send() para nós concorrentes.
"""

from __future__ import annotations

from typing import Any, TypedDict

from langgraph.graph import END, StateGraph
from langgraph.constants import Send

from agents.planner_agent import PlannerAgent, ExecutionPlan
from agents.finops_agent import FinOpsAgent
from agents.data_governance_agent import DataGovernanceAgent
from agents.cultura_agent import CulturaAgent
from agents.analyzer_agent import AnalyzerAgent
from providers.cloud.base import CloudProvider
from logger import get_logger

log = get_logger("graph")


class GraphState(TypedDict, total=False):
    cloud_providers: list[CloudProvider]
    cultura_text: str
    llm_provider: Any

    execution_plan: dict[str, Any]

    finops_result: dict[str, Any]
    governance_result: dict[str, Any]
    cultura_result: dict[str, Any]

    analyzer_result: dict[str, Any]

    execution_id: str
    errors: list[str]


def node_planner(state: GraphState) -> dict[str, Any]:
    """Decide quais agentes serão executados."""
    log.info("node_planner_start")
    planner = PlannerAgent()
    plan: ExecutionPlan = planner.run(
        cloud_providers=state["cloud_providers"],
        cultura_text=state.get("cultura_text", ""),
    )
    log.info("node_planner_done", active_agents=plan.active_agents)
    return {"execution_plan": plan.to_dict()}


def node_finops(state: GraphState) -> dict[str, Any]:
    """Executa FinOps Agent — lógica Python pura."""
    log.info("node_finops_start")
    try:
        agent = FinOpsAgent(providers=state["cloud_providers"])
        report = agent.run()
        log.info("node_finops_done", total_cost=report.total_cost)
        return {"finops_result": report.to_dict()}
    except Exception as exc:
        log.error("node_finops_error", error=str(exc))
        return {"finops_result": {"error": str(exc)}, "errors": [f"finops: {exc}"]}


def node_data_governance(state: GraphState) -> dict[str, Any]:
    """Executa Data Governance Agent — lógica Python pura."""
    log.info("node_data_governance_start")
    try:
        agent = DataGovernanceAgent(providers=state["cloud_providers"])
        report = agent.run()
        log.info("node_data_governance_done", compliance_score=report.compliance_score)
        return {"governance_result": report.to_dict()}
    except Exception as exc:
        log.error("node_data_governance_error", error=str(exc))
        return {
            "governance_result": {"error": str(exc)},
            "errors": [f"data_governance: {exc}"],
        }


def node_cultura(state: GraphState) -> dict[str, Any]:
    """Executa Cultura Agent — RAG + LLM opcional para narrativa."""
    log.info("node_cultura_start")
    try:
        agent = CulturaAgent(
            cultura_text=state.get("cultura_text", ""),
            llm_provider=state.get("llm_provider"),
        )
        report = agent.run()
        log.info("node_cultura_done", culture_type=report.culture_type)
        return {"cultura_result": report.to_dict()}
    except Exception as exc:
        log.error("node_cultura_error", error=str(exc))
        # Retorna resultado parcial — não interrompe o Analyzer
        return {
            "cultura_result": {
                "culture_type": "Análise indisponível",
                "maturity_score": 0,
                "digital_readiness": "desconhecida",
                "traits": [],
                "bottlenecks": [],
                "strengths": [],
                "error": str(exc)[:200],
            },
        }


def node_analyzer(state: GraphState) -> dict[str, Any]:
    """Executa Analyzer Agent — correlaciona todos os resultados, usa LLM para narrativa."""
    log.info("node_analyzer_start")
    try:
        agent = AnalyzerAgent(llm_provider=state.get("llm_provider"))
        report = agent.run(
            finops_data=state.get("finops_result"),
            governance_data=state.get("governance_result"),
            cultura_data=state.get("cultura_result"),
        )
        log.info(
            "node_analyzer_done",
            risk_score=round(report.overall_risk_score, 1),
            correlations=len(report.correlated_issues),
        )
        return {"analyzer_result": report.to_dict()}
    except Exception as exc:
        log.error("node_analyzer_error", error=str(exc))
        return {"analyzer_result": {"error": str(exc)}, "errors": [f"analyzer: {exc}"]}


def route_after_planner(state: GraphState) -> list[str]:
    """
    Router pós-planner: envia para os executors que foram ativados.
    Retorna lista de nomes de nós a executar em paralelo.
    """
    plan = state.get("execution_plan", {})
    active = plan.get("active_agents", [])
    log.info("routing", active_agents=active)

    # nome do nó no grafo
    node_map = {
        "finops": "node_finops",
        "data_governance": "node_data_governance",
        "cultura": "node_cultura",
    }
    return [node_map[a] for a in active if a in node_map] or ["node_analyzer"]


def build_graph() -> StateGraph:
    """
    Constrói e compila o grafo LangGraph.
    Retorna o grafo compilado, pronto para .invoke() ou .ainvoke().
    """
    builder = StateGraph(GraphState)

    builder.add_node("node_planner", node_planner)
    builder.add_node("node_finops", node_finops)
    builder.add_node("node_data_governance", node_data_governance)
    builder.add_node("node_cultura", node_cultura)
    builder.add_node("node_analyzer", node_analyzer)

    builder.set_entry_point("node_planner")

    # Planner -> executors (condicional/paralelo)
    builder.add_conditional_edges(
        "node_planner",
        route_after_planner,
        {
            "node_finops": "node_finops",
            "node_data_governance": "node_data_governance",
            "node_cultura": "node_cultura",
            "node_analyzer": "node_analyzer",
        },
    )

    for executor_node in ("node_finops", "node_data_governance", "node_cultura"):
        builder.add_edge(executor_node, "node_analyzer")

    builder.add_edge("node_analyzer", END)

    return builder.compile()


_graph: StateGraph | None = None


def get_graph() -> StateGraph:
    global _graph
    if _graph is None:
        _graph = build_graph()
        log.info("langgraph_compiled")
    return _graph
