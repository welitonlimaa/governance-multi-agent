"""
Sistema multi-agent de governança.

Fluxo:
  1. Parse do arquivo .md  -> extrai dados de FinOps, Governança e Cultura
  2. Cloud providers       -> mock (padrão) ou real via CLOUD_*_MODE
  3. LLM provider          -> OpenAI (padrão) ou mock via LLM_PROVIDER
  4. LangGraph             -> Planner -> Executors (paralelo) -> Analyzer
  5. Persistência          -> S3 simulado (filesystem local)
  6. Console               -> sumário executivo formatado

Uso:
  python main.py
  python main.py --file outro_arquivo.md

Troca para APIs reais (exemplo AWS):
  CLOUD_AWS_MODE=real python main.py

Modo offline sem API key:
  LLM_PROVIDER=mock python main.py
"""

from __future__ import annotations

import argparse
import sys
import time
from uuid import uuid4

from config import (
    INPUT_FILE,
    LLM_PROVIDER,
    CLOUD_AWS_MODE,
    CLOUD_GCP_MODE,
    CLOUD_AZURE_MODE,
)
from logger import get_logger, setup_logging
from parser.md_parser import parse
from providers import get_llm_provider
from providers.cloud import get_cloud_providers
from orchestration.graph import get_graph
from storage.report_writer import persist_report, print_summary

setup_logging()
log = get_logger("main")


def parse_args() -> argparse.Namespace:
    p = argparse.ArgumentParser(
        description="Sistema Multi-Agent de Governança (FinOps + LGPD + Cultura)"
    )
    p.add_argument(
        "--file",
        "-f",
        default=INPUT_FILE,
        help="Arquivo .md com mocks estruturados (default: %(default)s)",
    )
    p.add_argument(
        "--execution-id",
        default=None,
        help="ID de execução customizado (default: UUID)",
    )
    return p.parse_args()


def print_boot_info(execution_id: str, filepath: str) -> None:
    """Exibe configuração ativa no início da execução."""
    mode_aws = f"{'🔴 real' if CLOUD_AWS_MODE   == 'real' else '🟡 mock'}"
    mode_gcp = f"{'🔴 real' if CLOUD_GCP_MODE   == 'real' else '🟡 mock'}"
    mode_azure = f"{'🔴 real' if CLOUD_AZURE_MODE == 'real' else '🟡 mock'}"
    mode_llm = f"{'🔴 openai' if LLM_PROVIDER == 'openai' else '🟡 mock'}"

    print(f"""
╔══════════════════════════════════════════════════════════════╗
║       SISTEMA MULTI-AGENT DE GOVERNANÇA CLOUD                ║
╚══════════════════════════════════════════════════════════════╝
  Execução ID : {execution_id}
  Arquivo     : {filepath}
  LLM         : {mode_llm}
  AWS         : {mode_aws}
  GCP         : {mode_gcp}
  Azure       : {mode_azure}
""")


def main() -> int:
    args = parse_args()
    execution_id = args.execution_id or str(uuid4())[:8]
    print_boot_info(execution_id, args.file)
    start = time.perf_counter()

    # Parse do arquivo .md
    try:
        parsed = parse(args.file)
    except FileNotFoundError:
        print(f"Error:  Arquivo não encontrado: {args.file}")
        print("Copie o .md para o diretório do projeto ou use --file <caminho>")
        return 1
    except Exception as exc:
        log.error("parse_failed", error=str(exc))
        print(f"Error:  Erro ao parsear arquivo: {exc}")
        return 1

    # Cloud providers
    print("Inicializando cloud providers...")
    try:
        cloud_providers = get_cloud_providers()
        print(
            f" {len(cloud_providers)} provider(s) ativo(s): "
            f"{', '.join(p.provider_name() for p in cloud_providers)}"
        )
    except Exception as exc:
        log.error("cloud_providers_failed", error=str(exc))
        print(f"Error:  Erro ao inicializar cloud providers: {exc}")
        return 1

    # LLM provider
    print("Inicializando LLM provider...")
    try:
        llm_provider = get_llm_provider()
        print(f"Provider: {llm_provider.name()}")
    except EnvironmentError as exc:
        print(f"Error:  {exc}")
        return 1
    except Exception as exc:
        log.error("llm_provider_failed", error=str(exc))
        print(f"Error:  Erro ao inicializar LLM: {exc}")
        return 1

    # Execução do LangGraph
    print("\nExecutando fluxo LangGraph...")
    print("  Planner -> [FinOps | DataGovernance | Cultura] -> Analyzer\n")

    graph = get_graph()
    initial_state = {
        "cloud_providers": cloud_providers,
        "cultura_text": parsed,
        "llm_provider": llm_provider,
        "execution_id": execution_id,
        "errors": [],
    }

    try:
        final_state = graph.invoke(initial_state)
    except Exception as exc:
        log.error("graph_failed", error=str(exc))
        print(f"\nError:  Erro na execução do grafo: {exc}")
        import traceback

        traceback.print_exc()
        return 1

    elapsed = time.perf_counter() - start

    # Persistência
    try:
        uri = persist_report(execution_id, dict(final_state))
        print(f"Relatório salvo em: {uri}")
    except Exception as exc:
        log.warning("report_save_failed", error=str(exc))
        print(f"Não foi possível salvar relatório: {exc}")

    # Sumário no console
    print_summary(dict(final_state))

    errors = final_state.get("errors", [])
    if errors:
        print(f"{len(errors)} erro(s) durante execução (ver relatório completo)")

    print(f"Concluído em {elapsed:.2f}s  |  ID: {execution_id}\n")
    return 0


if __name__ == "__main__":
    sys.exit(main())
