from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel, Field


class HealthResponse(BaseModel):
    status: Literal["ok"]
    service: str
    version: str


class SessionMessage(BaseModel):
    role: Literal["user", "assistant", "system"]
    content: str


class AttachmentV2(BaseModel):
    kind: Literal["local_path"] = "local_path"
    path: str
    name: str | None = None


class TraceEventV2(BaseModel):
    node: str
    event: str
    detail: str


class SessionSummary(BaseModel):
    session_id: str
    title: str
    latest_run_id: str | None
    created_at: str | None = None
    updated_at: str | None = None


class SessionDetail(SessionSummary):
    created_by: str | None
    messages: list[SessionMessage]


class CreateSessionRequest(BaseModel):
    title: str | None = None
    user_id: str | None = None


class CreateSessionResponse(BaseModel):
    session: SessionDetail


class UpdateSessionRequest(BaseModel):
    title: str | None = None


class RequestContextV2(BaseModel):
    entrypoint: Literal["chat", "detect", "v2_ui", "api"] = "api"
    conversation_mode: Literal["chat", "task"] = "chat"
    region: str | None = None
    crop_type: str | None = None
    task_type: str | None = None
    image_path: str | None = None
    use_mock: bool | None = None
    attachments: list[AttachmentV2] = Field(default_factory=list)
    client_capabilities: dict[str, Any] = Field(default_factory=dict)
    extra_params: dict[str, Any] = Field(default_factory=dict)


class SendMessageRequest(BaseModel):
    message: str = Field(min_length=1)
    user_id: str | None = None
    context: RequestContextV2 | None = None


class AgentProfile(BaseModel):
    name: str
    role: str
    description: str


class ToolSpecV2(BaseModel):
    name: str
    display_name: str | None = None
    description: str
    visibility: Literal["public", "bounded", "internal"]
    category: str | None = None
    pack_name: str | None = None
    usage_hint: str | None = None
    input_schema: dict[str, Any] = Field(default_factory=dict)
    safety_level: Literal["safe", "caution", "dangerous"] = "safe"
    surface_visibility: Literal["all", "web", "api", "debug", "internal"] = "all"
    user_confirmation_required: bool = False
    enabled_by_default: bool = True
    is_macro: bool = False
    capabilities: list[str] = Field(default_factory=list)
    requires_context: list[str] = Field(default_factory=list)
    produces_artifacts: list[str] = Field(default_factory=list)


class PermissionPolicy(BaseModel):
    name: str
    description: str
    max_replans: int
    max_delegations: int
    allow_internal_tools: bool = False


class PlannerDecisionV2(BaseModel):
    action: Literal["reply", "clarify", "call_tools", "fail"]
    reasoning: str
    response_message: str | None = None


class AgentToolCallV2(BaseModel):
    call_id: str | None = None
    tool_name: str
    tool_input: dict[str, Any] = Field(default_factory=dict)


class AgentStepV2(PlannerDecisionV2):
    tool_calls: list[AgentToolCallV2] | None = Field(default_factory=list)


class ExecutorActionV2(BaseModel):
    action_type: Literal["respond", "invoke_tool", "delegate", "run_pack_flow", "abstain"]
    response_message: str | None = None
    tool_name: str | None = None
    tool_input: dict[str, Any] = Field(default_factory=dict)
    target_agent: str | None = None
    pack_name: str | None = None
    flow_name: str | None = None


class ObservationV2(BaseModel):
    source: str
    status: Literal["success", "error"]
    summary: str
    payload: dict[str, Any] = Field(default_factory=dict)


class DelegationRequest(BaseModel):
    target_agent: str
    goal: str


class DelegationResult(BaseModel):
    target_agent: str
    status: Literal["accepted", "rejected", "completed"]
    summary: str


