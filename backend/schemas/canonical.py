"""Canonical product protocol Pydantic models (/api/product/v1).

These models implement the stable product contract defined in
canonical_api_spec.md.  They are independent of the internal V2
runtime models in schemas.runtime.
"""

from __future__ import annotations

from typing import Any, Literal, TypeAlias

from pydantic import BaseModel, ConfigDict, Field, field_validator


DatasetSourceKind: TypeAlias = Literal["local_path"]
SubmissionStatus: TypeAlias = Literal[
    "queued", "running", "cancelling", "cancelled", "completed", "failed"
]
SubmissionStage: TypeAlias = Literal[
    "accepted", "processing", "cancelling", "finalizing", "completed", "failed", "cancelled"
]
CanonicalRunStatus: TypeAlias = Literal[
    "pending", "running", "completed", "failed", "abstained", "cancelled", "awaiting_approval"
]
CanonicalArtifactKind: TypeAlias = Literal[
    "apsim_report", "confidence_card", "file_content", "inference_card", "inversion_result",
    "knowledge_card", "lai_confidence_geotiff", "lai_geotiff", "lai_html_report", "lai_preview",
    "lai_raster", "lut_card", "reflectance_tif", "registry_card", "report_card", "search_results",
    "simulation_data", "simulation_log", "simulation_result", "text_card", "training_card",
    "visualization", "visualization_card",
]
SubmissionEventKind: TypeAlias = Literal[
    "submission.accepted", "submission.approval_required", "submission.cancelled",
    "run.started", "run.progress", "artifact.available", "run.completed", "run.failed",
]


# ── Manifest ──

class ManifestResponse(BaseModel):
    """GET /api/product/v1/manifest — capability negotiation."""
    protocol_version: str = "1.1"
    features: dict[str, bool] = Field(default_factory=dict)
    delivery_modes: list[str] = Field(default_factory=list)
    supported_preferences: list[str] = Field(default_factory=list)
    artifact_kinds: list[str] = Field(default_factory=list)
    compat_adapters: list[str] = Field(default_factory=list)
    limits: dict[str, int] = Field(default_factory=dict)
    debug_extension: bool = True


# ── Datasets ──

class DatasetSource(BaseModel):
    """Descriptor for a dataset's physical source."""
    kind: DatasetSourceKind = "local_path"
    uri: str  # absolute path to file


class DatasetDefaults(BaseModel):
    """Known dataset defaults; extensions remain explicit model extras."""

    model_config = ConfigDict(extra="allow")

    region: str | None = None
    crop_type: str | None = None
    task_type: str | None = None


class CreateDatasetRequest(BaseModel):
    """POST /api/product/v1/datasets."""
    source: DatasetSource
    display_name: str
    defaults: DatasetDefaults | None = None
    metadata: dict[str, Any] = Field(default_factory=dict)
    tags: list[str] = Field(default_factory=list)


class CanonicalDataset(BaseModel):
    """Canonical dataset resource."""
    dataset_id: str
    source: DatasetSource
    display_name: str
    defaults: DatasetDefaults = Field(default_factory=DatasetDefaults)
    metadata: dict[str, Any] = Field(default_factory=dict)
    tags: list[str] = Field(default_factory=list)
    created_at: str | None = None


class DatasetListResponse(BaseModel):
    items: list[CanonicalDataset]
    next_cursor: str | None = None
    has_more: bool = False


class UpdateDatasetRequest(BaseModel):
    """PATCH /api/product/v1/datasets/{dataset_id}."""
    display_name: str | None = None
    defaults: DatasetDefaults | None = None
    metadata: dict[str, Any] | None = None
    tags: list[str] | None = None


# ── Conversations ──

class CreateConversationRequest(BaseModel):
    """POST /api/product/v1/conversations."""
    title: str | None = None


class CanonicalConversation(BaseModel):
    """Canonical conversation resource (maps from SessionDetail)."""
    conversation_id: str
    title: str
    created_at: str | None = None
    updated_at: str | None = None


class ConversationListResponse(BaseModel):
    items: list[CanonicalConversation]
    next_cursor: str | None = None
    has_more: bool = False


class UpdateConversationRequest(BaseModel):
    """PATCH /api/product/v1/conversations/{id}."""
    title: str | None = None


# ── Submissions ──

class SubmissionReference(BaseModel):
    type: Literal["dataset"]
    id: str = Field(min_length=1)


class SubmissionInput(BaseModel):
    message: str = Field(min_length=1)
    refs: list[SubmissionReference] = Field(default_factory=list)


class SubmissionContext(BaseModel):
    inherit: Literal["latest", "none"] = "none"
    inherit_run_id: str | None = None


class SubmissionMode(BaseModel):
    interaction: Literal["task", "chat"] = "chat"
    delivery: Literal["async"] = "async"


class SubmissionPreferences(BaseModel):
    model_config = ConfigDict(extra="allow")

    include_visualization: bool | None = None


class SubmissionClient(BaseModel):
    model_config = ConfigDict(extra="forbid")

    name: str | None = None
    version: str | None = None


class CreateSubmissionRequest(BaseModel):
    """POST /api/product/v1/conversations/{id}/submissions."""
    input: SubmissionInput
    context: SubmissionContext | None = None
    mode: SubmissionMode | None = None
    preferences: SubmissionPreferences | None = None
    client: SubmissionClient | None = None


class SubmissionResponse(BaseModel):
    """Canonical submission resource."""
    submission_id: str
    conversation_id: str
    run_id: str | None = None
    status: SubmissionStatus
    stage: SubmissionStage
    created_at: str
    completed_at: str | None = None


