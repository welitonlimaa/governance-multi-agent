"""
Data Governance Agent — motor de risco LGPD 100% determinístico.
NÃO usa LLM para classificar riscos.

Regras de negócio implementadas:
  CRITICAL  -> recurso público + campos PII sensíveis (cpf, email, rg...)
  HIGH      -> recurso público sem controle de acesso
  MEDIUM    -> sem controle de acesso (mas privado) OU sem criptografia
  LOW       -> privado, com controle de acesso e criptografia
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from logger import get_logger
from providers.cloud.base import CloudProvider, CloudResource

log = get_logger("data_governance_agent")

# Campos PII por nível de sensibilidade
_PII_CRITICAL: frozenset[str] = frozenset(
    [
        "cpf",
        "rg",
        "email",
        "senha",
        "password",
        "credit_card",
        "cartao",
        "cnh",
        "passaporte",
        "biometria",
    ]
)
_PII_HIGH: frozenset[str] = frozenset(
    [
        "nome",
        "telefone",
        "celular",
        "endereco",
        "cep",
        "data_nascimento",
        "birth_date",
        "ip_address",
    ]
)
_PII_MEDIUM: frozenset[str] = frozenset(
    ["user_id", "session_id", "device_id", "client_id"]
)

# Artigos LGPD relevantes por tipo de violação
_LGPD_ARTICLES: dict[str, list[str]] = {
    "public_with_pii": ["Art. 6", "Art. 46", "Art. 47", "Art. 48"],
    "public_no_access": ["Art. 46", "Art. 49"],
    "no_access_control": ["Art. 46"],
    "no_encryption": ["Art. 46", "Art. 49"],
    "no_encryption_with_pii": ["Art. 46", "Art. 47", "Art. 49"],
}

RiskLevel = str  # "critical" | "high" | "medium" | "low"


@dataclass
class ResourceFinding:
    resource_id: str
    provider: str
    service_type: str
    risk_level: RiskLevel
    issues: list[str]
    pii_fields: list[str]
    pii_sensitivity: str  # "critical" | "high" | "medium" | "none"
    lgpd_articles: list[str]
    recommendation: str

    def to_dict(self) -> dict[str, Any]:
        return {
            "resource_id": self.resource_id,
            "provider": self.provider,
            "service_type": self.service_type,
            "risk_level": self.risk_level,
            "issues": self.issues,
            "pii_fields": self.pii_fields,
            "pii_sensitivity": self.pii_sensitivity,
            "lgpd_articles": sorted(set(self.lgpd_articles)),
            "recommendation": self.recommendation,
        }


@dataclass
class DataGovernanceReport:
    findings: list[ResourceFinding] = field(default_factory=list)
    risk_summary: dict[str, int] = field(default_factory=dict)
    compliance_score: int = 0  # 0-100 (100 = totalmente conforme)
    pii_exposure_count: int = 0
    provider_errors: list[str] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return {
            "findings": [f.to_dict() for f in self.findings],
            "risk_summary": self.risk_summary,
            "compliance_score": self.compliance_score,
            "pii_exposure_count": self.pii_exposure_count,
            "critical_count": self.risk_summary.get("critical", 0),
            "high_count": self.risk_summary.get("high", 0),
            "provider_errors": self.provider_errors,
        }


def _detect_pii(schema_hint: list[str]) -> tuple[list[str], str]:
    """
    Detecta campos PII e retorna (campos_encontrados, nivel_sensibilidade).
    Nível: "critical" > "high" > "medium" > "none"
    """
    fields_lower = [f.lower() for f in schema_hint]
    found: list[str] = []
    max_level = "none"

    for f in fields_lower:
        if f in _PII_CRITICAL:
            found.append(f)
            max_level = "critical"
        elif f in _PII_HIGH and max_level not in ("critical",):
            found.append(f)
            if max_level != "critical":
                max_level = "high"
        elif f in _PII_MEDIUM and max_level == "none":
            found.append(f)
            max_level = "medium"

    return found, max_level


def _classify_risk(resource: CloudResource) -> ResourceFinding:
    """
    Aplica o motor de regras LGPD sobre um recurso e retorna o finding.
    Ordem de precedência: critical > high > medium > low
    """
    pii_fields, pii_sensitivity = _detect_pii(resource.schema_hint)
    issues: list[str] = []
    lgpd: list[str] = []
    risk: RiskLevel = "low"
    recommendation_parts: list[str] = []

    # Regra 1: Público + PII crítico = CRITICAL
    if resource.is_public and pii_sensitivity == "critical":
        risk = "critical"
        issues.append("recurso público com dados PII críticos")
        lgpd.extend(_LGPD_ARTICLES["public_with_pii"])
        recommendation_parts.append(
            f"Tornar recurso privado IMEDIATAMENTE. "
            f"Campos sensíveis detectados: {', '.join(pii_fields)}."
        )

    # Regra 2: Público + PII alto = HIGH
    elif resource.is_public and pii_sensitivity == "high":
        risk = "high"
        issues.append("recurso público com dados pessoais")
        lgpd.extend(_LGPD_ARTICLES["public_with_pii"])
        recommendation_parts.append(
            f"Restringir acesso público. Campos detectados: {', '.join(pii_fields)}."
        )

    # Regra 3: Público sem controle = HIGH
    elif resource.is_public and not resource.has_access_control:
        risk = "high"
        issues.append("recurso público sem controle de acesso")
        lgpd.extend(_LGPD_ARTICLES["public_no_access"])
        recommendation_parts.append("Implementar ACL e tornar recurso privado.")

    # Regra 4: Público (sem os anteriores) = HIGH
    elif resource.is_public:
        risk = "high"
        issues.append("recurso exposto publicamente")
        lgpd.extend(_LGPD_ARTICLES["public_no_access"])
        recommendation_parts.append("Revisar necessidade de exposição pública.")

    # Regra 5: Sem controle de acesso = MEDIUM
    if not resource.has_access_control and risk not in ("critical", "high"):
        risk = "medium"
        issues.append("sem controle de acesso configurado")
        lgpd.extend(_LGPD_ARTICLES["no_access_control"])
        recommendation_parts.append("Implementar RBAC e policies de acesso.")
    elif not resource.has_access_control:
        issues.append("sem controle de acesso configurado")
        lgpd.extend(_LGPD_ARTICLES["no_access_control"])
        recommendation_parts.append("Implementar RBAC e policies de acesso.")

    # Regra 6: Sem criptografia
    if not resource.has_encryption:
        if pii_fields:
            if risk not in ("critical",):
                risk = "high" if risk == "medium" else risk
            issues.append("dados em repouso sem criptografia (PII exposto)")
            lgpd.extend(_LGPD_ARTICLES["no_encryption_with_pii"])
        else:
            if risk == "low":
                risk = "medium"
            issues.append("dados em repouso sem criptografia")
            lgpd.extend(_LGPD_ARTICLES["no_encryption"])
        recommendation_parts.append("Habilitar criptografia em repouso (SSE/TDE).")

    # PII médio detectado sem outros problemas = MEDIUM mínimo
    if pii_sensitivity in ("critical", "high") and risk == "low":
        risk = "medium"
        issues.append(f"campos pessoais detectados: {', '.join(pii_fields)}")
        recommendation_parts.append("Auditar acesso e implementar data masking.")

    recommendation = (
        " ".join(recommendation_parts)
        if recommendation_parts
        else (
            "Recurso dentro dos padrões de conformidade. Manter monitoramento regular."
        )
    )

    return ResourceFinding(
        resource_id=resource.resource_id,
        provider=resource.provider,
        service_type=resource.service_type,
        risk_level=risk,
        issues=issues,
        pii_fields=pii_fields,
        pii_sensitivity=pii_sensitivity,
        lgpd_articles=lgpd,
        recommendation=recommendation,
    )


def _compute_compliance_score(findings: list[ResourceFinding]) -> int:
    """
    Score 0-100. Penalidades:
      critical: -25 pts
      high:     -15 pts
      medium:   -7 pts
      low:       0 pts
    """
    if not findings:
        return 100
    score = 100
    penalties = {"critical": 25, "high": 15, "medium": 7, "low": 0}
    for f in findings:
        score -= penalties.get(f.risk_level, 0)
    return max(0, score)


class DataGovernanceAgent:
    """
    Avalia conformidade LGPD de recursos cloud.
    Toda classificação é determinística — sem LLM.
    """

    def __init__(self, providers: list[CloudProvider]) -> None:
        self.providers = providers

    def run(self) -> DataGovernanceReport:
        log.info("data_gov_agent_start")
        report = DataGovernanceReport()

        all_resources: list[CloudResource] = []
        for provider in self.providers:
            try:
                resources = provider.get_resources()
                storage_resources = [
                    r for r in resources if r.service_type in ("storage", "database")
                ]
                all_resources.extend(storage_resources)
            except Exception as exc:
                err = f"{provider.provider_name()}: {exc}"
                report.provider_errors.append(err)
                log.error("provider_error", error=err)

        # Classifica cada recurso
        for resource in all_resources:
            finding = _classify_risk(resource)
            report.findings.append(finding)
            log.debug(
                "resource_classified",
                resource_id=resource.resource_id,
                risk=finding.risk_level,
                pii=finding.pii_fields,
            )

        # Sumariza riscos
        risk_summary: dict[str, int] = {"critical": 0, "high": 0, "medium": 0, "low": 0}
        for f in report.findings:
            risk_summary[f.risk_level] = risk_summary.get(f.risk_level, 0) + 1
        report.risk_summary = risk_summary

        # Conta exposições de PII
        report.pii_exposure_count = sum(1 for f in report.findings if f.pii_fields)

        # Score de conformidade
        report.compliance_score = _compute_compliance_score(report.findings)

        # Ordena por severidade
        _order = {"critical": 0, "high": 1, "medium": 2, "low": 3}
        report.findings.sort(key=lambda f: _order.get(f.risk_level, 9))

        log.info(
            "data_gov_agent_complete",
            findings=len(report.findings),
            compliance_score=report.compliance_score,
            risk_summary=risk_summary,
        )
        return report
