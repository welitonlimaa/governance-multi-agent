"""
providers/cloud/mock_gcp.py
Simula Google Cloud SDK localmente.
Em produção, substituir por google-cloud-* calls.
"""
from __future__ import annotations

import random
from config import FAILURE_RATE
from logger import get_logger
from providers.cloud.base import CloudProvider, CloudResource

log = get_logger("mock_gcp")

_MOCK_RESOURCES: list[dict] = [
    {
        "provider": "gcp",
        "service_type": "compute",
        "service_name": "compute_engine",
        "region": "us-central1",
        "resource_id": "vm-1",
        "cost": 430.10,
        "is_idle": True,
        "is_public": False,
        "has_encryption": True,
        "has_access_control": True,
        "tags": ["dev"],
        "schema_hint": [],
    },
    {
        "provider": "gcp",
        "service_type": "storage",
        "service_name": "cloud_storage",
        "region": "us-central1",
        "resource_id": "gs://analytics-temp",
        "cost": 98.50,
        "is_idle": False,
        "is_public": True,
        "has_encryption": True,
        "has_access_control": False,
        "tags": [],
        "schema_hint": ["session_id", "user_id"],
    },
    {
        "provider": "gcp",
        "service_type": "database",
        "service_name": "bigquery",
        "region": "us-central1",
        "resource_id": "bq-analytics-prod",
        "cost": 215.80,
        "is_idle": False,
        "is_public": False,
        "has_encryption": True,
        "has_access_control": True,
        "tags": ["analytics", "prod"],
        "schema_hint": ["event_id", "user_id", "timestamp"],
    },
]


class MockGCPProvider(CloudProvider):
    """Simula Google Cloud SDK com dados fixos do mock."""

    def provider_name(self) -> str:
        return "gcp"

    def get_resources(self) -> list[CloudResource]:
        if FAILURE_RATE > 0 and random.random() < FAILURE_RATE:
            raise ConnectionError("[SIMULATED] GCP quota exceeded")
        log.info("mock_gcp_fetch", count=len(_MOCK_RESOURCES))
        return [CloudResource(r) for r in _MOCK_RESOURCES]
