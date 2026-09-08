"""V2 runtime Pydantic models.

Auto-generated from v2/shared/schemas.py during Step 0 refactoring.
All models that were originally in v2/shared/schemas.py now live here.

Old import paths continue to work via the re-export bridge at
v2/shared/schemas.py.
"""

from __future__ import annotations

from enum import Enum
from typing import Any, Literal, TypeAlias

from pydantic import BaseModel, Field


RuntimeRunStatus: TypeAlias = Literal[
    "completed", "abstained", "failed", "running", "cancelled", "awaiting_approval"
]
RuntimeEventKind: TypeAlias = Literal[
    "agent_step_selected", "analysis_input_clarification", "approval_required", "artifact.available",
    "artifact_created", "assistant.delta", "assistant.status", "assistant_message",
    "llm_schema_alias_applied", "loop_terminated_duplicate_calls", "planner.delta",
    "planner_decision", "planner_start", "planning_failed", "prosail.reasoning",
    "request_context_loaded", "run.cancelled", "run.completed", "run.error", "run.failed",
    "run.progress", "run.started", "run_cancelled", "run_completed", "run_created", "run_failed",
    "run_finalized", "submission.approval_required", "thinking", "tool.blocked", "tool.completed",
    "tool.progress", "tool.started", "tool_call_completed", "tool_call_started", "tool_failed",
    "tool_finished", "visibility_loaded",
]
RuntimeArtifactKind: TypeAlias = Literal[
    "apsim_report", "confidence_card", "file_content", "inference_card", "inversion_result",
    "knowledge_card", "lai_confidence_geotiff", "lai_geotiff", "lai_html_report", "lai_preview",
    "lai_raster", "lut_card", "registry_card", "report_card", "search_results", "simulation_data",
    "simulation_log", "simulation_result", "text_card", "training_card", "visualization_card",
    "classification_result", "segmentation_mask", "segmentation_preview", "statistics_table",
    "provenance_record",
]


# ── Permission model ──


class PermissionResult(str, Enum):
    """Outcome of a permission check against a tool's spec + policy."""

    ALLOWED = "allowed"
    NEEDS_APPROVAL = "needs_approval"
    BLOCKED = "blocked"


# ── Shared types ──

class HealthResponse(BaseModel):
    status: Literal["ok"]
    service: str
    version: str


# Deprecated: use schemas.canonical.SessionMessage instead
# Kept here for backward compatibility during migration
class SessionMessage(BaseModel):
    role: Literal["user", "assistant", "system"]
    content: str


class AttachmentV2(BaseModel):
    kind: Literal["local_path"] = "local_path"
    path: str
    name: str | None = None


class ResolvedDatasetV2(BaseModel):
    """A dataset reference resolved by the canonical boundary for Runtime use."""

    dataset_id: str
    display_name: str
    local_path: str
    region: str | None = None
    crop_type: str | None = None
    task_type: str | None = None
    content_type: str | None = None


# Deprecated: use schemas.canonical.TraceEventV2 instead
# Kept here for backward compatibility during migration
class TraceEventV2(BaseModel):
    node: str
    event: str
    detail: str


# ── Session models ──

# Deprecated: use schemas.canonical.SessionSummary instead
# Kept here for backward compatibility during migration
class SessionSummary(BaseModel):
    session_id: str
    title: str
    latest_run_id: str | None
    created_at: str | None = None
    updated_at: str | None = None
    summary: str | None = None


# Deprecated: use schemas.canonical.SessionDetail instead
# Kept here for backward compatibility during migration
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


# ── Request / context models ──


class SceneParameters(BaseModel):
    """LLM-extracted PROSAIL scene parameters for LUT inversion.

    Attributes:
        crop_type:   Detected crop type (e.g. "玉米", "Wheat").
        region:      Geographic region (e.g. "张掖", "河南").
        month:       Inferred month (1–12) for growth-stage mapping.
        growth_stage: Human-readable growth stage description.
        lai_range:   Plausible LAI range [min, max]  m²/m².
        cab_range:   Plausible Cab range [min, max]  μg/cm².
        lidfa_range: Plausible LIDFa range [min, max]  degrees.
        psoil_range: Plausible psoil range [min, max].
        confidence:  Overall confidence 0–1 (≥0.4 = usable).
        reasoning:   Short explanation of the inference logic.
    """

    crop_type: str | None = None
    region: str | None = None
    month: int | None = None
    growth_stage: str | None = None
    lai_range: tuple[float, float] | None = None
    cab_range: tuple[float, float] | None = None
    lidfa_range: tuple[float, float] | None = None
    psoil_range: tuple[float, float] | None = None
    confidence: float = 0.0
    reasoning: str = ""

    def to_constraints(self) -> dict[str, list[float]]:
        """Convert non-None parameter ranges to LUT filtering constraints."""
        constraints: dict[str, list[float]] = {}
        if self.lai_range is not None:
            constraints["lai_range"] = list(self.lai_range)
        if self.cab_range is not None:
            constraints["cab_range"] = list(self.cab_range)
        if self.lidfa_range is not None:
            constraints["lidfa_range"] = list(self.lidfa_range)
        if self.psoil_range is not None:
            constraints["psoil_range"] = list(self.psoil_range)
        return constraints

