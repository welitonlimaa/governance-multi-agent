"""
FinOps Agent — lógica 100% determinística.
NÃO usa LLM para cálculos.

Responsabilidades:
  - Coletar recursos de todos os cloud providers
  - Calcular custo total e por provider
  - Identificar recursos ociosos
  - Identificar recursos sem tags
  - Calcular potencial de economia
"""

from __future__ import annotations

from collections import defaultdict
from dataclasses import dataclass, field
from typing import Any

from logger import get_logger
from providers.cloud.base import CloudProvider, CloudResource

log = get_logger("finops_agent")

# PIIs que aumentam a criticidade de um recurso ocioso
_PII_FIELDS: frozenset[str] = frozenset(
    ["cpf", "email", "nome", "telefone", "rg", "cnpj", "endereco"]
)

# Threshold: custo mensal considerado "alto" para um único recurso
_HIGH_COST_THRESHOLD: float = 500.0


@dataclass
class IdleResource:
    resource_id: str
    provider: str
    service_type: str
    cost: float
    tags: list[str]
    has_tags: bool

    def to_dict(self) -> dict[str, Any]:
        return {
            "resource_id": self.resource_id,
            "provider": self.provider,
            "service_type": self.service_type,
            "monthly_cost": round(self.cost, 2),
            "tags": self.tags,
            "has_tags": self.has_tags,
        }


@dataclass
class FinOpsReport:
    total_cost: float = 0.0
    cost_by_provider: dict[str, float] = field(default_factory=dict)
    cost_by_service_type: dict[str, float] = field(default_factory=dict)
    idle_resources: list[IdleResource] = field(default_factory=list)
    untagged_resources: list[str] = field(default_factory=list)
    high_cost_resources: list[dict[str, Any]] = field(default_factory=list)
    savings_potential: float = 0.0
    provider_errors: list[str] = field(default_factory=list)
    total_resources: int = 0

    def to_dict(self) -> dict[str, Any]:
        return {
            "total_cost": round(self.total_cost, 2),
            "cost_by_provider": {
                k: round(v, 2) for k, v in self.cost_by_provider.items()
            },
            "cost_by_service_type": {
                k: round(v, 2) for k, v in self.cost_by_service_type.items()
            },
            "idle_resources": [r.to_dict() for r in self.idle_resources],
            "idle_count": len(self.idle_resources),
            "idle_cost": round(sum(r.cost for r in self.idle_resources), 2),
            "untagged_resources": self.untagged_resources,
            "untagged_count": len(self.untagged_resources),
            "high_cost_resources": self.high_cost_resources,
            "savings_potential": round(self.savings_potential, 2),
            "provider_errors": self.provider_errors,
            "total_resources": self.total_resources,
        }


class FinOpsAgent:
    """
    Processa dados de múltiplos cloud providers e produz análise de custos.
    """

    def __init__(self, providers: list[CloudProvider]) -> None:
        self.providers = providers

    def run(self) -> FinOpsReport:
        """
        Ponto de entrada principal.
        1. Coleta recursos de todos os providers (com tratamento de falha)
        2. Aplica lógica analítica
        3. Retorna FinOpsReport estruturado
        """
        log.info(
            "finops_agent_start", providers=[p.provider_name() for p in self.providers]
        )

        all_resources: list[CloudResource] = []
        report = FinOpsReport()

        # Coleta de dados
        for provider in self.providers:
            try:
                resources = provider.get_resources()
                all_resources.extend(resources)
                log.info(
                    "provider_fetched",
                    provider=provider.provider_name(),
                    count=len(resources),
                )
            except Exception as exc:
                err_msg = f"{provider.provider_name()}: {exc}"
                report.provider_errors.append(err_msg)
                log.error(
                    "provider_fetch_error",
                    provider=provider.provider_name(),
                    error=str(exc),
                )

        report.total_resources = len(all_resources)

        # Custo total
        report.total_cost = sum(r.cost for r in all_resources)

        # Custo por provider
        by_provider: dict[str, float] = defaultdict(float)
        for r in all_resources:
            by_provider[r.provider] += r.cost
        report.cost_by_provider = dict(by_provider)

        # Custo por tipo de serviço
        by_type: dict[str, float] = defaultdict(float)
        for r in all_resources:
            by_type[r.service_type] += r.cost
        report.cost_by_service_type = dict(by_type)

        # Recursos ociosos
        for r in all_resources:
            if r.is_idle:
                report.idle_resources.append(
                    IdleResource(
                        resource_id=r.resource_id,
                        provider=r.provider,
                        service_type=r.service_type,
                        cost=r.cost,
                        tags=r.tags,
                        has_tags=bool(r.tags),
                    )
                )

        # Potencial de economia (custo dos recursos ociosos)
        report.savings_potential = sum(r.cost for r in report.idle_resources)

        # Recursos sem tags
        report.untagged_resources = [r.resource_id for r in all_resources if not r.tags]

        # Recursos de alto custo
        report.high_cost_resources = [
            {
                "resource_id": r.resource_id,
                "provider": r.provider,
                "service_type": r.service_type,
                "cost": round(r.cost, 2),
            }
            for r in sorted(all_resources, key=lambda x: x.cost, reverse=True)
            if r.cost >= _HIGH_COST_THRESHOLD
        ]

        log.info(
            "finops_agent_complete",
            total_cost=round(report.total_cost, 2),
            idle_count=len(report.idle_resources),
            savings_potential=round(report.savings_potential, 2),
            errors=len(report.provider_errors),
        )
        return report
