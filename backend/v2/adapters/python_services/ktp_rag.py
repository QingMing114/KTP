from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from services.rag_service.client import RAGServiceClientError
from shared.schemas.service_results import RagServiceResult


@dataclass(slots=True)
class KtpKnowledgeAdapter:
    """Bridge V2 runtime tools into the existing KTP RAG service."""

    client: Any

    def retrieve_knowledge(
        self,
        *,
        query: str,
        top_k: int = 3,
    ) -> RagServiceResult:
        return self.client.run_rag(
            request_id=None,
            user_query=query,
            task_type=None,
            region=None,
            crop_type=None,
            top_k=top_k,
        )


class _UnavailableRagClient:
    """Raise an explicit error when the real RAG dependency chain is unavailable."""

    def run_rag(
        self,
        *,
        request_id: str | None,
        user_query: str,
        task_type: str | None,
        region: str | None,
        crop_type: str | None,
        inference_result: dict | None = None,
        context: dict | None = None,
        top_k: int | None = None,
    ) -> RagServiceResult:
        del request_id, user_query, task_type, region, crop_type, inference_result, context, top_k
        raise RAGServiceClientError(
            "KTP knowledge adapter is unavailable because the local RAG dependency chain could not be loaded."
        )


def build_default_ktp_knowledge_adapter() -> KtpKnowledgeAdapter:
    try:
        from services.rag_service.client import LocalRAGServiceClient

        return KtpKnowledgeAdapter(client=LocalRAGServiceClient())
    except ModuleNotFoundError:
        return KtpKnowledgeAdapter(client=_UnavailableRagClient())
