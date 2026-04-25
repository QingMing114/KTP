"""Unified gateway-facing response models for the KTP single-agent product."""

from __future__ import annotations

from typing import Any, Literal

from pydantic import Field

from shared.schemas.common import BaseSchema
from v2.shared.schemas import AssistantMessageV2, PackArtifactView, ToolInvocationView


class GatewayWorkflowView(BaseSchema):
    model_registry_result: dict[str, Any] | None = None
    inference_result: dict[str, Any] | None = None
    knowledge_result: dict[str, Any] | None = None
    report_result: dict[str, Any] | None = None
    confidence_result: dict[str, Any] | None = None
    visualization_result: dict[str, Any] | None = None
    training_result: dict[str, Any] | None = None


class GatewayDebugView(BaseSchema):
    session_url: str
    run_url: str
    trace_url: str
    replay_url: str
    ui_url: str


class GatewayAgentResponse(BaseSchema):
    request_id: str
    conversation_id: str
    session_id: str
    run_id: str
    status: Literal["completed", "abstained", "failed"]
    answer: str
    assistant_message: AssistantMessageV2 | None = None
    artifacts: list[PackArtifactView] = Field(default_factory=list)
    sources: list[str] = Field(default_factory=list)
    tool_invocations: list[ToolInvocationView] = Field(default_factory=list)
    workflow: GatewayWorkflowView
    debug: GatewayDebugView
