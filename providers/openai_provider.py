from __future__ import annotations

import json
from typing import Any

from providers.base import LLMProvider
from logger import get_logger

log = get_logger("openai_provider")

_SYSTEM_GOVERNANCE = (
    "Você é um consultor sênior de governança cloud e conformidade LGPD. "
    "Escreva em português do Brasil. Seja direto, objetivo e executivo. "
    "Nunca invente dados — use apenas os números fornecidos."
)


class OpenAIProvider(LLMProvider):
    """
    Provider OpenAI — usa a API para gerar apenas narrativa.
    Requer OPENAI_API_KEY no .env.
    """

    def __init__(self) -> None:
        try:
            from openai import OpenAI
            from config import OPENAI_API_KEY, OPENAI_MODEL

            self._client = OpenAI(api_key=OPENAI_API_KEY)
            self._model = OPENAI_MODEL
            log.info("openai_provider_init", model=self._model)
        except ImportError:
            raise ImportError("openai not installed. Run: pip install openai")

    def name(self) -> str:
        return "openai"

    # summarize

    def summarize(self, domain: str, structured_data: dict[str, Any]) -> str:
        """Gera narrativa executiva de um domínio a partir de dados estruturados."""
        prompts = {
            "finops": self._finops_prompt,
            "data_governance": self._governance_prompt,
            "cultura": self._cultura_prompt,
        }
        build_prompt = prompts.get(domain, self._generic_prompt)
        prompt = build_prompt(structured_data)

        return self._call(
            prompt=prompt,
            system=_SYSTEM_GOVERNANCE + " Responda em no máximo 150 palavras.",
        )

    def _finops_prompt(self, d: dict[str, Any]) -> str:
        providers_str = json.dumps(d.get("cost_by_provider", {}), ensure_ascii=False)
        return (
            f"Gere um parágrafo executivo sobre os seguintes dados de FinOps multi-cloud:\n"
            f"- Custo total mensal: ${d.get('total_cost', 0):,.2f}\n"
            f"- Custo por provider: {providers_str}\n"
            f"- Recursos ociosos: {d.get('idle_count', 0)} (custo: ${d.get('idle_cost', 0):,.2f})\n"
            f"- Recursos sem tags: {d.get('untagged_count', 0)}\n"
            f"- Potencial de economia: ${d.get('savings_potential', 0):,.2f}\n"
            f"Inclua recomendação de ação imediata."
        )

    def _governance_prompt(self, d: dict[str, Any]) -> str:
        rs = d.get("risk_summary", {})
        findings_summary = "; ".join(
            f"{f['resource_id']} ({f['risk_level']})" for f in d.get("findings", [])[:4]
        )
        return (
            f"Gere um parágrafo executivo sobre conformidade LGPD com os dados abaixo:\n"
            f"- Score de conformidade: {d.get('compliance_score', 0)}/100\n"
            f"- Riscos: crítico={rs.get('critical',0)}, alto={rs.get('high',0)}, "
            f"médio={rs.get('medium',0)}, baixo={rs.get('low',0)}\n"
            f"- Recursos com PII expostos: {d.get('pii_exposure_count', 0)}\n"
            f"- Principais findings: {findings_summary}\n"
            f"Mencione artigos LGPD relevantes e risco de multa."
        )

    def _cultura_prompt(self, d: dict[str, Any]) -> str:
        traits_str = "; ".join(d.get("traits", [])[:3])
        bottleneck_str = "; ".join(d.get("bottlenecks", [])[:2])
        return (
            f"Gere um parágrafo executivo sobre cultura organizacional:\n"
            f"- Tipo de cultura: {d.get('culture_type', 'N/A')}\n"
            f"- Maturidade digital: {d.get('maturity_score', 0)}/10\n"
            f"- Digital readiness: {d.get('digital_readiness', 'N/A')}\n"
            f"- Traços: {traits_str}\n"
            f"- Gargalos: {bottleneck_str}\n"
            f"Conecte o perfil cultural à capacidade de resposta a riscos de TI."
        )

    def _generic_prompt(self, d: dict[str, Any]) -> str:
        return f"Resuma os seguintes dados em um parágrafo executivo:\n{json.dumps(d, ensure_ascii=False, indent=2)}"

    # correlate

    def correlate(
        self,
        finops: dict[str, Any] | None,
        governance: dict[str, Any] | None,
        cultura: dict[str, Any] | None,
        correlations: list[dict[str, Any]],
        risk_score: float,
    ) -> dict[str, Any]:
        """Gera sumário executivo e insights cruzados com base em dados já processados."""
        sections: list[str] = [
            f"SCORE DE RISCO GLOBAL: {risk_score:.1f}/10\n",
        ]

        if finops and not finops.get("error"):
            sections.append(
                f"FINOPS:\n"
                f"  Custo total: ${finops.get('total_cost', 0):,.2f}/mês\n"
                f"  Recursos ociosos: {finops.get('idle_count', 0)} "
                f"(${finops.get('idle_cost', 0):,.2f} desperdiçado)\n"
                f"  Sem tags: {finops.get('untagged_count', 0)} recursos\n"
            )

        if governance and not governance.get("error"):
            rs = governance.get("risk_summary", {})
            sections.append(
                f"GOVERNANÇA LGPD:\n"
                f"  Score conformidade: {governance.get('compliance_score', 0)}/100\n"
                f"  Crítico: {rs.get('critical', 0)} | Alto: {rs.get('high', 0)} | "
                f"Médio: {rs.get('medium', 0)}\n"
                f"  PII exposto: {governance.get('pii_exposure_count', 0)} recursos\n"
            )

        if cultura and not cultura.get("error"):
            sections.append(
                f"CULTURA:\n"
                f"  Tipo: {cultura.get('culture_type', 'N/A')}\n"
                f"  Maturidade: {cultura.get('maturity_score', 0)}/10\n"
                f"  Readiness: {cultura.get('digital_readiness', 'N/A')}\n"
            )

        if correlations:
            corr_text = "\n".join(
                f"  [{c['severity'].upper()}] {c['title']}: {c['evidence']}"
                for c in correlations
            )
            sections.append(f"CORRELAÇÕES DETECTADAS:\n{corr_text}\n")

        prompt = (
            "Com base nos dados de governança abaixo, responda APENAS com JSON no formato:\n"
            '{"executive_summary": "string (máx 200 palavras)", "insights": ["string", ...]}\n\n'
            "Dados:\n" + "\n".join(sections)
        )

        raw = self._call(
            prompt=prompt,
            system=_SYSTEM_GOVERNANCE
            + " Responda APENAS com JSON válido, sem markdown.",
        )
        return self._parse_json_response(raw)

    # Helpers internos

    def _call(self, prompt: str, system: str = "", max_tokens: int = 600) -> str:
        messages: list[dict[str, str]] = []
        if system:
            messages.append({"role": "system", "content": system})
        messages.append({"role": "user", "content": prompt})

        response = self._client.chat.completions.create(
            model=self._model,
            messages=messages,
            max_tokens=max_tokens,
            temperature=0.3,
        )
        content = response.choices[0].message.content or ""
        tokens = response.usage.total_tokens if response.usage else 0
        log.debug("openai_call", tokens=tokens)
        return content

    def _parse_json_response(self, raw: str) -> dict[str, Any]:
        clean = raw.strip()
        if clean.startswith("```"):
            lines = clean.split("\n")
            clean = "\n".join(lines[1:-1]) if len(lines) > 2 else clean
        try:
            return json.loads(clean)
        except json.JSONDecodeError:
            return {"executive_summary": clean[:500], "insights": []}
