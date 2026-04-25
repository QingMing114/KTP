"""Query routes for the RAG service."""

from __future__ import annotations

from fastapi import APIRouter, Depends, Request

from services.rag_service.schemas import RAGQueryRequest, RAGQueryResponse
from services.rag_service.service import RAGService

router = APIRouter(tags=["query"])


async def get_rag_service(request: Request) -> RAGService:
    """Return the application-scoped RAG service instance."""
    return request.app.state.rag_service


@router.post("/query", response_model=RAGQueryResponse, summary="Query the RAG service")
async def run_query(
    request: RAGQueryRequest,
    service: RAGService = Depends(get_rag_service),
) -> RAGQueryResponse:
    """Run retrieval for a structured RAG request."""
    return service.query(request)
