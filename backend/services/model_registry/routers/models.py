"""Model routes for the model registry service."""

from __future__ import annotations

from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from services.model_registry.db import get_db
from services.model_registry.repository import ModelRegistryRepository
from services.model_registry.schemas import (
    ModelListResponse,
    ModelLookupResponse,
    ModelRegisterRequest,
    ModelResponse,
    ModelStatus,
    ModelStatusUpdateRequest,
)
from services.model_registry.service import ModelRegistryService

router = APIRouter(prefix="/models", tags=["models"])


async def get_model_registry_service(
    db: Session = Depends(get_db),
) -> ModelRegistryService:
    """Provide a request-scoped model registry service."""
    return ModelRegistryService(ModelRegistryRepository(db))


@router.post("", response_model=ModelResponse, status_code=201, summary="Register model")
async def register_model(
    request: ModelRegisterRequest,
    service: ModelRegistryService = Depends(get_model_registry_service),
) -> ModelResponse:
    """Register a new model."""
    return service.register_model(request)


@router.get("/lookup", response_model=ModelLookupResponse, summary="Lookup latest ready model")
async def lookup_model(
    region: str,
    crop_type: str,
    task_type: str,
    service: ModelRegistryService = Depends(get_model_registry_service),
) -> ModelLookupResponse:
    """Lookup the latest ready model for a region/crop/task combination."""
    return service.lookup_model(region=region, crop_type=crop_type, task_type=task_type)


@router.get("/{model_id}", response_model=ModelResponse, summary="Get model by id")
async def get_model(
    model_id: int,
    service: ModelRegistryService = Depends(get_model_registry_service),
) -> ModelResponse:
    """Get a registered model by identifier."""
    return service.get_model_by_id(model_id)


@router.patch(
    "/{model_id}/status",
    response_model=ModelResponse,
    summary="Update model status",
)
async def update_model_status(
    model_id: int,
    request: ModelStatusUpdateRequest,
    service: ModelRegistryService = Depends(get_model_registry_service),
) -> ModelResponse:
    """Update the lifecycle status of a registered model."""
    return service.set_model_status(model_id, request)


@router.get("", response_model=ModelListResponse, summary="List models")
async def list_models(
    region: str | None = None,
    crop_type: str | None = None,
    task_type: str | None = None,
    status: ModelStatus | None = None,
    service: ModelRegistryService = Depends(get_model_registry_service),
) -> ModelListResponse:
    """List registered models with basic filters."""
    return service.list_registered_models(
        region=region,
        crop_type=crop_type,
        task_type=task_type,
        status=status,
    )
