"""
providers/__init__.py
Factory do provider LLM.

LLM_PROVIDER=openai  -> OpenAIProvider  (padrão — requer OPENAI_API_KEY)
LLM_PROVIDER=mock    -> MockLLMProvider (fallback offline, sem API key)

O provider de LLM é usado SOMENTE para narrativa e correlação.
Nenhum agente usa LLM para cálculo de valores ou classificação de risco.
"""

from config import LLM_PROVIDER, OPENAI_API_KEY
from providers.base import LLMProvider
from logger import get_logger

log = get_logger("llm_factory")


def get_llm_provider() -> LLMProvider:
    """
    Instancia e retorna o provider LLM conforme LLM_PROVIDER no .env.
    Levanta erro claro se OpenAI for solicitado sem API key configurada.
    """
    if LLM_PROVIDER == "mock":
        log.info("llm_provider", mode="mock")
        from providers.mock_provider import MockLLMProvider

        return MockLLMProvider()

    # OpenAI (padrão)
    if not OPENAI_API_KEY:
        raise EnvironmentError(
            "OPENAI_API_KEY não encontrada.\n"
            "  -> Defina OPENAI_API_KEY=sk-... no arquivo .env\n"
            "  -> Ou use modo offline: LLM_PROVIDER=mock"
        )
    log.info("llm_provider", mode="openai", model_hint="see OPENAI_MODEL")
    from providers.openai_provider import OpenAIProvider

    return OpenAIProvider()