class ToolInvocationView(BaseModel):
    call_id: str | None = None
    tool_name: str
    display_name: str | None = None
    category: str | None = None
    safety_level: Literal["safe", "caution", "dangerous"] = "safe"
    status: Literal["running", "success", "error", "blocked", "approval_required"]
    requires_confirmation: bool = False
    tool_input: dict[str, Any] = Field(default_factory=dict)
    result_preview: str | None = None
    is_user_visible: bool = True
    output_summary: str


class PackArtifactView(BaseModel):
    pack_name: str
    artifact_type: str
    title: str
    content: str | None = None
    uri: str | None = None


class AssistantMessagePartV2(BaseModel):
    type: Literal["text", "artifact", "tool_call", "tool_result", "status", "error"]
    text: str | None = None
    artifact: PackArtifactView | None = None
    tool_invocation: ToolInvocationView | None = None
    status: str | None = None


class AssistantMessageV2(BaseModel):
    role: Literal["assistant"] = "assistant"
    parts: list[AssistantMessagePartV2] = Field(default_factory=list)


class RunSummary(BaseModel):
    run_id: str
    session_id: str
    status: Literal["completed", "abstained", "failed"]
    input_message: str | None = None


class RunDetail(RunSummary):
    input_message: str
    input_context: RequestContextV2 | None = None
    output_message: str
    assistant_message: AssistantMessageV2 | None = None
    agent_steps: list[AgentStepV2] = Field(default_factory=list)
    planner_decision: PlannerDecisionV2 | None = None
    executor_action: ExecutorActionV2 | None = None
    observation: ObservationV2 | None = None
    delegation: DelegationResult | None = None
    tool_invocations: list[ToolInvocationView] = Field(default_factory=list)
    artifacts: list[PackArtifactView] = Field(default_factory=list)
    replan_count: int = 0
    delegation_count: int = 0
    replay_of_run_id: str | None = None
    trace: list[TraceEventV2] = Field(default_factory=list)


class RunEventV2(BaseModel):
    sequence: int
    event: str
    run_id: str
    session_id: str
    detail: str
    message: SessionMessage | None = None
    planner_decision: PlannerDecisionV2 | None = None
    executor_action: ExecutorActionV2 | None = None
    observation: ObservationV2 | None = None
    delegation: DelegationResult | None = None
    tool_invocation: ToolInvocationView | None = None
    artifact: PackArtifactView | None = None
    assistant_part: AssistantMessagePartV2 | None = None
    assistant_message: AssistantMessageV2 | None = None
    output_message: str | None = None
    run_status: Literal["completed", "abstained", "failed"] | None = None
    run: RunDetail | None = None


class SessionStateV2(BaseModel):
    session: SessionDetail
    latest_run: RunDetail | None = None


class RunStateV2(BaseModel):
    run: RunDetail
    policy: PermissionPolicy | None = None
    visible_tools: list[ToolSpecV2] = Field(default_factory=list)
    visible_agents: list[AgentProfile] = Field(default_factory=list)


class ReplayComparisonV2(BaseModel):
    overall_match: bool
    status_match: bool
    planner_action_match: bool
    planner_reasoning_match: bool
    executor_action_match: bool
    output_message_match: bool
    observation_source_match: bool
    observation_status_match: bool
    observation_summary_match: bool
    observation_payload_match: bool
    delegation_status_match: bool
    delegation_target_match: bool
    tool_invocation_count_match: bool
    tool_invocation_sequence_match: bool
    artifact_count_match: bool
    artifact_sequence_match: bool
    replan_count_match: bool
    delegation_count_match: bool
    trace_event_count_match: bool
    trace_event_sequence_match: bool
    mismatch_fields: list[str] = Field(default_factory=list)


class ReplayResponseV2(BaseModel):
    replay_mode: Literal["deterministic_dry_replay"]
    notes: str
    original_state: RunStateV2
    replayed_state: RunStateV2
    comparison: ReplayComparisonV2


class DomainPackSummary(BaseModel):
    name: str
    status: str
    description: str
    entry_tools: list[str] = Field(default_factory=list)
