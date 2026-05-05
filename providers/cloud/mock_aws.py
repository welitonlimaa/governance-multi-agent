"""
providers/cloud/mock_aws.py
Simula a AWS SDK localmente.
Serve dados fixos realistas — nunca chama APIs reais.
Em produção, substituir por boto3 calls.
"""
from __future__ import annotations

import random
from config import FAILURE_RATE
from logger import get_logger
from providers.cloud.base import CloudProvider, CloudResource

log = get_logger("mock_aws")

# ─── Dados fixos do mock ───────────────────────────────────────────────────────
_MOCK_RESOURCES: list[dict] = [
    {
        "provider": "aws",
        "service_type": "compute",
        "service_name": "ec2",
        "region": "us-east-1",
        "resource_id": "i-123",
        "cost": 820.45,
        "is_idle": True,
        "is_public": False,
        "has_encryption": True,
        "has_access_control": True,
        "tags": ["prod"],
        "schema_hint": [],
    },
    {
        "provider": "aws",
        "service_type": "storage",
        "service_name": "s3",
        "region": "us-east-1",
        "resource_id": "s3://clientes-dados",
        "cost": 1200.00,
        "is_idle": False,
        "is_public": True,
        "has_encryption": False,
        "has_access_control": False,
        "tags": [],
        "schema_hint": ["nome", "cpf", "email"],
    },
    {
        "provider": "aws",
        "service_type": "storage",
        "service_name": "s3",
        "region": "us-west-2",
        "resource_id": "s3://logs-aplicacao",
        "cost": 340.10,
        "is_idle": False,
        "is_public": False,
        "has_encryption": True,
        "has_access_control": True,
        "tags": ["logs", "prod"],
        "schema_hint": ["timestamp", "event_type"],
    },
    {
        "provider": "aws",
        "service_type": "compute",
        "service_name": "lambda",
        "region": "us-east-1",
        "resource_id": "fn-processor",
        "cost": 45.00,
        "is_idle": False,
        "is_public": False,
        "has_encryption": True,
        "has_access_control": True,
        "tags": ["prod"],
        "schema_hint": [],
    },
]


class MockAWSProvider(CloudProvider):
    """Simula boto3/AWS SDK com dados fixos do mock."""

    def provider_name(self) -> str:
        return "aws"

    def get_resources(self) -> list[CloudResource]:
        if FAILURE_RATE > 0 and random.random() < FAILURE_RATE:
            raise ConnectionError("[SIMULATED] AWS API rate limit exceeded")
        log.info("mock_aws_fetch", count=len(_MOCK_RESOURCES))
        return [CloudResource(r) for r in _MOCK_RESOURCES]
