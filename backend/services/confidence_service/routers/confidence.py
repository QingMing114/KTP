"""Confidence evaluation routes."""

from __future__ import annotations

from fastapi import APIRouter, Depends, Request

from services.confidence_service.schemas import ConfidenceRequest, ConfidenceResponse
from services.confidence_service.service import ConfidenceService

router = APIRouter(tags=["confidence"])


async def get_confidence_service(request: Request) -> ConfidenceService:
    """Return the application-scoped confidence service."""
    return request.app.state.confidence_service


@router.post(
    "/confidence/evaluate",
    response_model=ConfidenceResponse,
    summary="Evaluate workflow confidence",
)
async def evaluate_confidence(
    request: ConfidenceRequest,
    service: ConfidenceService = Depends(get_confidence_service),
) -> ConfidenceResponse:
    """Evaluate and fuse workflow confidence signals."""
    return service.evaluate(request)
