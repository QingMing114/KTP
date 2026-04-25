"""Schemas for the unified chat entrypoint."""

from __future__ import annotations

from typing import Any, Literal

from pydantic import Field

from shared.schemas.common import BaseSchema


class ChatRequest(BaseSchema):
    """Public request payload for the unified QA/workflow chat route."""

    request_id: str | None = Field(
        default=None,
        description="Optional stable request identifier. Generated when omitted.",
    )
    conversation_id: str | None = Field(
        default=None,
        description="Optional stable conversation identifier for multi-turn chat.",
    )
    user_id: str | None = Field(
        default=None,
        description="Optional user identifier used to isolate conversations.",
    )
    message: str = Field(..., min_length=1, max_length=10000, description="User message or task request.")
    mode: Literal["auto", "agent", "qa", "workflow"] = Field(
        default="auto",
        description="Routing mode. Auto prefers LLM self-routing when available; agent forces LLM self-routing.",
    )
    region: str | None = Field(default=None, max_length=50, description="Optional region context override.")
    crop_type: str | None = Field(default=None, max_length=50, description="Optional crop type override.")
    task_type: str | None = Field(default=None, max_length=50, description="Optional task type override.")
    image_path: str | None = Field(default=None, description="Optional local image path.")
    use_mock: bool | None = Field(default=None, description="Optional inference mock override.")
    top_k: int | None = Field(
        default=None,
        ge=1,
        le=100,
        description="Optional retrieval top-k for QA style requests.",
    )
    extra_params: dict[str, Any] = Field(
        default_factory=dict,
        description="Additional structured parameters forwarded downstream.",
    )


class ChatResponse(BaseSchema):
    """Unified response payload for chat QA and workflow execution."""

    request_id: str = Field(..., description="Stable request identifier.")
    conversation_id: str = Field(..., description="Stable conversation identifier.")
    user_id: str = Field(..., description="Resolved user identifier for conversation isolation.")
    success: bool = Field(..., description="Whether the routed operation succeeded.")
    mode: Literal["agent", "qa", "workflow"] = Field(
        ...,
        description="Resolved execution mode.",
    )
    route_reason: str = Field(..., description="Reason the request was routed this way.")
    answer: str = Field(..., description="User-facing Chinese answer.")
    message: str = Field(..., description="Human-readable operation outcome.")
    history_turn_count: int = Field(
        default=0,
        description="Number of prior conversation turns used as context.",
    )
    workflow_status: str | None = Field(
        default=None,
        description="Final workflow status when the request ran through orchestrator.",
    )
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
    sources: list[str] = Field(
        default_factory=list,
        description="Traceable knowledge sources used in the answer when available.",
    )
