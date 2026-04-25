"""Health routes for the visualization service."""

from __future__ import annotations

from fastapi import APIRouter, Depends, Request

from services.visualization_service.service import VisualizationService
from shared.config.settings import get_settings
from shared.schemas.common import HealthResponse

router = APIRouter(tags=["health"])
settings = get_settings()


async def get_visualization_service(request: Request) -> VisualizationService:
    """Return the application-scoped visualization service."""
    return request.app.state.visualization_service


@router.get(
    "/health",
    response_model=HealthResponse,
    summary="Visualization service health check",
)
async def health_check(
    request: Request,
    service: VisualizationService = Depends(get_visualization_service),
) -> HealthResponse:
    """Return the current health status for the visualization service."""
    return HealthResponse(
        service=request.app.state.visualization_config.visualization_service_name,
        status="ok",
        environment=settings.app_env,
        checks=service.get_health_snapshot(),
    )
