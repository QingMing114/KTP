"""Deprecated import bridge for the V2 runtime schema package.

New runtime code must import these names from :mod:`schemas.runtime`.
Canonical product models are intentionally not exposed here; callers must
import them from :mod:`schemas.canonical` or :mod:`schemas.spatial`.
"""

from schemas.runtime import (
    AgentProfile,
    AgentStepV2,
    AgentToolCallV2,
    AssistantMessagePartV2,
    AssistantMessageV2,
    AttachmentV2,
    AuthTokenPayload,
    CreateSessionRequest,
    CreateSessionResponse,
    DelegationRequest,
    DelegationResult,
    DomainPackSummary,
    ExecutorActionV2,
    HealthResponse,
    ObservationV2,
    PackArtifactView,
    PermissionPolicy,
    PermissionResult,
    PlannerDecisionV2,
    PublicUserRecord,
    ReplayComparisonV2,
    ReplayResponseV2,
    RequestContextV2,
    RunDetail,
    RunEventV2,
    RunStateV2,
    RunSummary,
    RuntimeArtifactKind,
    RuntimeEventKind,
    RuntimeRunStatus,
    SceneParameters,
    SendMessageRequest,
    SessionDetail,
    SessionMessage,
    SessionStateV2,
    SessionSummary,
    ToolInvocationView,
    ToolSpecV2,
    TraceEventV2,
    UpdateSessionRequest,
    UserRecord,
)

DEPRECATED_ALIASES = frozenset({
    "AgentProfile", "AgentStepV2", "AgentToolCallV2", "AssistantMessagePartV2",
    "AssistantMessageV2", "AttachmentV2", "AuthTokenPayload", "CreateSessionRequest",
    "CreateSessionResponse", "DelegationRequest", "DelegationResult", "DomainPackSummary",
    "ExecutorActionV2", "HealthResponse", "ObservationV2", "PackArtifactView",
    "PermissionPolicy", "PermissionResult", "PlannerDecisionV2", "PublicUserRecord",
    "ReplayComparisonV2", "ReplayResponseV2", "RequestContextV2", "RunDetail", "RunEventV2",
    "RunStateV2", "RunSummary", "RuntimeArtifactKind", "RuntimeEventKind", "RuntimeRunStatus",
    "SceneParameters", "SendMessageRequest", "SessionDetail", "SessionMessage", "SessionStateV2",
    "SessionSummary", "ToolInvocationView", "ToolSpecV2", "TraceEventV2", "UpdateSessionRequest",
    "UserRecord",
})

__all__ = sorted(DEPRECATED_ALIASES)
