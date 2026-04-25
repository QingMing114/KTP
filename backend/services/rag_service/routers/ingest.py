"""Document ingestion routes for the RAG service."""

from __future__ import annotations

from fastapi import APIRouter, Depends, Request

from services.rag_service.schemas import DocumentIngestRequest, DocumentIngestResponse
from services.rag_service.service import RAGService

router = APIRouter(tags=["ingest"])


async def get_rag_service(request: Request) -> RAGService:
    """Return the application-scoped RAG service instance."""
    return request.app.state.rag_service


@router.post(
    "/documents/ingest",
    response_model=DocumentIngestResponse,
    summary="Ingest a domain document",
)
async def ingest_document(
    request: DocumentIngestRequest,
    service: RAGService = Depends(get_rag_service),
) -> DocumentIngestResponse:
    """Ingest a knowledge document into the local RAG store."""
    return service.ingest_document(request)
