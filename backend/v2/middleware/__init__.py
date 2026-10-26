"""Tool execution middleware (see ``docs/tool_seam_v1_design.md`` S2)."""

from v2.middleware.builtin import (
    PermissionMiddleware,
    PolicyGuardMiddleware,
    build_default_tool_pipeline,
)
from v2.middleware.tool_pipeline import (
    ToolCallState,
    ToolMiddleware,
    ToolPipeline,
)

#: Middleware names a composition manifest may declare.
KNOWN_MIDDLEWARE_NAMES = frozenset({"permission", "policy-guard"})

__all__ = [
    "KNOWN_MIDDLEWARE_NAMES",
    "PermissionMiddleware",
    "PolicyGuardMiddleware",
    "ToolCallState",
    "ToolMiddleware",
    "ToolPipeline",
    "build_default_tool_pipeline",
]
