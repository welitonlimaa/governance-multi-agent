"""
providers/cloud/mock_azure.py
Simula Azure SDK localmente.
Em produção, substituir por azure-mgmt-* calls.
"""
from __future__ import annotations

import random
from config import FAILURE_RATE
from logger import get_logger
from providers.cloud.base import CloudProvider, CloudResource

log = get_logger("mock_azure")

_MOCK_RESOURCES: list[dict] = [
    {
        "provider": "azure",
        "service_type": "database",
        "service_name": "sql_database",
        "region": "eastus",
        "resource_id": "db-prod",
        "cost": 980.75,
        "is_idle": False,
        "is_public": False,
        "has_encryption": True,
        "has_access_control": False,
        "tags": ["critical"],
        "schema_hint": [],
    },
    {
        "provider": "azure",
        "service_type": "database",
        "service_name": "sql_database",
        "region": "eastus",
        "resource_id": "db-clientes",
        "cost": 450.00,
        "is_idle": False,
        "is_public": False,
        "has_encryption": True,
        "has_access_control": False,
        "tags": [],
        "schema_hint": ["id", "nome", "telefone"],
    },
    {
        "provider": "azure",
        "service_type": "compute",
        "service_name": "virtual_machine",
        "region": "westeurope",
        "resource_id": "vm-staging",
        "cost": 180.00,
        "is_idle": True,
        "is_public": False,
        "has_encryption": False,
        "has_access_control": True,
        "tags": ["staging"],
        "schema_hint": [],
    },
    {
        "provider": "azure",
        "service_type": "storage",
        "service_name": "blob_storage",
        "region": "eastus",
        "resource_id": "blob-backups",
        "cost": 220.00,
        "is_idle": False,
        "is_public": False,
        "has_encryption": True,
        "has_access_control": True,
        "tags": ["backup"],
        "schema_hint": [],
    },
]


class MockAzureProvider(CloudProvider):
    """Simula Azure SDK com dados fixos do mock."""

    def provider_name(self) -> str:
        return "azure"

    def get_resources(self) -> list[CloudResource]:
        if FAILURE_RATE > 0 and random.random() < FAILURE_RATE:
            raise ConnectionError("[SIMULATED] Azure throttling error")
        log.info("mock_azure_fetch", count=len(_MOCK_RESOURCES))
        return [CloudResource(r) for r in _MOCK_RESOURCES]
