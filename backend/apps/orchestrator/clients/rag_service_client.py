"""Orchestrator client for RAG retrieval."""

from __future__ import annotations

from services.rag_service.client import LocalRAGServiceClient
from services.rag_service.config import RAGServiceConfig


class RAGServiceClient:
    """Thin orchestrator wrapper around the local RAG client."""

    def __init__(self, *, config: RAGServiceConfig) -> None:
        self._client = LocalRAGServiceClient(config=config)

    def run_rag(self, **kwargs):
        return self._client.run_rag(**kwargs)