# ── Artifacts ──

class CanonicalArtifact(BaseModel):
    """Canonical artifact resource (maps from PackArtifactView)."""
    artifact_id: str
    kind: CanonicalArtifactKind
    title: str
    view_url: str
    download_url: str | None = None
    content: str | None = None


class CreateApsimYieldReportRequest(BaseModel):
    """Parameters for a deterministic APSIM yield-report request."""

    mode: Literal["demo", "simulation"] = "demo"
    crop_type: Literal["wheat", "maize", "soybean"] = "wheat"
    region: str = Field(default="henan", min_length=1, max_length=80)
    start_year: int = Field(default=2024, ge=1900, le=2200)
    end_year: int = Field(default=2025, ge=1900, le=2200)
    cultivar: str | None = Field(default=None, max_length=120)
    sowing_date: str | None = Field(default=None, pattern=r"^\d{4}-\d{2}-\d{2}$")

    @field_validator("cultivar", "sowing_date", mode="before")
    @classmethod
    def empty_optional_string_to_none(cls, value: Any) -> Any:
        if isinstance(value, str) and not value.strip():
            return None
        return value


class ApsimYieldMetrics(BaseModel):
    estimated_yield_t_ha: float
    peak_lai: float
    max_biomass_g_m2: float
    simulation_days: int


class ApsimYieldReportResponse(BaseModel):
    status: Literal["success"]
    mode: Literal["demo", "simulation"]
    summary: str
    metrics: ApsimYieldMetrics
    parameters: dict[str, Any] = Field(default_factory=dict)
    artifact: CanonicalArtifact


class CanonicalAssistantPart(BaseModel):
    """A single part of a canonical assistant message."""
    type: Literal["text", "status", "artifact_ref", "warning", "error"]
    text: str | None = None
    artifact_id: str | None = None


class CanonicalAssistant(BaseModel):
    summary: str = ""
    parts: list[CanonicalAssistantPart] = Field(default_factory=list)


# ── Runs ──

class CanonicalRunResponse(BaseModel):
    """GET /api/product/v1/runs/{run_id}."""
    run_id: str
    conversation_id: str
    status: CanonicalRunStatus
    assistant: CanonicalAssistant | None = None
    artifacts: list[CanonicalArtifact] = Field(default_factory=list)
    workflow_summary: str | None = None
    termination_reason: str | None = None


class PaginatedRunsResponse(BaseModel):
    items: list[CanonicalRunResponse]
    next_cursor: str | None = None
    has_more: bool = False


# ── SSE events ──

class SubmissionSSEEvent(BaseModel):
    """Canonical SSE event sent over /api/product/v1/submissions/{id}/events."""
    event: SubmissionEventKind
    submission_id: str
    run_id: str | None = None
    stage: SubmissionStage | None = None
    detail: str = ""
    data: dict[str, Any] | None = None  # event-type-specific payload bag
    timestamp: str


# ── 从 schemas.runtime 迁移的对外模型 ──────────────────────────────
# 这些模型原本定义在 schemas/runtime.py，此处提供面向 API 的版本。
# 旧位置保留向后兼容（标记为已弃用），新代码应从 canonical 导入。


class SessionMessage(BaseModel):
    """Single message in conversation history. Exposed via /conversations/{id}/history."""
    role: Literal["user", "assistant", "system"]
    content: str
    parts: list[dict] = Field(default_factory=list)
    run_id: str | None = None        # 关联 canonical run
    timestamp: str = ""


class SessionSummary(BaseModel):
    """Conversation/session summary. Exposed via /conversations endpoints."""
    session_id: str
    title: str
    created_by: str | None = None
    latest_run_id: str | None = None
    created_at: str | None = None
    updated_at: str | None = None


class SessionDetail(SessionSummary):
    """Full session detail with message history."""
    messages: list[SessionMessage] = Field(default_factory=list)
    summary: str = ""


class RunSummary(BaseModel):
    """Run summary. Exposed via /runs/{id} endpoints."""
    run_id: str
    session_id: str
    status: Literal["pending", "running", "completed", "failed"]
    created_at: str = ""
    completed_at: str | None = None
    input_message: str = ""
    output_message: str = ""


class TraceEventV2(BaseModel):
    """Single trace event. Exposed via /debug/runs/{id}/trace."""
    node: str
    event: str
    detail: str = ""
    timestamp: str = ""


__all__ = [
    "CanonicalArtifact",
    "CanonicalArtifactKind",
    "CanonicalAssistant",
    "CanonicalAssistantPart",
    "CanonicalConversation",
    "CanonicalDataset",
    "CanonicalRunResponse",
    "CanonicalRunStatus",
    "ConversationListResponse",
    "CreateConversationRequest",
    "CreateDatasetRequest",
    "CreateSubmissionRequest",
    "DatasetListResponse",
    "DatasetDefaults",
    "DatasetSource",
    "DatasetSourceKind",
    "ManifestResponse",
    "PaginatedRunsResponse",
    "RunSummary",
    "SessionDetail",
    "SessionMessage",
    "SessionSummary",
    "SubmissionResponse",
    "SubmissionClient",
    "SubmissionContext",
    "SubmissionEventKind",
    "SubmissionInput",
    "SubmissionMode",
    "SubmissionPreferences",
    "SubmissionReference",
    "SubmissionStage",
    "SubmissionStatus",
    "SubmissionSSEEvent",
    "TraceEventV2",
    "UpdateConversationRequest",
    "UpdateDatasetRequest",
]
