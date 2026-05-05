"""
Entrypoint do sistema multi-agent de governança.

Suporta dois orquestradores, selecionáveis via ORCHESTRATOR no .env:

  ORCHESTRATOR=langgraph       (padrão)
    -> LangGraph StateGraph com paralelismo declarativo
    -> Ideal para desenvolvimento local rápido

  ORCHESTRATOR=step_functions
    -> LambdaRuntime + StepFunctionsRuntime simulados localmente
    -> Simula fidelmente a arquitetura AWS Lambda + Step Functions
    -> Pronto para migração: cada Lambda vira uma função AWS real

Ambos os orquestradores retornam o mesmo dict de estado final —
report_writer, console summary e storage funcionam sem alteração.

Uso:
  python main.py
  python main.py --file outro_arquivo.md
  python main.py --orchestrator step_functions

Troca via env var (sem alterar código):
  ORCHESTRATOR=step_functions python main.py
  CLOUD_AWS_MODE=real python main.py
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
    ORCHESTRATOR,
    CLOUD_AWS_MODE,
    CLOUD_GCP_MODE,
    CLOUD_AZURE_MODE,
)
from logger import get_logger, setup_logging
from parser.md_parser import parse
from providers import get_llm_provider
from providers.cloud import get_cloud_providers
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
        "--orchestrator",
        "-o",
        default=None,
        choices=["langgraph", "step_functions"],
        help="Orquestrador a usar (default: valor de ORCHESTRATOR no .env)",
    )
    p.add_argument(
        "--execution-id",
        default=None,
        help="ID de execução customizado (default: UUID curto)",
    )
    return p.parse_args()


def print_boot_info(orchestrator: str, execution_id: str, filepath: str) -> None:
    orch_label = {
        "langgraph": "🔷 langgraph       (StateGraph + paralelismo declarativo)",
        "step_functions": "🔶 step_functions  (LambdaRuntime + StepFunctionsRuntime local)",
    }.get(orchestrator, orchestrator)

    mode = lambda m, label: f"{'🔴 real' if m == 'real' else '🟡 mock'} {label}"

    print(f"""
╔══════════════════════════════════════════════════════════════╗
║       SISTEMA MULTI-AGENT DE GOVERNANÇA CLOUD                ║
╚══════════════════════════════════════════════════════════════╝
  Execução ID  : {execution_id}
  Arquivo      : {filepath}
  Orquestrador : {orch_label}
  LLM          : {'🔴 openai' if LLM_PROVIDER == 'openai' else '🟡 mock'}
  AWS          : {mode(CLOUD_AWS_MODE, '')}
  GCP          : {mode(CLOUD_GCP_MODE, '')}
  Azure        : {mode(CLOUD_AZURE_MODE, '')}
""")


def run_langgraph(
    cloud_providers: list,
    cultura_text: str,
    llm_provider,
    execution_id: str,
) -> dict:
    """Executa o pipeline via LangGraph StateGraph."""
    from orchestration.graph import get_graph

    graph = get_graph()
    initial_state = {
        "cloud_providers": cloud_providers,
        "cultura_text": cultura_text,
        "llm_provider": llm_provider,
        "execution_id": execution_id,
        "errors": [],
    }
    return dict(graph.invoke(initial_state))


def run_step_functions(
    cloud_providers: list,
    cultura_text: str,
    llm_provider,
    execution_id: str,
) -> dict:
    """
    Executa o pipeline via LambdaRuntime + StepFunctionsRuntime local.

    Cada agente roda como uma função Lambda isolada (com retry e timeout).
    O StepFunctionsRuntime orquestra os states sequencialmente, com
    paralelismo no step dos executors e routing condicional via filter_by.
    """
    from orchestration.sf_orchestrator import run as sf_run

    return sf_run(
        cloud_providers=cloud_providers,
        cultura_text=cultura_text,
        llm_provider=llm_provider,
        execution_id=execution_id,
    )


def main() -> int:
    args = parse_args()

    # CLI tem precedência sobre env var
    orchestrator = args.orchestrator or ORCHESTRATOR
    execution_id = args.execution_id or str(uuid4())[:8]

    print_boot_info(orchestrator, execution_id, args.file)
    start = time.perf_counter()

    # Parse do arquivo .md
    try:
        parsed = parse(args.file)
    except FileNotFoundError:
        print(f"Error:  Arquivo não encontrado: {args.file}")
        return 1
    except Exception as exc:
        log.error("parse_failed", error=str(exc))
        print(f"Error:  Erro ao parsear: {exc}")
        return 1

    # Cloud providers
    print("Inicializando cloud providers...")
    try:
        cloud_providers = get_cloud_providers()
        names = ", ".join(p.provider_name() for p in cloud_providers)
        print(f"   {len(cloud_providers)} provider(s) ativo(s): {names}")
    except Exception as exc:
        print(f"Error:  Erro ao inicializar cloud providers: {exc}")
        return 1

    # LLM provider
    print("Inicializando LLM provider...")
    try:
        llm_provider = get_llm_provider()
        print(f"  Provider: {llm_provider.name()}")
    except EnvironmentError as exc:
        print(f"Error:  {exc}")
        return 1
    except Exception as exc:
        print(f"Error:  Erro ao inicializar LLM: {exc}")
        return 1

    # Execução do orquestrador
    if orchestrator == "step_functions":
        print("\n-->  Executando via Step Functions (Lambda + Step Functions local)...")
        print("    Planner -> [FinOps ∥ DataGovernance ∥ Cultura] -> Analyzer\n")
        runner = run_step_functions
    else:
        print("\n-->  Executando via LangGraph (StateGraph local)...")
        print("    Planner -> [FinOps ∥ DataGovernance ∥ Cultura] -> Analyzer\n")
        runner = run_langgraph

    try:
        final_state = runner(
            cloud_providers=cloud_providers,
            cultura_text=parsed,
            llm_provider=llm_provider,
            execution_id=execution_id,
        )
    except Exception as exc:
        log.error("orchestrator_failed", error=str(exc))
        print(f"\nError:  Erro na execução: {exc}")
        import traceback

        traceback.print_exc()
        return 1

    elapsed = time.perf_counter() - start

    # Persistência
    try:
        uri = persist_report(execution_id, final_state)
        print(f"Relatório salvo em: {uri}")
    except Exception as exc:
        log.warning("report_save_failed", error=str(exc))
        print(f"Warning: Não foi possível salvar relatório: {exc}")

    # Sumário no console
    print_summary(final_state)

    errors = final_state.get("errors", [])
    if errors:
        print(f"Warning: {len(errors)} erro(s) durante execução:")
        for e in errors:
            print(f" - {e}")

    skipped = final_state.get("skipped_agents", [])
    if skipped:
        print(f"Agentes ignorados pelo Planner: {', '.join(skipped)}")

    print(
        f"\nConcluído em {elapsed:.2f}s  |  Orquestrador: {orchestrator}  |  ID: {execution_id}\n"
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
