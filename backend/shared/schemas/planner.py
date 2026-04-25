"""Planner schemas."""

from __future__ import annotations

from pydantic import Field

from shared.schemas.common import BaseSchema


class PlannerResult(BaseSchema):
    """Structured output from the planner role."""

    task_type: str = Field(..., description="Normalized task type.")
    region: str | None = Field(default=None, description="Normalized target region.")
    crop_type: str | None = Field(default=None, description="Normalized crop type.")
    need_training: bool = Field(..., description="Whether the plan expects training.")
    need_rag: bool = Field(..., description="Whether external knowledge is needed.")
    need_report: bool = Field(..., description="Whether a report should be built.")
    need_confidence: bool = Field(
        ...,
        description="Whether workflow confidence should be evaluated.",
    )
    reasoning_summary: str = Field(
        ...,
        description="Short explanation of why the planner set these fields.",
    )
