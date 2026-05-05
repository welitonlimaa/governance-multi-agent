"""
Analyzer Agent — usa LLM.

Responsabilidade:
  - Receber outputs estruturados dos outros agentes (Python dicts)
  - Calcular métricas agregadas (Python puro)
  - Usar LLM para correlacionar insights entre domínios e gerar narrativa
  - Produzir relatório executivo final

A lógica de agregação (scores, contagens, prioridades) é determinística.
O LLM é usado APENAS para:
  1. Correlação narrativa entre FinOps + Governance + Cultura
  2. Linguagem executiva do relatório
  3. Recomendações priorizadas em linguagem natural
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from logger import get_logger

log = get_logger("analyzer_agent")


@dataclass
class AnalyzerReport:
    # Métricas agregadas
    overall_risk_score: float = 0.0
    financial_exposure: float = 0.0
    savings_opportunity: float = 0.0
    total_critical_findings: int = 0
    domains_analyzed: list[str] = field(default_factory=list)

    # Correlações detectadas deterministicamente
    correlated_issues: list[dict[str, Any]] = field(default_factory=list)
    priority_actions: list[str] = field(default_factory=list)

    # Narrativa gerada pelo LLM
    executive_summary: str = ""
    llm_insights: list[str] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return {
            "overall_risk_score": round(self.overall_risk_score, 1),
            "financial_exposure": round(self.financial_exposure, 2),
            "savings_opportunity": round(self.savings_opportunity, 2),
            "total_critical_findings": self.total_critical_findings,
            "domains_analyzed": self.domains_analyzed,
            "correlated_issues": self.correlated_issues,
            "priority_actions": self.priority_actions,
            "executive_summary": self.executive_summary,
            "llm_insights": self.llm_insights,
        }


def _detect_correlations(
    finops: dict[str, Any] | None,
    governance: dict[str, Any] | None,
    cultura: dict[str, Any] | None,
) -> list[dict[str, Any]]:
    """
    Detecta correlações entre domínios usando lógica Python pura.
    Cada correlação tem: title, severity, domains, evidence.
    """
    correlations: list[dict[str, Any]] = []

    # Correlação 1: Recursos públicos com custo alto = exposição financeira+legal
    if finops and governance:
        critical_count = governance.get("risk_summary", {}).get("critical", 0)
        total_cost = finops.get("total_cost", 0)
        if critical_count > 0 and total_cost > 1000:
            correlations.append(
                {
                    "title": "Alto custo em recursos com violações LGPD críticas",
                    "severity": "critical",
                    "domains": ["finops", "data_governance"],
                    "evidence": (
                        f"{critical_count} recurso(s) crítico(s) com custo total de "
                        f"R$ {total_cost:,.2f}. Exposição financeira e legal simultânea."
                    ),
                }
            )

    # Correlação 2: Cultura burocrática + recursos ociosos = slow remediation
    if cultura and finops:
        maturity = cultura.get("maturity_score", 10)
        idle_count = finops.get("idle_count", 0)
        if maturity < 5 and idle_count > 0:
            correlations.append(
                {
                    "title": "Cultura burocrática retarda remediação de recursos ociosos",
                    "severity": "high",
                    "domains": ["cultura", "finops"],
                    "evidence": (
                        f"Maturidade digital {maturity}/10 indica processo lento de aprovação. "
                        f"{idle_count} recurso(s) ocioso(s) provavelmente mantido(s) por falta de "
                        f"processo ágil de descomissionamento."
                    ),
                }
            )

    # Correlação 3: Gap TI-negócio + recursos sem controle de acesso
    if cultura and governance:
        high_risk = governance.get("risk_summary", {}).get("high", 0)
        culture_type = cultura.get("culture_type", "")
        if "Burocrática" in culture_type or "Hierárquica" in culture_type:
            if high_risk > 0:
                correlations.append(
                    {
                        "title": "Processos hierárquicos impedem implementação de controles de acesso",
                        "severity": "high",
                        "domains": ["cultura", "data_governance"],
                        "evidence": (
                            f"Cultura {culture_type} com {high_risk} recurso(s) de risco alto sem "
                            f"controle de acesso. Aprovações em múltiplos níveis atrasam implementação "
                            f"de policies de segurança."
                        ),
                    }
                )

    # Correlação 4: Sem tags + sem controle de acesso = governança frágil
    if finops and governance:
        untagged = finops.get("untagged_count", 0)
        no_access = governance.get("risk_summary", {}).get(
            "medium", 0
        ) + governance.get("risk_summary", {}).get("high", 0)
        if untagged > 0 and no_access > 0:
            correlations.append(
                {
                    "title": "Ausência de tagueamento e controle de acesso indica maturidade de governança baixa",
                    "severity": "medium",
                    "domains": ["finops", "data_governance"],
                    "evidence": (
                        f"{untagged} recurso(s) sem tags + {no_access} recurso(s) sem controle de acesso. "
                        f"Padrão sistêmico de governança imatura."
                    ),
                }
            )

    return correlations


def _compute_overall_risk(
    governance: dict[str, Any] | None,
    cultura: dict[str, Any] | None,
    finops: dict[str, Any] | None,
) -> float:
    """Calcula score de risco global ponderado (0-10)."""
    score = 0.0
    weight_total = 0.0

    if governance:
        compliance = governance.get("compliance_score", 100)
        gov_risk = (100 - compliance) / 10.0  # 0-10
        score += gov_risk * 0.5
        weight_total += 0.5

    if cultura:
        maturity = cultura.get("maturity_score", 5.0)
        cultura_risk = (10 - maturity) * 0.7  # inverte (baixa maturidade = alto risco)
        score += cultura_risk * 0.3
        weight_total += 0.3

    if finops:
        savings_pct = 0.0
        total = finops.get("total_cost", 0)
        savings = finops.get("savings_potential", 0)
        if total > 0:
            savings_pct = (savings / total) * 10.0
        score += savings_pct * 0.2
        weight_total += 0.2

    return min(10.0, score / weight_total) if weight_total > 0 else 0.0


def _generate_priority_actions(
    finops: dict[str, Any] | None,
    governance: dict[str, Any] | None,
    cultura: dict[str, Any] | None,
    correlations: list[dict[str, Any]],
) -> list[str]:
    """Gera lista ordenada de ações prioritárias (determinístico)."""
    actions: list[str] = []

    # Ações de governance (máxima prioridade)
    if governance:
        for finding in governance.get("findings", []):
            if finding.get("risk_level") == "critical":
                actions.append(
                    f"[CRÍTICO] {finding['resource_id']}: {finding.get('recommendation', 'Remediar imediatamente')}"
                )

    # Ações de FinOps
    if finops:
        idle = finops.get("idle_resources", [])
        if idle:
            idle_cost = finops.get("idle_cost", 0)
            actions.append(
                f"[ALTO] Descomissionar/redimensionar {len(idle)} recurso(s) ocioso(s) "
                f"— economia potencial de ${idle_cost:,.2f}/mês"
            )
        untagged = finops.get("untagged_count", 0)
        if untagged:
            actions.append(
                f"[MÉDIO] Aplicar política de tagueamento obrigatório "
                f"({untagged} recurso(s) sem tags)"
            )

    # Ações de cultura
    if cultura:
        bottlenecks = cultura.get("bottlenecks", [])
        for b in bottlenecks[:2]:
            actions.append(f"[ESTRATÉGICO] Cultura: {b}")

    return actions


class AnalyzerAgent:
    """
    Combina outputs de todos os agentes e gera relatório executivo.
    """

    def __init__(self, llm_provider=None) -> None:
        self.llm = llm_provider

    def run(
        self,
        finops_data: dict[str, Any] | None = None,
        governance_data: dict[str, Any] | None = None,
        cultura_data: dict[str, Any] | None = None,
    ) -> AnalyzerReport:
        log.info(
            "analyzer_agent_start",
            has_finops=finops_data is not None,
            has_governance=governance_data is not None,
            has_cultura=cultura_data is not None,
        )
        report = AnalyzerReport()

        if finops_data:
            report.domains_analyzed.append("finops")
        if governance_data:
            report.domains_analyzed.append("data_governance")
        if cultura_data:
            report.domains_analyzed.append("cultura")

        if finops_data:
            report.savings_opportunity = finops_data.get("savings_potential", 0)

        if governance_data:
            report.total_critical_findings = governance_data.get(
                "risk_summary", {}
            ).get("critical", 0)

            if finops_data:
                high_risk_ids = {
                    f["resource_id"]
                    for f in governance_data.get("findings", [])
                    if f.get("risk_level") in ("critical", "high")
                }
                report.financial_exposure = sum(
                    r["monthly_cost"]
                    for r in finops_data.get("idle_resources", [])
                    if r["resource_id"] in high_risk_ids
                )

        # Risk score global
        report.overall_risk_score = _compute_overall_risk(
            governance_data, cultura_data, finops_data
        )

        # Correlações (determinísticas)
        report.correlated_issues = _detect_correlations(
            finops_data, governance_data, cultura_data
        )

        # Ações prioritárias (determinísticas)
        report.priority_actions = _generate_priority_actions(
            finops_data, governance_data, cultura_data, report.correlated_issues
        )

        # LLM: sumário executivo e insights narrativos
        if self.llm:
            try:
                llm_output = self.llm.correlate(
                    finops=finops_data,
                    governance=governance_data,
                    cultura=cultura_data,
                    correlations=report.correlated_issues,
                    risk_score=report.overall_risk_score,
                )
                report.executive_summary = llm_output.get("executive_summary", "")
                report.llm_insights = llm_output.get("insights", [])
            except Exception as exc:
                log.warning("analyzer_llm_error", error=str(exc))
                report.executive_summary = (
                    "[LLM indisponível — resumo gerado automaticamente]"
                )

        # Fallback se LLM não disponível
        if not report.executive_summary:
            report.executive_summary = self._generate_fallback_summary(report)

        log.info(
            "analyzer_agent_complete",
            overall_risk=round(report.overall_risk_score, 1),
            correlations=len(report.correlated_issues),
            priority_actions=len(report.priority_actions),
        )
        return report

    def _generate_fallback_summary(self, report: "AnalyzerReport") -> str:
        parts = [
            f"Análise multi-domínio concluída. "
            f"Score de risco global: {report.overall_risk_score:.1f}/10.",
        ]
        if report.total_critical_findings:
            parts.append(
                f"{report.total_critical_findings} finding(s) crítico(s) de LGPD requerem ação imediata."
            )
        if report.savings_opportunity:
            parts.append(
                f"Potencial de economia em cloud: ${report.savings_opportunity:,.2f}/mês."
            )
        if report.correlated_issues:
            parts.append(
                f"{len(report.correlated_issues)} correlação(ões) cross-domínio identificada(s)."
            )
        return " ".join(parts)
