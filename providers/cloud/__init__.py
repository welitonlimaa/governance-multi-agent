"""
providers/cloud/__init__.py
Factory de cloud providers.

Retorna o provider correto (mock ou real) com base nas variáveis de ambiente:
  CLOUD_AWS_MODE   = "mock" | "real"
  CLOUD_GCP_MODE   = "mock" | "real"
  CLOUD_AZURE_MODE = "mock" | "real"

Os agentes dependem APENAS da interface CloudProvider.
A troca mock -> real é transparente — nenhum agente precisa ser alterado.

Uso:
    from providers.cloud import get_cloud_providers
    providers = get_cloud_providers()   # retorna [AWSProvider, GCPProvider, AzureProvider]
"""

from __future__ import annotations

from config import CLOUD_AWS_MODE, CLOUD_GCP_MODE, CLOUD_AZURE_MODE
from providers.cloud.base import CloudProvider
from logger import get_logger

log = get_logger("cloud_factory")

# ─── Mapeamento mode -> classe ──────────────────────────────────────────────────


def _build_aws() -> CloudProvider:
    if CLOUD_AWS_MODE == "real":
        log.info("cloud_provider_mode", provider="aws", mode="real")
        from providers.cloud.real_aws import RealAWSProvider

        return RealAWSProvider()
    log.info("cloud_provider_mode", provider="aws", mode="mock")
    from providers.cloud.mock_aws import MockAWSProvider

    return MockAWSProvider()


def _build_gcp() -> CloudProvider:
    if CLOUD_GCP_MODE == "real":
        log.info("cloud_provider_mode", provider="gcp", mode="real")
        from providers.cloud.real_gcp import RealGCPProvider

        return RealGCPProvider()
    log.info("cloud_provider_mode", provider="gcp", mode="mock")
    from providers.cloud.mock_gcp import MockGCPProvider

    return MockGCPProvider()


def _build_azure() -> CloudProvider:
    if CLOUD_AZURE_MODE == "real":
        log.info("cloud_provider_mode", provider="azure", mode="real")
        from providers.cloud.real_azure import RealAzureProvider

        return RealAzureProvider()
    log.info("cloud_provider_mode", provider="azure", mode="mock")
    from providers.cloud.mock_azure import MockAzureProvider

    return MockAzureProvider()


def get_cloud_providers() -> list[CloudProvider]:
    """
    Retorna lista de providers ativos conforme configuração.
    Falhas de inicialização de um provider são logadas mas não
    impedem o sistema de rodar com os providers restantes.
    """
    builders = {
        "aws": _build_aws,
        "gcp": _build_gcp,
        "azure": _build_azure,
    }
    providers: list[CloudProvider] = []
    for name, build_fn in builders.items():
        try:
            providers.append(build_fn())
        except Exception as exc:
            log.error("cloud_provider_init_failed", provider=name, error=str(exc))

    if not providers:
        raise RuntimeError(
            "Nenhum cloud provider disponível. "
            "Verifique as variáveis CLOUD_*_MODE e dependências instaladas."
        )
    return providers
