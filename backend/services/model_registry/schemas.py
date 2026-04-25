"""Pydantic schemas for the model registry service."""

from __future__ import annotations

from datetime import datetime
from enum import Enum
from typing import Any

from pydantic import ConfigDict, Field

from shared.schemas.common import BaseSchema


class ModelStatus(str, Enum):
    """Lifecycle status for registered models."""

    TRAINING = "training"
    READY = "ready"
    FAILED = "failed"
    DEPRECATED = "deprecated"


class ModelRegisterRequest(BaseSchema):
    """Request payload for registering a new model."""

    region: str = Field(..., description="Target region identifier.")
    crop_type: str = Field(..., description="Target crop type.")
    task_type: str = Field(..., description="Target task type.")
    model_name: str = Field(..., description="Model family or name.")
    model_version: str = Field(..., description="Model version string.")
    artifact_uri: str = Field(..., description="Artifact storage URI.")
    metrics_json: dict[str, Any] | None = Field(
        default=None,
        description="Evaluation metrics payload.",
    )
    status: ModelStatus = Field(
        default=ModelStatus.TRAINING,
        description="Initial model lifecycle status.",
    )
    description: str | None = Field(default=None, description="Optional description.")


class ModelStatusUpdateRequest(BaseSchema):
    """Request payload for updating a model lifecycle status."""

    status: ModelStatus = Field(..., description="New lifecycle status.")


class ModelResponse(BaseSchema):
    """Canonical response payload for a registered model."""

    model_config = ConfigDict(from_attributes=True, extra="forbid")

    id: int = Field(..., description="Primary key.")
    region: str = Field(..., description="Target region identifier.")
    crop_type: str = Field(..., description="Target crop type.")
    task_type: str = Field(..., description="Target task type.")
    model_name: str = Field(..., description="Model family or name.")
    model_version: str = Field(..., description="Model version string.")
    artifact_uri: str = Field(..., description="Artifact storage URI.")
    metrics_json: dict[str, Any] | None = Field(
        default=None,
        description="Evaluation metrics payload.",
    )
    status: ModelStatus = Field(..., description="Current model lifecycle status.")
    description: str | None = Field(default=None, description="Optional description.")
    created_at: datetime = Field(..., description="Creation timestamp.")
    updated_at: datetime = Field(..., description="Last update timestamp.")


class ModelListResponse(BaseSchema):
    """Response payload for listing registered models."""

    total: int = Field(..., description="Number of returned models.")
    items: list[ModelResponse] = Field(
        default_factory=list,
        description="Registered models matching the filter.",
    )


class ModelLookupResponse(BaseSchema):
    """Lookup response designed for future orchestrator integration."""

    model_exists: bool = Field(..., description="Whether a ready model exists.")
    model_id: int | None = Field(default=None, description="Resolved model identifier.")
    model_name: str | None = Field(default=None, description="Resolved model name.")
    model_version: str | None = Field(default=None, description="Resolved version.")
    artifact_uri: str | None = Field(default=None, description="Resolved artifact URI.")
    metrics_json: dict[str, Any] | None = Field(
        default=None,
        description="Resolved model metadata payload.",
    )
    status: ModelStatus | None = Field(default=None, description="Resolved model status.")
    description: str | None = Field(default=None, description="Resolved model description.")
    reason: str | None = Field(default=None, description="Reason when no model is available.")
