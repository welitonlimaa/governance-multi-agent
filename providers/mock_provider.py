"""
LLM mock totalmente local — NÃO requer API key.

Responsabilidade ÚNICA: gerar NARRATIVA sobre dados já calculados.
Este provider NÃO calcula custos, NÃO classifica riscos, NÃO detecta PII.
Toda lógica de negócio fica nos agentes.

Implementa os dois métodos do contrato:
  - summarize()  -> narrativa de um domínio
  - correlate()  -> sumário executivo cruzado
"""

from __future__ import annotations

from typing import Any

from providers.base import LLMProvider


class MockLLMProvider(LLMProvider):
    """
    Provider mock determinístico que gera narrativa a partir de dados estruturados.
    Ideal para desenvolvimento, CI e ambientes sem API key.
    """

    def name(self) -> str:
        return "mock"

    # ─────────────────────────────────────────────────────────────────────────
    # summarize — narrativa por domínio
    # ─────────────────────────────────────────────────────────────────────────

    def summarize(self, domain: str, structured_data: dict[str, Any]) -> str:
        """Gera parágrafo narrativo a partir de dados já processados pelo agente."""
        dispatch = {
            "finops": self._summarize_finops,
            "data_governance": self._summarize_governance,
            "cultura": self._summarize_cultura,
        }
        handler = dispatch.get(domain, self._summarize_generic)
        return handler(structured_data)

    def _summarize_finops(self, data: dict[str, Any]) -> str:
        total = data.get("total_cost", 0)
        idle_ct = data.get("idle_count", 0)
        idle_cost = data.get("idle_cost", 0)
        savings = data.get("savings_potential", 0)
        untagged = data.get("untagged_count", 0)

        providers_str = ", ".join(
            f"{p.upper()} (${c:,.0f})"
            for p, c in data.get("cost_by_provider", {}).items()
        )

        return (
            f"[MOCK] A infraestrutura multi-cloud totaliza ${total:,.2f}/mês distribuídos entre "
            f"{providers_str}. Foram identificados {idle_ct} recurso(s) ocioso(s) representando "
            f"${idle_cost:,.2f} em custo desperdiçado — potencial de economia de ${savings:,.2f}/mês. "
            f"Adicionalmente, {untagged} recurso(s) operam sem tags, comprometendo a rastreabilidade "
            f"e o chargeback. Recomenda-se revisão imediata dos recursos ociosos e implementação "
            f"de política de tagueamento obrigatório."
        )

    def _summarize_governance(self, data: dict[str, Any]) -> str:
        score = data.get("compliance_score", 0)
        rs = data.get("risk_summary", {})
        pii_ct = data.get("pii_exposure_count", 0)
        critical = rs.get("critical", 0)
        high = rs.get("high", 0)

        urgency = (
            "IMEDIATA" if critical > 0 else ("URGENTE" if high > 0 else "PLANEJADA")
        )

        return (
            f"[MOCK] O score de conformidade LGPD da organização é {score}/100, indicando "
            f"{'alto risco regulatório' if score < 50 else 'conformidade parcial'}. "
            f"Foram detectados {critical} finding(s) crítico(s) e {high} de risco alto, "
            f"com {pii_ct} recurso(s) expondo dados pessoais (PII). "
            f"A ação regulatória é {urgency} — o descumprimento do Art. 46 e 49 da LGPD "
            f"pode acarretar multas de até 2% do faturamento bruto (limitadas a R$50M por infração)."
        )

    def _summarize_cultura(self, data: dict[str, Any]) -> str:
        c_type = data.get("culture_type", "Indefinida")
        maturity = data.get("maturity_score", 0)
        readiness = data.get("digital_readiness", "indefinida")
        bottlenecks = data.get("bottlenecks", [])
        traits = data.get("traits", [])

        bottleneck_str = (
            f" Os principais gargalos são: {'; '.join(bottlenecks[:2])}."
            if bottlenecks
            else ""
        )
        traits_str = f" Traços dominantes: {', '.join(traits[:3])}." if traits else ""

        return (
            f"[MOCK] A organização exibe cultura predominantemente {c_type}, com maturidade "
            f"digital de {maturity}/10 e digital readiness classificada como '{readiness}'."
            f"{traits_str}{bottleneck_str} "
            f"Para acelerar a adoção de práticas modernas de governança cloud, "
            f"é essencial reduzir a cadeia de aprovação e criar canais ágeis entre TI e negócio."
        )

    def _summarize_generic(self, data: dict[str, Any]) -> str:
        return (
            f"[MOCK] Análise concluída. {len(data)} métricas processadas pelo agente."
        )

    # ─────────────────────────────────────────────────────────────────────────
    # correlate — sumário executivo cruzado
    # ─────────────────────────────────────────────────────────────────────────

    def correlate(
        self,
        finops: dict[str, Any] | None,
        governance: dict[str, Any] | None,
        cultura: dict[str, Any] | None,
        correlations: list[dict[str, Any]],
        risk_score: float,
    ) -> dict[str, Any]:
        """
        Gera sumário executivo e insights cruzados a partir de dados já processados.
        NÃO recalcula nenhum valor — apenas narra e conecta os achados.
        """
        # ── Construir sumário executivo ──────────────────────────────────────
        parts: list[str] = [
            f"[MOCK] A análise integrada de governança multi-cloud apresenta score de risco "
            f"global de {risk_score:.1f}/10."
        ]

        if finops and not finops.get("error"):
            parts.append(
                f"No plano financeiro, o custo total de ${finops.get('total_cost', 0):,.0f}/mês "
                f"com {finops.get('idle_count', 0)} recurso(s) ocioso(s) sinaliza maturidade "
                f"FinOps ainda incipiente."
            )

        if governance and not governance.get("error"):
            score = governance.get("compliance_score", 0)
            crit = governance.get("risk_summary", {}).get("critical", 0)
            parts.append(
                f"Em conformidade LGPD (score {score}/100), "
                f"{'há ' + str(crit) + ' violação(ões) crítica(s) de dados pessoais que exigem ação imediata. ' if crit else 'os riscos são gerenciáveis com ações planejadas. '}"
            )

        if cultura and not cultura.get("error"):
            parts.append(
                f"A cultura {cultura.get('culture_type', '')} (maturidade {cultura.get('maturity_score', 0)}/10) "
                f"representa o fator de amplificação dos riscos — processos lentos de aprovação "
                f"retardam a remediação dos problemas identificados."
            )

        executive_summary = " ".join(parts)

        # ── Insights cruzados (narrativa das correlações já calculadas) ──────
        insights: list[str] = []

        for corr in correlations[:5]:
            title = corr.get("title", "")
            severity = corr.get("severity", "medium").upper()
            evidence = corr.get("evidence", "")
            insights.append(f"[{severity}] {title}: {evidence}")

        # Insight de síntese final
        if len(correlations) >= 2:
            insights.append(
                "[MOCK] A convergência de riscos financeiros, regulatórios e culturais "
                "recomenda um programa integrado de governança, não ações isoladas por domínio."
            )

        if not insights:
            insights.append(
                "[MOCK] Nenhuma correlação crítica entre domínios detectada nesta execução."
            )

        return {
            "executive_summary": executive_summary,
            "insights": insights,
        }
