"""
providers/cloud/real_azure.py
Provider Azure REAL — usa azure-mgmt-* SDKs para buscar dados reais.

Para ativar:
  1. pip install azure-mgmt-compute azure-mgmt-storage azure-mgmt-sql azure-identity azure-mgmt-costmanagement
  2. Definir no .env:
       AZURE_SUBSCRIPTION_ID=xxx
       AZURE_TENANT_ID=xxx
       AZURE_CLIENT_ID=xxx
       AZURE_CLIENT_SECRET=xxx
  3. Definir no .env: CLOUD_AZURE_MODE=real
"""

from __future__ import annotations

import os
from typing import Any

from providers.cloud.base import CloudProvider, CloudResource
from logger import get_logger

log = get_logger("real_azure")


class RealAzureProvider(CloudProvider):
    """
    Busca recursos e custos reais do Azure.

    Serviços consultados:
      - Cost Management API  -> custos
      - Compute              -> VMs
      - Storage              -> Blob Storage Accounts
      - SQL Database         -> bancos gerenciados

    Requer: azure-mgmt-compute, azure-mgmt-storage, azure-mgmt-sql,
            azure-identity, azure-mgmt-costmanagement
    """

    def __init__(self) -> None:
        self._subscription_id = os.getenv("AZURE_SUBSCRIPTION_ID", "")
        if not self._subscription_id:
            raise ValueError("AZURE_SUBSCRIPTION_ID não definido no .env")
        try:
            from azure.identity import DefaultAzureCredential
            from azure.mgmt.compute import ComputeManagementClient
            from azure.mgmt.storage import StorageManagementClient
            from azure.mgmt.sql import SqlManagementClient

            cred = DefaultAzureCredential()
            self._compute = ComputeManagementClient(cred, self._subscription_id)
            self._storage = StorageManagementClient(cred, self._subscription_id)
            self._sql = SqlManagementClient(cred, self._subscription_id)
            log.info("real_azure_init", subscription=self._subscription_id)
        except ImportError:
            raise ImportError(
                "azure SDKs não instalados.\n"
                "Execute: pip install azure-mgmt-compute azure-mgmt-storage "
                "azure-mgmt-sql azure-identity"
            )

    def provider_name(self) -> str:
        return "azure"

    def get_resources(self) -> list[CloudResource]:
        resources: list[CloudResource] = []
        resources.extend(self._get_virtual_machines())
        resources.extend(self._get_storage_accounts())
        resources.extend(self._get_sql_databases())
        log.info("real_azure_fetch_complete", count=len(resources))
        return resources

    # ── Virtual Machines ──────────────────────────────────────────────────────

    def _get_virtual_machines(self) -> list[CloudResource]:
        resources = []
        for vm in self._compute.virtual_machines.list_all():
            status = self._get_vm_status(vm)
            is_idle = status != "running"
            tags = list(vm.tags.values()) if vm.tags else []

            resources.append(
                CloudResource(
                    {
                        "provider": "azure",
                        "service_type": "compute",
                        "service_name": "virtual_machine",
                        "region": vm.location,
                        "resource_id": vm.name,
                        "cost": 0.0,  # TODO: buscar via Cost Management API
                        "is_idle": is_idle,
                        "is_public": False,  # TODO: checar public IP allocation
                        "has_encryption": self._vm_has_encryption(vm),
                        "has_access_control": True,  # TODO: checar NSG rules
                        "tags": tags,
                        "schema_hint": [],
                    }
                )
            )

        log.debug("real_azure_vms", count=len(resources))
        return resources

    # ── Storage Accounts ──────────────────────────────────────────────────────

    def _get_storage_accounts(self) -> list[CloudResource]:
        resources = []
        for account in self._storage.storage_accounts.list():
            encryption = account.encryption
            has_enc = encryption is not None and encryption.services is not None
            is_public = account.allow_blob_public_access or False
            tags = list(account.tags.values()) if account.tags else []

            resources.append(
                CloudResource(
                    {
                        "provider": "azure",
                        "service_type": "storage",
                        "service_name": "blob_storage",
                        "region": account.location,
                        "resource_id": account.name,
                        "cost": 0.0,  # TODO: Cost Management API
                        "is_idle": False,
                        "is_public": is_public,
                        "has_encryption": has_enc,
                        "has_access_control": not is_public,
                        "tags": tags,
                        "schema_hint": [],
                    }
                )
            )

        log.debug("real_azure_storage", count=len(resources))
        return resources

    # ── SQL Databases ─────────────────────────────────────────────────────────

    def _get_sql_databases(self) -> list[CloudResource]:
        resources = []
        for server in self._sql.servers.list():
            rg = server.id.split("/resourceGroups/")[1].split("/")[0]
            for db in self._sql.databases.list_by_server(rg, server.name):
                if db.name == "master":
                    continue
                tags = list(db.tags.values()) if db.tags else []

                resources.append(
                    CloudResource(
                        {
                            "provider": "azure",
                            "service_type": "database",
                            "service_name": "sql_database",
                            "region": db.location,
                            "resource_id": db.name,
                            "cost": 0.0,  # TODO: Cost Management API
                            "is_idle": db.status != "Online",
                            "is_public": False,  # Azure SQL não é público por padrão
                            "has_encryption": True,  # TDE ativo por padrão no Azure SQL
                            "has_access_control": self._sql_has_firewall(server, rg),
                            "tags": tags,
                            "schema_hint": [],
                        }
                    )
                )

        log.debug("real_azure_sql", count=len(resources))
        return resources

    # ── Helpers ───────────────────────────────────────────────────────────────

    def _get_vm_status(self, vm: Any) -> str:
        try:
            rg = vm.id.split("/resourceGroups/")[1].split("/")[0]
            iview = self._compute.virtual_machines.instance_view(rg, vm.name)
            for s in iview.statuses:
                if s.code.startswith("PowerState/"):
                    return s.code.split("/")[1].lower()
        except Exception:
            pass
        return "unknown"

    def _vm_has_encryption(self, vm: Any) -> bool:
        try:
            return vm.storage_profile.os_disk.encryption_settings is not None
        except Exception:
            return False

    def _sql_has_firewall(self, server: Any, resource_group: str) -> bool:
        try:
            rules = list(
                self._sql.firewall_rules.list_by_server(resource_group, server.name)
            )
            return len(rules) > 0
        except Exception:
            return False
