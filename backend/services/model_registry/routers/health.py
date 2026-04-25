"""Health routes for the model registry service."""

from __future__ import annotations

from fastapi import APIRouter

from shared.config.settings import get_settings
from shared.schemas.common import HealthResponse

router = APIRouter(tags=["health"])


@router.get("/health", response_model=HealthResponse, summary="Service health check")
async def health_check() -> HealthResponse:
    """Return health information for the model registry service."""
    settings = get_settings()
    return HealthResponse(
        service="model-registry",
        status="ok",
        environment=settings.app_env,
        checks={"database": "configured"},
    )
