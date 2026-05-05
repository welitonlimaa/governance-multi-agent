"""
Interface abstrata para provedores de LLM.

O LLM é usado APENAS para:
  - summarize() -> narrar resultados estruturados em linguagem natural
  - correlate()  -> gerar insights cruzados entre domínios (FinOps + LGPD + Cultura)
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from typing import Any


class LLMProvider(ABC):
    """Contrato mínimo que todo provider de LLM deve implementar."""

    @abstractmethod
    def name(self) -> str:
        """Identificador do provider (mock, openai, anthropic...)."""

    @abstractmethod
    def summarize(self, domain: str, structured_data: dict[str, Any]) -> str:
        """
        Recebe dados JÁ PROCESSADOS por um agente e retorna narrativa.

        Args:
            domain:          Nome do domínio ("finops" | "data_governance" | "cultura")
            structured_data: Output tipado do agente (dicts com valores calculados)

        Returns:
            Parágrafo narrativo em português. Máx ~150 palavras.
        """

    @abstractmethod
    def correlate(
        self,
        finops: dict[str, Any] | None,
        governance: dict[str, Any] | None,
        cultura: dict[str, Any] | None,
        correlations: list[dict[str, Any]],
        risk_score: float,
    ) -> dict[str, Any]:
        """
        Recebe outputs de todos os agentes + correlações já detectadas e
        gera sumário executivo + insights narrativos.

        Returns dict com:
            {
                "executive_summary": str,
                "insights": list[str]   # máx 5 itens
            }
        """
