"""
Configuração central do sistema.
Carrega variáveis de ambiente e expõe constantes tipadas.

TROCA DE PROVIDER CLOUD:
  Cada provider pode ser "mock" ou "real" de forma independente.
  CLOUD_AWS_MODE=mock  -> MockAWSProvider   (default)
  CLOUD_AWS_MODE=real  -> RealAWSProvider   (requer boto3 + credenciais)
  Idem para GCP e AZURE.

TROCA DE PROVIDER LLM:
  LLM_PROVIDER=openai  -> OpenAIProvider    (default — requer OPENAI_API_KEY)
  LLM_PROVIDER=mock    -> MockLLMProvider   (fallback offline, sem API key)
"""

import os
from pathlib import Path
from dotenv import load_dotenv

load_dotenv()

# ── LLM ──────────────────────────────────────────────────────────────────────
LLM_PROVIDER: str = os.getenv("LLM_PROVIDER", "openai")
OPENAI_API_KEY: str = os.getenv("OPENAI_API_KEY", "")
OPENAI_MODEL: str = os.getenv("OPENAI_MODEL", "gpt-4o-mini")

# ── Orquestrador ──────────────────────────────────────────────────────────────
# "langgraph"      -> LangGraph (StateGraph + paralelismo declarativo)
# "step_functions" -> LambdaRuntime + StepFunctionsRuntime (simulação local de AWS)
ORCHESTRATOR: str = os.getenv("ORCHESTRATOR", "langgraph")

# ── Cloud provider mode (mock | real) ─────────────────────────────────────────
CLOUD_AWS_MODE: str = os.getenv("CLOUD_AWS_MODE", "mock")
CLOUD_GCP_MODE: str = os.getenv("CLOUD_GCP_MODE", "mock")
CLOUD_AZURE_MODE: str = os.getenv("CLOUD_AZURE_MODE", "mock")

# ── Storage ───────────────────────────────────────────────────────────────────
STORAGE_PATH: Path = Path(os.getenv("STORAGE_PATH", "./storage/reports"))
VECTOR_DB_PATH: Path = Path(os.getenv("VECTOR_DB_PATH", "./storage/vector_db"))

# ── Input ─────────────────────────────────────────────────────────────────────
INPUT_FILE: str = os.getenv("INPUT_FILE", "cultura.md")

# ── Logging ───────────────────────────────────────────────────────────────────
LOG_LEVEL: str = os.getenv("LOG_LEVEL", "INFO")

# ── Fault injection (0.0 = nunca, 1.0 = sempre) ───────────────────────────────
FAILURE_RATE: float = float(os.getenv("FAILURE_RATE", "0.0"))

# ── Embeddings (modelo local, sem API) ───────────────────────────────────────
EMBEDDING_MODEL: str = "all-MiniLM-L6-v2"

# ── Garantir existência dos diretórios ────────────────────────────────────────
STORAGE_PATH.mkdir(parents=True, exist_ok=True)
VECTOR_DB_PATH.mkdir(parents=True, exist_ok=True)
