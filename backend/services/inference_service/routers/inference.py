"""Inference routes for the inference service."""

from __future__ import annotations

from fastapi import APIRouter, Depends, Request

from services.inference_service.schemas import InferenceRequest, InferenceResponse
from services.inference_service.service import InferenceService

router = APIRouter(tags=["inference"])


async def get_inference_service(request: Request) -> InferenceService:
    """Return the application-scoped inference service instance."""
    return request.app.state.inference_service


@router.post("/infer", response_model=InferenceResponse, summary="Run inference")
async def run_inference(
    request: InferenceRequest,
    service: InferenceService = Depends(get_inference_service),
) -> InferenceResponse:
    """Run the bounded inference chain for the given request."""
    return await service.run_inference(request)
