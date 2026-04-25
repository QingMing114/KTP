"""Executor input and output schemas."""

from __future__ import annotations

from typing import Any

from pydantic import Field

from shared.schemas.common import BaseSchema


class ExecutorTaskInput(BaseSchema):
    """Structured task passed to the executor role."""

    request_id: str = Field(..., description="Workflow request identifier.")
    tool_name: str = Field(..., description="Logical tool or adapter to invoke.")
    payload: dict[str, Any] = Field(
        default_factory=dict,
        description="Structured payload for the tool execution.",
    )


class ExecutorTaskOutput(BaseSchema):
    """Structured task execution result."""

    request_id: str = Field(..., description="Workflow request identifier.")
    tool_name: str = Field(..., description="Logical tool or adapter invoked.")
    success: bool = Field(..., description="Whether execution succeeded.")
    message: str = Field(..., description="Short execution summary.")
    output: dict[str, Any] = Field(
        default_factory=dict,
        description="Structured service output payload.",
    )
