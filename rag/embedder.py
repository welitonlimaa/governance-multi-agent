from __future__ import annotations

from typing import Any

import numpy as np

from config import EMBEDDING_MODEL
from logger import get_logger

log = get_logger("embedder")


class LocalEmbedder:
    """
    Wrapper sobre sentence-transformers para geração de embeddings.
    Modelo padrão: all-MiniLM-L6-v2 (384 dims, ~80MB)
    """

    def __init__(self, model_name: str = EMBEDDING_MODEL) -> None:
        log.info("embedder_loading", model=model_name)
        try:
            from sentence_transformers import SentenceTransformer

            self._model = SentenceTransformer(model_name)
            self._dim = self._model.get_sentence_embedding_dimension()
            log.info("embedder_ready", model=model_name, dim=self._dim)
        except ImportError:
            raise ImportError(
                "sentence-transformers not installed. "
                "Run: pip install sentence-transformers"
            )

    @property
    def dim(self) -> int:
        return self._dim

    def embed(self, text: str) -> np.ndarray:
        """Gera embedding de um único texto."""
        vec: np.ndarray = self._model.encode(text, normalize_embeddings=True)
        return vec

    def embed_batch(self, texts: list[str]) -> np.ndarray:
        """Gera embeddings em lote (mais eficiente)."""
        vecs: np.ndarray = self._model.encode(
            texts, normalize_embeddings=True, batch_size=32
        )
        return vecs
