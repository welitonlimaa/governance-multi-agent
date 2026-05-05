"""
Formata e persiste o relatório final no S3 simulado.
Também gera uma versão legível em texto (console summary).
"""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

from storage.s3_sim import get_bucket
from logger import get_logger

log = get_logger("report_writer")

_BUCKET_NAME = "governance-reports"
_SEPARATOR = "─" * 60


def _risk_badge(level: str) -> str:
    badges = {
        "critical": "🔴 CRÍTICO",
        "high": "🟠 ALTO",
        "medium": "🟡 MÉDIO",
        "low": "🟢 BAIXO",
    }
    return badges.get(level.lower(), level.upper())


def persist_report(
    execution_id: str,
    final_state: dict[str, Any],
) -> str:
    """
    Salva o relatório completo no S3 simulado.
    Retorna a URI do objeto salvo.
    """
    bucket = get_bucket(_BUCKET_NAME)
    key = f"reports/{execution_id}.json"

    report_body = {
        "execution_id": execution_id,
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "plan": final_state.get("execution_plan", {}),
        "finops": final_state.get("finops_result"),
        "data_governance": final_state.get("governance_result"),
        "cultura": final_state.get("cultura_result"),
        "analysis": final_state.get("analyzer_result"),
        "errors": final_state.get("errors", []),
    }

    uri = bucket.put_object(
        key=key,
        body=report_body,
        metadata={
            "execution_id": execution_id,
            "generated_at": datetime.now(timezone.utc).isoformat(),
        },
    )
    log.info("report_saved", uri=uri)
    return uri


def print_summary(final_state: dict[str, Any]) -> None:
    """
    Imprime um resumo legível no console.
    Não substitui o JSON completo no S3.
    """
    print(f"\n{'═' * 60}")
    print("  RELATÓRIO EXECUTIVO — GOVERNANÇA MULTI-CLOUD")
    print(f"{'═' * 60}")

    # Plano de execução
    plan = final_state.get("execution_plan", {})
    if plan:
        print(f"\n---> AGENTES EXECUTADOS: {', '.join(plan.get('active_agents', []))}")
        print(f"   Prioridade: {plan.get('priority', 'N/A').upper()}")

    # FinOps
    finops = final_state.get("finops_result")
    if finops and "error" not in finops:
        print(f"\n{_SEPARATOR}")
        print("*** FINOPS")
        print(f"   Custo total mensal:    ${finops.get('total_cost', 0):>10,.2f}")
        print(
            f"   Potencial de economia: ${finops.get('savings_potential', 0):>10,.2f}"
        )
        print(f"   Recursos ociosos:      {finops.get('idle_count', 0)} recurso(s)")
        print(f"   Sem tags:              {finops.get('untagged_count', 0)} recurso(s)")

        print("\n   Custo por provider:")
        for provider, cost in finops.get("cost_by_provider", {}).items():
            print(f"     {provider.upper():<8} ${cost:>10,.2f}")

        idle = finops.get("idle_resources", [])
        if idle:
            print("\n   Recursos ociosos:")
            for r in idle:
                print(
                    f"     • {r['resource_id']} ({r['provider']}) — ${r['monthly_cost']:,.2f}/mês"
                )

    # Data Governance
    gov = final_state.get("governance_result")
    if gov and "error" not in gov:
        print(f"\n{_SEPARATOR}")
        print("*** GOVERNANÇA DE DADOS (LGPD)")
        print(f"   Score de conformidade: {gov.get('compliance_score', 0)}/100")
        print(
            f"   Exposição de PII:      {gov.get('pii_exposure_count', 0)} recurso(s)"
        )

        rs = gov.get("risk_summary", {})
        print(f"   Distribuição de riscos:")
        print(f"     🔴 Crítico: {rs.get('critical', 0)}")
        print(f"     🟠 Alto:    {rs.get('high', 0)}")
        print(f"     🟡 Médio:   {rs.get('medium', 0)}")
        print(f"     🟢 Baixo:   {rs.get('low', 0)}")

        print("\n   Findings:")
        for f in gov.get("findings", []):
            badge = _risk_badge(f.get("risk_level", "low"))
            pii = f.get("pii_fields", [])
            pii_str = f" | PII: {', '.join(pii)}" if pii else ""
            print(f"     {badge} {f['resource_id']}{pii_str}")
            print(f"       -> {f.get('recommendation', '')[:80]}")

    # Cultura
    cult = final_state.get("cultura_result")
    if cult and "error" not in cult:
        print(f"\n{_SEPARATOR}")
        print("*** CULTURA ORGANIZACIONAL")
        print(f"   Tipo:              {cult.get('culture_type', 'N/A')}")
        print(f"   Maturidade digital: {cult.get('maturity_score', 0)}/10")
        print(f"   Readiness digital:  {cult.get('digital_readiness', 'N/A')}")

        traits = cult.get("traits", [])
        if traits:
            print("\n   Traços identificados:")
            for t in traits:
                print(f"     • {t}")

        bottlenecks = cult.get("bottlenecks", [])
        if bottlenecks:
            print("\n   Gargalos:")
            for b in bottlenecks:
                print(f"     ⚠ {b}")

    # Análise consolidada
    analyzer = final_state.get("analyzer_result")
    if analyzer and "error" not in analyzer:
        print(f"\n{_SEPARATOR}")
        print("!!! ANÁLISE CONSOLIDADA")
        print(
            f"   Score de risco global:   {analyzer.get('overall_risk_score', 0):.1f}/10"
        )
        print(
            f"   Correlações detectadas:  {len(analyzer.get('correlated_issues', []))}"
        )

        correlations = analyzer.get("correlated_issues", [])
        if correlations:
            print("\n   Correlações:")
            for c in correlations:
                badge = _risk_badge(c.get("severity", "medium"))
                print(f"     {badge} {c['title']}")
                print(f"       {c.get('evidence', '')[:90]}")

        actions = analyzer.get("priority_actions", [])
        if actions:
            print("\n   Ações prioritárias:")
            for a in actions:
                print(f"     -> {a}")

        summary = analyzer.get("executive_summary", "")
        if summary:
            print(f"\n   Sumário executivo:")
            words = summary.split()
            line = "     "
            for word in words:
                if len(line) + len(word) > 70:
                    print(line)
                    line = "     " + word + " "
                else:
                    line += word + " "
            if line.strip():
                print(line)

    # Erros
    errors = final_state.get("errors", [])
    if errors:
        print(f"\n{_SEPARATOR}")
        print("Error:  ERROS DURANTE EXECUÇÃO:")
        for e in errors:
            print(f"   • {e}")

    print(f"\n{'═' * 60}\n")
