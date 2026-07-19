"""Local orchestrator client for the RAG service."""

from __future__ import annotations

import logging
from typing import Any
from uuid import uuid4

from services.rag_service.config import RAGServiceConfig, get_rag_service_config
from services.rag_service.schemas import RAGQueryRequest, RetrievedChunk
from shared.schemas.service_results import RagServiceResult

logger = logging.getLogger(__name__)


class RAGServiceClientError(Exception):
    """Raised when local RAG execution cannot be completed."""


class LocalRAGServiceClient:
    """Run the local RAG service from orchestrator synchronous code."""

    def __init__(
        self,
        *,
        config: RAGServiceConfig | None = None,
        service: Any | None = None,
    ) -> None:
        self._config = config or get_rag_service_config()
        if service is None:
            from services.rag_service.service import RAGService

            self._service = RAGService(config=self._config)
        else:
            self._service = service

    def run_rag(
        self,
        *,
        request_id: str | None,
        user_query: str,
        task_type: str | None,
        region: str | None,
        crop_type: str | None,
        inference_result: dict | None = None,
        context: dict[str, Any] | None = None,
        top_k: int | None = None,
    ) -> RagServiceResult:
        """Run structured retrieval and normalize the result for orchestrator use."""
        logger.info(
            "local_rag_execution_started | request_id=%s | task_type=%s | region=%s | crop_type=%s",
            request_id,
            task_type,
            region,
            crop_type,
        )
        query_request = RAGQueryRequest(
            request_id=request_id or str(uuid4()),
            query=user_query,
            top_k=top_k,
            task_type=task_type,
            region=region,
            crop_type=crop_type,
            context={
                **(context or {}),
                "inference_result": inference_result or {},
            },
        )
        response = self._service.query(query_request)
        if not response.success:
            raise RAGServiceClientError(response.message)

        results_payload = [result.model_dump() for result in response.results]
        sources = list(dict.fromkeys(result.source for result in response.results))
        summary = self._build_summary(response.results)
        logger.info(
            "local_rag_execution_succeeded | request_id=%s | result_count=%s",
            query_request.request_id,
            len(response.results),
        )
        return RagServiceResult(
            query=response.query,
            summary=summary,
            sources=sources,
            top_k=len(response.results),
            results=results_payload,
        )

    def list_documents(self) -> list[dict[str, Any]]:
        return self._service.list_documents()

    def get_document(self, document_id: str) -> dict[str, Any] | None:
        return self._service.get_document(document_id)

    def delete_document(self, document_id: str) -> bool:
        return self._service.delete_document(document_id)

    def ingest_document(self, request: Any) -> Any:
        return self._service.ingest_document(request)

    def query(self, request: Any) -> Any:
        return self._service.query(request)

    @staticmethod
    def _build_summary(results: list[RetrievedChunk]) -> str:
        if not results:
            return "No relevant knowledge snippets were retrieved."
        snippets = [result.text for result in results[:3]]
        return " ".join(snippets)
