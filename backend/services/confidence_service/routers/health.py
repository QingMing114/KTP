"""Health routes for the confidence service."""

from __future__ import annotations

from fastapi import APIRouter, Depends, Request

from services.confidence_service.service import ConfidenceService
from shared.config.settings import get_settings
from shared.schemas.common import HealthResponse

router = APIRouter(tags=["health"])
settings = get_settings()


async def get_confidence_service(request: Request) -> ConfidenceService:
    """Return the application-scoped confidence service."""
    return request.app.state.confidence_service


@router.get(
    "/health",
    response_model=HealthResponse,
    summary="Confidence service health check",
)
async def health_check(
    request: Request,
    service: ConfidenceService = Depends(get_confidence_service),
) -> HealthResponse:
    """Return the current health status for the confidence service."""
    return HealthResponse(
        service=request.app.state.confidence_config.confidence_service_name,
        status="ok",
        environment=settings.app_env,
        checks=service.get_health_snapshot(),
    )
