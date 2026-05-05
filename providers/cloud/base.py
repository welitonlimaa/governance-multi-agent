"""
providers/cloud/base.py
Contrato que todos os cloud providers (mock ou real) devem seguir.
Os agentes dependem apenas desta interface — nunca da implementação concreta.
"""
from __future__ import annotations

from abc import ABC, abstractmethod
from typing import Any


class CloudResource:
    """Modelo normalizado de um recurso cloud (CCM – Common Cloud Model)."""

    __slots__ = (
        "provider", "service_type", "service_name", "region",
        "resource_id", "cost", "is_idle", "is_public",
        "has_encryption", "has_access_control", "tags", "schema_hint",
    )

    def __init__(self, raw: dict[str, Any]) -> None:
        self.provider: str            = raw.get("provider", "unknown")
        self.service_type: str        = raw.get("service_type", "unknown")
        self.service_name: str        = raw.get("service_name", "unknown")
        self.region: str              = raw.get("region", "unknown")
        self.resource_id: str         = raw.get("resource_id", "unknown")
        self.cost: float              = float(raw.get("cost", 0.0))
        self.is_idle: bool            = bool(raw.get("is_idle", False))
        self.is_public: bool          = bool(raw.get("is_public", False))
        self.has_encryption: bool     = bool(raw.get("has_encryption", True))
        self.has_access_control: bool = bool(raw.get("has_access_control", True))
        self.tags: list[str]          = raw.get("tags", [])
        self.schema_hint: list[str]   = raw.get("schema_hint", [])

    def to_dict(self) -> dict[str, Any]:
        return {slot: getattr(self, slot) for slot in self.__slots__}


class CloudProvider(ABC):
    """Interface base para provedores cloud."""

    @abstractmethod
    def get_resources(self) -> list[CloudResource]:
        """Retorna todos os recursos do provider, normalizados em CloudResource."""

    @abstractmethod
    def provider_name(self) -> str:
        """Identificador do provider (aws, gcp, azure...)."""
