"""
Planner Agent — decide quais agentes executar com base nos dados disponíveis.
Lógica 100% determinística. NÃO usa LLM.

Critérios de ativação:
  - FinOps:          algum provider cloud disponível com dados de custo
  - DataGovernance:  recursos de storage/database presentes
  - Cultura:         documento de cultura não vazio
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from logger import get_logger

log = get_logger("planner_agent")


@dataclass
class ExecutionPlan:
    """Plano de execução retornado pelo Planner."""

    run_finops: bool = False
    run_data_governance: bool = False
    run_cultura: bool = False
    rationale: list[str] = field(default_factory=list)
    priority: str = "normal"  # "critical" | "high" | "normal" | "low"

    @property
    def active_agents(self) -> list[str]:
        agents = []
        if self.run_finops:
            agents.append("finops")
        if self.run_data_governance:
            agents.append("data_governance")
        if self.run_cultura:
            agents.append("cultura")
        return agents

    def to_dict(self) -> dict[str, Any]:
        return {
            "active_agents": self.active_agents,
            "run_finops": self.run_finops,
            "run_data_governance": self.run_data_governance,
            "run_cultura": self.run_cultura,
            "rationale": self.rationale,
            "priority": self.priority,
        }


class PlannerAgent:
    """
    Analisa o input disponível e define quais agentes devem ser executados.
    A decisão é puramente baseada na presença e qualidade dos dados.
    """

    def run(
        self,
        cloud_providers: list,
        cultura_text: str,
    ) -> ExecutionPlan:
        log.info("planner_agent_start")
        plan = ExecutionPlan()

        provider_resources = {}

        for provider in cloud_providers:
            try:
                resources = provider.get_resources()
                provider_resources[provider.provider_name()] = resources
            except Exception as exc:
                log.warning(
                    "planner_provider_probe_failed",
                    provider=provider.provider_name(),
                    error=str(exc),
                )

        # FinOps
        active_providers = [
            name for name, resources in provider_resources.items() if resources
        ]

        if active_providers:
            plan.run_finops = True
            plan.rationale.append(
                f"Providers ativos com dados: {', '.join(active_providers)}"
            )

        # Data Governance
        storage_providers = []

        for name, resources in provider_resources.items():
            has_storage = any(
                r.service_type in ("storage", "database") for r in resources
            )
            if has_storage:
                storage_providers.append(name)

        if storage_providers:
            plan.run_data_governance = True
            plan.rationale.append(
                f"Recursos de storage/database detectados em: {', '.join(storage_providers)}"
            )

        # Cultura
        if cultura_text and len(cultura_text.strip()) > 50:
            plan.run_cultura = True
            plan.rationale.append(
                f"Documento de cultura disponível ({len(cultura_text)} chars)"
            )

        # Prioridade
        if plan.run_data_governance and plan.run_finops:
            plan.priority = "high"
        if len(plan.active_agents) == 3:
            plan.priority = "critical"

        log.info(
            "planner_agent_complete",
            active_agents=plan.active_agents,
            priority=plan.priority,
        )

        return plan
