"""Schemas for orchestrator requests and responses."""

from __future__ import annotations

from typing import Any

from pydantic import Field

from shared.schemas.common import BaseSchema


class WorkflowRequest(BaseSchema):
    """Request schema for invoking the orchestrator."""

    request_id: str = Field(..., description="Workflow request identifier.")
    user_query: str = Field(..., description="Natural-language user query.")
    region: str | None = Field(default=None, description="Optional explicit region override.")
    crop_type: str | None = Field(default=None, description="Optional explicit crop override.")
    task_type: str | None = Field(default=None, description="Optional explicit task override.")
    image_path: str | None = Field(
        default=None,
        description="Optional local image path used by inference-capable workflow runs.",
    )
    use_mock: bool | None = Field(
        default=None,
        description="Whether to force the mock inference path for this workflow run.",
    )
    extra_params: dict[str, Any] = Field(
        default_factory=dict,
        description="Additional structured parameters forwarded to downstream services.",
    )


class WorkflowResponse(BaseSchema):
    """Response schema produced by the orchestrator."""

    request_id: str = Field(..., description="Workflow request identifier.")
    status: str = Field(..., description="Final workflow status.")
    final_state: dict[str, Any] = Field(
        default_factory=dict,
        description="Final graph state after workflow execution.",
    )
