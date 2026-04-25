"""Routers for the inference service."""

from services.inference_service.routers.health import router as health_router
from services.inference_service.routers.inference import router as inference_router

__all__ = ["health_router", "inference_router"]
