"""Sentence-transformer embedding provider entrypoint."""

from __future__ import annotations

import logging

import numpy as np

from services.rag_service.embeddings.base import BaseEmbeddingProvider
from services.rag_service.embeddings.mock_embedding import MockEmbeddingProvider

logger = logging.getLogger(__name__)

try:  # pragma: no cover - optional dependency branch
    from sentence_transformers import SentenceTransformer
except Exception:  # pragma: no cover - optional dependency branch
    SentenceTransformer = None


class SentenceTransformerEmbeddingProvider(BaseEmbeddingProvider):
    """Embedding provider that uses sentence-transformers when available."""

    def __init__(self, model_name: str, dimension: int = 128) -> None:
        super().__init__(dimension=dimension)
        self._model_name = model_name
        self._fallback = MockEmbeddingProvider(dimension=dimension)
        self._model = None
        if SentenceTransformer is None:
            logger.warning(
                "sentence_transformers_unavailable | model_name=%s | fallback=mock_embedding",
                model_name,
            )
            return
        self._model = SentenceTransformer(model_name)

    def embed_texts(self, texts: list[str]) -> np.ndarray:
        """Embed texts using sentence-transformers or the deterministic fallback."""
        if self._model is None:
            return self._fallback.embed_texts(texts)
        return np.asarray(self._model.encode(texts), dtype=np.float32)

    def embed_query(self, text: str) -> np.ndarray:
        """Embed a query using sentence-transformers or the deterministic fallback."""
        if self._model is None:
            return self._fallback.embed_query(text)
        return np.asarray(self._model.encode([text])[0], dtype=np.float32)
