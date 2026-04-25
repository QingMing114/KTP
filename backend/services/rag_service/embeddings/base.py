"""Embedding provider abstractions."""

from __future__ import annotations

from abc import ABC, abstractmethod

import numpy as np


class BaseEmbeddingProvider(ABC):
    """Abstract base class for text embedding providers."""

    def __init__(self, dimension: int) -> None:
        self._dimension = dimension

    @property
    def dimension(self) -> int:
        """Return the configured embedding dimension."""
        return self._dimension

    @abstractmethod
    def embed_texts(self, texts: list[str]) -> np.ndarray:
        """Embed a batch of texts into a 2D numpy array."""

    @abstractmethod
    def embed_query(self, text: str) -> np.ndarray:
        """Embed a query into a 1D numpy array."""
