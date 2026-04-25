"""Health routes for the report service."""

from __future__ import annotations

from fastapi import APIRouter, Depends, Request

from services.report_service.service import ReportService
from shared.config.settings import get_settings
from shared.schemas.common import HealthResponse

router = APIRouter(tags=["health"])
settings = get_settings()


async def get_report_service(request: Request) -> ReportService:
    """Return the application-scoped report service."""
    return request.app.state.report_service


@router.get("/health", response_model=HealthResponse, summary="Report service health check")
async def health_check(
    request: Request,
    service: ReportService = Depends(get_report_service),
) -> HealthResponse:
    """Return the current health status for the report service."""
    return HealthResponse(
        service=request.app.state.report_config.report_service_name,
        status="ok",
        environment=settings.app_env,
        checks=service.get_health_snapshot(),
    )
