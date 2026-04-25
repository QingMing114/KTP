"""Health routes for the inference service."""

from __future__ import annotations

from fastapi import APIRouter, Request

from shared.config.settings import get_settings
from shared.schemas.common import HealthResponse

router = APIRouter(tags=["health"])


@router.get("/health", response_model=HealthResponse, summary="Service health check")
async def health_check(request: Request) -> HealthResponse:
    """Return the current health view for the inference service."""
    settings = get_settings()
    config = request.app.state.inference_config
    return HealthResponse(
        service=config.inference_service_name,
        status="ok",
        environment=settings.app_env,
        checks={
            "model_registry": "configured",
            "mask_output_dir": "configured",
        },
    )
