"""Canonical product protocol Pydantic models (/api/product/v1).

These models implement the stable product contract defined in
canonical_api_spec.md.  They are independent of the internal V2
runtime models in schemas.runtime.
"""

from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel, Field


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
    kind: str = "local_path"
    uri: str  # absolute path to file


class CreateDatasetRequest(BaseModel):
    """POST /api/product/v1/datasets."""
    source: DatasetSource
    display_name: str
    defaults: dict | None = None  # {region, crop_type, task_type}
    metadata: dict = Field(default_factory=dict)
    tags: list[str] = Field(default_factory=list)


class CanonicalDataset(BaseModel):
    """Canonical dataset resource."""
    dataset_id: str
    source: DatasetSource
    display_name: str
    defaults: dict = Field(default_factory=dict)
    metadata: dict = Field(default_factory=dict)
    tags: list[str] = Field(default_factory=list)
    created_at: str | None = None


class DatasetListResponse(BaseModel):
    items: list[CanonicalDataset]
    next_cursor: str | None = None
    has_more: bool = False


class UpdateDatasetRequest(BaseModel):
    """PATCH /api/product/v1/datasets/{dataset_id}."""
    display_name: str | None = None
    defaults: dict | None = None
    metadata: dict | None = None
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

class CreateSubmissionRequest(BaseModel):
    """POST /api/product/v1/conversations/{id}/submissions."""
    input: dict  # {message: str, refs: [{type: "dataset", id: str}]}
    context: dict | None = None  # {inherit: "latest"|"none", inherit_run_id: str | None}
    mode: dict | None = None  # {interaction: "task"|"chat", delivery: "async"}
    preferences: dict | None = None  # {include_visualization: bool, ...}
    client: dict | None = None  # {name: str, version: str}


class SubmissionResponse(BaseModel):
    """Canonical submission resource."""
    submission_id: str
    conversation_id: str
    run_id: str | None = None
    status: str  # queued | running | cancelling | cancelled | completed | failed
    stage: str  # accepted | processing | finalizing | completed | failed
    created_at: str
    completed_at: str | None = None


# ── Artifacts ──

class CanonicalArtifact(BaseModel):
    """Canonical artifact resource (maps from PackArtifactView)."""
    artifact_id: str
    kind: str
    title: str
    view_url: str
    download_url: str | None = None
    content: str | None = None


class CanonicalAssistantPart(BaseModel):
    """A single part of a canonical assistant message."""
    type: Literal["text", "status", "artifact_ref", "warning", "error"]
    text: str | None = None
    artifact_id: str | None = None


# ── Runs ──

class CanonicalRunResponse(BaseModel):
    """GET /api/product/v1/runs/{run_id}."""
    run_id: str
    conversation_id: str
    status: str
    assistant: dict | None = None  # {summary: str, parts: list[...]}
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
    event: str
    submission_id: str
    run_id: str | None = None
    stage: str | None = None
    detail: str = ""
    data: dict | None = None  # event-type-specific payload bag
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
    "CanonicalAssistantPart",
    "CanonicalConversation",
    "CanonicalDataset",
    "CanonicalRunResponse",
    "ConversationListResponse",
    "CreateConversationRequest",
    "CreateDatasetRequest",
    "CreateSubmissionRequest",
    "DatasetListResponse",
    "DatasetSource",
    "ManifestResponse",
    "PaginatedRunsResponse",
    "RunSummary",
    "SessionDetail",
    "SessionMessage",
    "SessionSummary",
    "SubmissionResponse",
    "SubmissionSSEEvent",
    "TraceEventV2",
    "UpdateConversationRequest",
    "UpdateDatasetRequest",
]
