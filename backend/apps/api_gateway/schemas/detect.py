"""Schemas for the public detect entrypoint."""

from __future__ import annotations

from typing import Any

from pydantic import Field

from shared.schemas.common import BaseSchema


class DetectRequest(BaseSchema):
    """Public request payload for detect-style workflow runs."""

    request_id: str = Field(..., description="Stable request identifier.")
    user_query: str = Field(..., description="Natural-language task description.")
    region: str | None = Field(default=None, description="Optional region override.")
    crop_type: str | None = Field(default=None, description="Optional crop override.")
    task_type: str | None = Field(default=None, description="Optional task override.")
    image_path: str | None = Field(default=None, description="Optional local image path.")
    use_mock: bool | None = Field(default=None, description="Force mock inference path.")
    extra_params: dict[str, Any] = Field(
        default_factory=dict,
        description="Additional structured parameters for downstream services.",
    )


class DetectResponse(BaseSchema):
    """Public response payload returned by the detect route."""

    request_id: str = Field(..., description="Original request identifier.")
    success: bool = Field(..., description="Whether the workflow succeeded.")
    workflow_status: str = Field(..., description="Final workflow status.")
    inference_result: dict[str, Any] | None = Field(
        default=None,
        description="Inference result when available.",
    )
    rag_result: dict[str, Any] | None = Field(
        default=None,
        description="RAG result when available.",
    )
    report_result: dict[str, Any] | None = Field(
        default=None,
        description="Report result when available.",
    )
    confidence_result: dict[str, Any] | None = Field(
        default=None,
        description="Confidence result when available.",
    )
    visualization_result: dict[str, Any] | None = Field(
        default=None,
        description="Visualization result when available.",
    )
    message: str = Field(..., description="Human-readable workflow outcome.")
