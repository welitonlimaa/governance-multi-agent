"""
rag/vector_store.py
Vector store local usando FAISS.
Persiste índice e metadados em disco (VECTOR_DB_PATH).
"""
from __future__ import annotations

import json
import pickle
from pathlib import Path
from typing import Any

import numpy as np

from config import VECTOR_DB_PATH
from logger import get_logger

log = get_logger("vector_store")

INDEX_FILE = VECTOR_DB_PATH / "faiss.index"
META_FILE = VECTOR_DB_PATH / "metadata.pkl"


class FAISSVectorStore:
    """
    Armazena e recupera documentos por similaridade coseno.
    Interface: add_documents, query, persist, load.
    """

    def __init__(self, dim: int) -> None:
        try:
            import faiss
        except ImportError:
            raise ImportError("faiss-cpu not installed. Run: pip install faiss-cpu")

        import faiss as _faiss

        self._faiss = _faiss
        self.dim = dim
        self._index = _faiss.IndexFlatIP(dim)  # Inner Product = cosine (com embeddings normalizados)
        self._documents: list[str] = []
        self._metadata: list[dict[str, Any]] = []
        log.info("vector_store_init", dim=dim)

    def add_documents(
        self,
        texts: list[str],
        embeddings: np.ndarray,
        metadata: list[dict[str, Any]] | None = None,
    ) -> None:
        """Adiciona documentos ao índice."""
        if len(texts) == 0:
            return
        meta = metadata or [{} for _ in texts]
        self._index.add(embeddings.astype(np.float32))
        self._documents.extend(texts)
        self._metadata.extend(meta)
        log.info("vector_store_add", count=len(texts), total=self._index.ntotal)

    def query(
        self, query_embedding: np.ndarray, top_k: int = 3
    ) -> list[dict[str, Any]]:
        """Retorna top_k documentos mais similares."""
        if self._index.ntotal == 0:
            log.warning("vector_store_empty_query")
            return []

        k = min(top_k, self._index.ntotal)
        vec = query_embedding.astype(np.float32).reshape(1, -1)
        distances, indices = self._index.search(vec, k)

        results = []
        for dist, idx in zip(distances[0], indices[0]):
            if idx == -1:
                continue
            results.append({
                "text": self._documents[idx],
                "score": float(dist),
                "metadata": self._metadata[idx],
            })
        return results

    def persist(self) -> None:
        """Salva índice e metadados em disco."""
        VECTOR_DB_PATH.mkdir(parents=True, exist_ok=True)
        self._faiss.write_index(self._index, str(INDEX_FILE))
        with open(META_FILE, "wb") as f:
            pickle.dump({"documents": self._documents, "metadata": self._metadata}, f)
        log.info("vector_store_persisted", path=str(VECTOR_DB_PATH))

    def load(self) -> bool:
        """Carrega índice do disco. Retorna True se bem-sucedido."""
        if not INDEX_FILE.exists() or not META_FILE.exists():
            return False
        self._index = self._faiss.read_index(str(INDEX_FILE))
        with open(META_FILE, "rb") as f:
            data = pickle.load(f)
        self._documents = data["documents"]
        self._metadata = data["metadata"]
        log.info("vector_store_loaded", total=self._index.ntotal)
        return True


def chunk_text(text: str, chunk_size: int = 300, overlap: int = 50) -> list[str]:
    """
    Divide texto em chunks com overlap para melhor recall no RAG.
    """
    words = text.split()
    chunks: list[str] = []
    start = 0
    while start < len(words):
        end = min(start + chunk_size, len(words))
        chunks.append(" ".join(words[start:end]))
        start += chunk_size - overlap
    return [c for c in chunks if len(c.strip()) > 10]
