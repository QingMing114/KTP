"""Stable mock embedding provider used for local RAG runs."""

from __future__ import annotations

import hashlib

import numpy as np

from services.rag_service.embeddings.base import BaseEmbeddingProvider


class MockEmbeddingProvider(BaseEmbeddingProvider):
    """Generate deterministic embeddings without external model downloads."""

    def __init__(self, dimension: int = 128) -> None:
        super().__init__(dimension=dimension)

    def embed_texts(self, texts: list[str]) -> np.ndarray:
        """Embed a batch of texts deterministically."""
        if not texts:
            return np.zeros((0, self.dimension), dtype=np.float32)
        return np.vstack([self._embed_single(text) for text in texts]).astype(np.float32)

    def embed_query(self, text: str) -> np.ndarray:
        """Embed a single query deterministically."""
        return self._embed_single(text).astype(np.float32)

    def _embed_single(self, text: str) -> np.ndarray:
        normalized = text.strip().lower().encode("utf-8")
        values = np.empty(self.dimension, dtype=np.float32)
        filled = 0
        counter = 0
        while filled < self.dimension:
            digest = hashlib.sha256(normalized + counter.to_bytes(4, "little")).digest()
            digest_values = np.frombuffer(digest, dtype=np.uint8).astype(np.float32)
            scaled = (digest_values / 127.5) - 1.0
            take = min(self.dimension - filled, scaled.shape[0])
            values[filled : filled + take] = scaled[:take]
            filled += take
            counter += 1
        return values
