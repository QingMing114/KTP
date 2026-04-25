"""Schemas for the self-scheduling agent runtime."""

from __future__ import annotations

from typing import Any, Literal

from pydantic import Field

from shared.schemas.common import BaseSchema


class ToolSpec(BaseSchema):
    """Metadata exposed to planner/executor for bounded tool discovery."""

    name: str = Field(..., description="Unique tool identifier.")
    description: str = Field(..., description="Concise tool summary.")
    input_schema: dict[str, str] = Field(
        default_factory=dict,
        description="Compact field contract for tool input.",
    )
    output_schema: dict[str, str] = Field(
        default_factory=dict,
        description="Compact field contract for tool output.",
    )
    when_to_use: str = Field(..., description="When the planner/executor should consider this tool.")
    usage_rules: list[str] = Field(
        default_factory=list,
        description="Important bounded usage rules.",
    )
    tags: list[str] = Field(
        default_factory=list,
        description="Searchable tags used by tool retrieval.",
    )
    risk_level: Literal["low", "medium", "high"] = Field(
        default="low",
        description="Operational risk of invoking the tool.",
    )


class PlannerStep(BaseSchema):
    """One structured step emitted by the planner role."""

    step_id: str = Field(..., description="Stable planner step identifier.")
    action: Literal["direct_answer", "call_tool", "finish"] = Field(
        ...,
        description="Planner-level next action.",
    )
    tool_name: str | None = Field(
        default=None,
        description="Tool to call when action=call_tool.",
    )
    purpose: str = Field(..., description="Why this step exists.")
    tool_input: dict[str, Any] = Field(
        default_factory=dict,
        description="Structured initial tool input suggested by the planner.",
    )


class PlannerDecision(BaseSchema):
    """Structured 70B planning decision for one chat turn."""

    route: Literal["direct_answer", "tool_sequence", "abstain"] = Field(
        ...,
        description="Top-level decision for the current user turn.",
    )
    reasoning_summary: str = Field(..., description="Short planner explanation.")
    answer: str | None = Field(
        default=None,
        description="Final answer when route=direct_answer.",
    )
    region: str | None = Field(default=None, description="Normalized region key when available.")
    crop_type: str | None = Field(default=None, description="Normalized crop key when available.")
    task_type: str | None = Field(default=None, description="Normalized task key when available.")
    need_training: bool | None = Field(default=None, description="Whether training is explicitly required.")
    need_rag: bool | None = Field(default=None, description="Whether retrieval is explicitly required.")
    need_report: bool | None = Field(default=None, description="Whether report generation is explicitly required.")
    need_confidence: bool | None = Field(
        default=None,
        description="Whether confidence evaluation is explicitly required.",
    )
    steps: list[PlannerStep] = Field(
        default_factory=list,
        description="Ordered bounded steps for the executor/runtime.",
    )


class ExecutorAction(BaseSchema):
    """Structured 30B executor output for one planned step."""

    step_id: str = Field(..., description="Planner step identifier.")
    decision: Literal["invoke_tool", "return_answer", "request_replan"] = Field(
        ...,
        description="Executor-level action.",
    )
    tool_name: str | None = Field(default=None, description="Tool chosen for invocation.")
    tool_input: dict[str, Any] = Field(
        default_factory=dict,
        description="Validated tool input prepared by the executor.",
    )
    message: str = Field(..., description="Short executor rationale or status.")


class ToolObservation(BaseSchema):
    """Normalized observation returned by a tool execution."""

    step_id: str = Field(..., description="Planner step identifier.")
    tool_name: str = Field(..., description="Tool that produced the observation.")
    success: bool = Field(..., description="Whether tool invocation succeeded.")
    summary: str = Field(..., description="Short summary of the tool result.")
    output: dict[str, Any] = Field(
        default_factory=dict,
        description="Structured tool output payload.",
    )
    sources: list[str] = Field(
        default_factory=list,
        description="Traceable sources when the tool uses retrieval or references.",
    )
