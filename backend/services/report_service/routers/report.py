"""Report generation routes."""

from __future__ import annotations

from fastapi import APIRouter, Depends, Request

from services.report_service.schemas import ReportRequest, ReportResponse
from services.report_service.service import ReportService

router = APIRouter(tags=["report"])


async def get_report_service(request: Request) -> ReportService:
    """Return the application-scoped report service."""
    return request.app.state.report_service


@router.post(
    "/report/generate",
    response_model=ReportResponse,
    summary="Generate an HTML report",
)
async def generate_report(
    request: ReportRequest,
    service: ReportService = Depends(get_report_service),
) -> ReportResponse:
    """Generate an HTML report from structured workflow data."""
    return service.generate_report(request)
