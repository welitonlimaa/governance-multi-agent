"""
providers/cloud/real_gcp.py
Provider GCP REAL — usa google-cloud-* SDKs para buscar dados reais.

Para ativar:
  1. pip install google-cloud-billing google-cloud-compute google-cloud-storage
  2. Configurar: export GOOGLE_APPLICATION_CREDENTIALS=/path/to/key.json
  3. Definir no .env: CLOUD_GCP_MODE=real
"""

from __future__ import annotations

import os
from typing import Any

from providers.cloud.base import CloudProvider, CloudResource
from logger import get_logger

log = get_logger("real_gcp")


class RealGCPProvider(CloudProvider):
    """
    Busca recursos e custos reais do GCP.

    Serviços consultados:
      - Cloud Billing API  -> custos
      - Compute Engine API -> VMs
      - Cloud Storage API  -> buckets
      - BigQuery API       -> datasets

    Requer: google-cloud-billing, google-cloud-compute, google-cloud-storage
    """

    def __init__(self) -> None:
        self._project_id = os.getenv("GCP_PROJECT_ID", "")
        if not self._project_id:
            raise ValueError("GCP_PROJECT_ID não definido no .env")
        try:
            from google.oauth2 import service_account
            from google.cloud import compute_v1, storage

            self._compute_client = compute_v1.InstancesClient()
            self._storage_client = storage.Client(project=self._project_id)
            log.info("real_gcp_init", project=self._project_id)
        except ImportError:
            raise ImportError(
                "google-cloud SDKs não instalados.\n"
                "Execute: pip install google-cloud-compute google-cloud-storage"
            )

    def provider_name(self) -> str:
        return "gcp"

    def get_resources(self) -> list[CloudResource]:
        resources: list[CloudResource] = []
        resources.extend(self._get_compute_instances())
        resources.extend(self._get_storage_buckets())
        log.info("real_gcp_fetch_complete", count=len(resources))
        return resources

    # ── Compute Engine ────────────────────────────────────────────────────────

    def _get_compute_instances(self) -> list[CloudResource]:
        from google.cloud import compute_v1

        resources = []
        zones_client = compute_v1.ZonesClient()

        for zone in zones_client.list(project=self._project_id):
            instances_client = compute_v1.InstancesClient()
            for instance in instances_client.list(
                project=self._project_id, zone=zone.name
            ):
                is_running = instance.status == "RUNNING"
                tags = list(instance.labels.values()) if instance.labels else []

                resources.append(
                    CloudResource(
                        {
                            "provider": "gcp",
                            "service_type": "compute",
                            "service_name": "compute_engine",
                            "region": zone.name,
                            "resource_id": instance.name,
                            "cost": 0.0,  # TODO: buscar via Billing API
                            "is_idle": not is_running,
                            "is_public": self._has_public_ip(instance),
                            "has_encryption": True,  # GCP encrypt at rest by default
                            "has_access_control": True,  # TODO: checar IAM bindings
                            "tags": tags,
                            "schema_hint": [],
                        }
                    )
                )

        log.debug("real_gcp_compute", count=len(resources))
        return resources

    # ── Cloud Storage ─────────────────────────────────────────────────────────

    def _get_storage_buckets(self) -> list[CloudResource]:
        resources = []
        for bucket in self._storage_client.list_buckets():
            iam_config = bucket.iam_configuration
            is_public = not iam_config.uniform_bucket_level_access_enabled

            resources.append(
                CloudResource(
                    {
                        "provider": "gcp",
                        "service_type": "storage",
                        "service_name": "cloud_storage",
                        "region": bucket.location,
                        "resource_id": f"gs://{bucket.name}",
                        "cost": 0.0,  # TODO: buscar via Billing API
                        "is_idle": False,
                        "is_public": is_public,
                        "has_encryption": bucket.default_kms_key_name is not None
                        or True,
                        "has_access_control": iam_config.uniform_bucket_level_access_enabled,
                        "tags": list(bucket.labels.values()) if bucket.labels else [],
                        "schema_hint": [],  # TODO: detectar via Data Catalog
                    }
                )
            )

        log.debug("real_gcp_storage", count=len(resources))
        return resources

    # ── Helpers ───────────────────────────────────────────────────────────────

    def _has_public_ip(self, instance: Any) -> bool:
        for iface in instance.network_interfaces:
            if iface.access_configs:
                return True
        return False
