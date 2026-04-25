"""Health routes for the RAG service."""

from __future__ import annotations

from fastapi import APIRouter, Depends, Request

from services.rag_service.service import RAGService
from shared.config.settings import get_settings
from shared.schemas.common import HealthResponse

router = APIRouter(tags=["health"])
settings = get_settings()


async def get_rag_service(request: Request) -> RAGService:
    """Return the application-scoped RAG service instance."""
    return request.app.state.rag_service


@router.get("/health", response_model=HealthResponse, summary="RAG service health check")
async def health_check(
    request: Request,
    service: RAGService = Depends(get_rag_service),
) -> HealthResponse:
    """Return the current health snapshot for the RAG service."""
    return HealthResponse(
        service=request.app.state.rag_config.rag_service_name,
        status="ok",
        environment=settings.app_env,
        checks=service.get_health_snapshot(),
    )