class RequestContextV2(BaseModel):
    entrypoint: Literal["chat", "detect", "v2_ui", "api"] = "api"
    conversation_mode: Literal["chat", "task"] = "chat"
    region: str | None = None
    crop_type: str | None = None
    task_type: str | None = None
    image_path: str | None = None
    use_mock: bool | None = None
    attachments: list[AttachmentV2] = Field(default_factory=list)
    datasets: list[ResolvedDatasetV2] = Field(default_factory=list)
    client_capabilities: dict[str, Any] = Field(default_factory=dict)
    extra_params: dict[str, Any] = Field(default_factory=dict)
    scene_parameters: SceneParameters | None = None


class SendMessageRequest(BaseModel):
    message: str = Field(min_length=1)
    user_id: str | None = None
    context: RequestContextV2 | None = None


# ── Agent / tool registries ──

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
    output_schema: dict[str, Any] = Field(default_factory=dict)
    contract_version: str = "legacy"
    availability: Literal["available", "unavailable", "disabled"] = "available"
    unavailable_reason: str | None = None
    permissions: list[str] = Field(default_factory=list)
    runtime_requirements: dict[str, Any] = Field(default_factory=dict)
    implementation: dict[str, Any] = Field(default_factory=dict)
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
    approval_mode: Literal["auto_approve", "require_approval"] = "auto_approve"


# ── Agent loop models ──

class PlannerDecisionV2(BaseModel):
    action: Literal["reply", "clarify", "call_tools", "delegate", "fail"]
    reasoning: str
    response_message: str | None = None
    delegation_target: str | None = None   # 当 action="delegate" 时，目标 agent
    delegation_goal: str | None = None     # 当 action="delegate" 时，委派任务描述


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
    artifact_type: RuntimeArtifactKind
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


# ── Run / state models ──

# Deprecated (API use): use schemas.canonical.RunSummary instead
# Kept here for backward compatibility — RunDetail extends it internally.
class RunSummary(BaseModel):
    run_id: str
    session_id: str
    status: RuntimeRunStatus
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
    task_digest: dict | None = None


class RunEventV2(BaseModel):
    sequence: int
    event: RuntimeEventKind
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
    run_status: RuntimeRunStatus | None = None
    run: RunDetail | None = None
    tool_progress: dict | None = None  # {"current": int, "total": int, "call_id": str}


class SessionStateV2(BaseModel):
    session: SessionDetail
    latest_run: RunDetail | None = None


class RunStateV2(BaseModel):
    run: RunDetail
    policy: PermissionPolicy | None = None
    visible_tools: list[ToolSpecV2] = Field(default_factory=list)
    visible_agents: list[AgentProfile] = Field(default_factory=list)


# ── Replay models ──

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


# ── Domain pack ──

class DomainPackSummary(BaseModel):
    name: str
    status: Literal["ready", "partial", "disabled"]
    description: str
    entry_tools: list[str] = Field(default_factory=list)


# ── Auth models ──

class UserRecord(BaseModel):
    user_id: str
    password_hash: str
    role: str = "user"
    created_at: str = ""
    last_login: str | None = None


class PublicUserRecord(BaseModel):
    user_id: str
    role: str = "user"
    created_at: str = ""
    last_login: str | None = None


class AuthTokenPayload(BaseModel):
    user_id: str
    role: str = "user"
    exp: float = -1


__all__ = [
    "AgentProfile",
    "AgentStepV2",
    "AgentToolCallV2",
    "AssistantMessagePartV2",
    "AssistantMessageV2",
    "AttachmentV2",
    "AuthTokenPayload",
    "CreateSessionRequest",
    "CreateSessionResponse",
    "DelegationRequest",
    "DelegationResult",
    "DomainPackSummary",
    "ExecutorActionV2",
    "HealthResponse",
    "ObservationV2",
    "PackArtifactView",
    "PermissionPolicy",
    "PermissionResult",
    "PlannerDecisionV2",
    "PublicUserRecord",
    "ReplayComparisonV2",
    "ReplayResponseV2",
    "ResolvedDatasetV2",
    "RequestContextV2",
    "RunDetail",
    "RunEventV2",
    "RuntimeArtifactKind",
    "RuntimeEventKind",
    "RuntimeRunStatus",
    "RunStateV2",
    "RunSummary",
    "SceneParameters",
    "SendMessageRequest",
    "SessionDetail",
    "SessionMessage",
    "SessionStateV2",
    "SessionSummary",
    "ToolInvocationView",
    "ToolSpecV2",
    "TraceEventV2",
    "UpdateSessionRequest",
    "UserRecord",
]
