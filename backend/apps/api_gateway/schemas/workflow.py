"""Schemas for workflow lookup and service health aggregation."""

from __future__ import annotations

from typing import Any

from pydantic import Field

from shared.schemas.common import BaseSchema


class WorkflowStatusResponse(BaseSchema):
    """Response payload for gateway workflow lookup."""

    request_id: str = Field(..., description="Workflow request identifier.")
    found: bool = Field(..., description="Whether the workflow result exists.")
    workflow_status: str | None = Field(default=None, description="Latest workflow status.")
    result: dict[str, Any] | None = Field(
        default=None,
        description="Stored workflow final state when available.",
    )
    message: str = Field(..., description="Human-readable lookup outcome.")


class ServiceHealthResponse(BaseSchema):
    """Aggregated internal service health response."""

    success: bool = Field(..., description="Whether the aggregation completed.")
    services: dict[str, dict[str, Any]] = Field(
        default_factory=dict,
        description="Per-service health snapshots or failures.",
    )
