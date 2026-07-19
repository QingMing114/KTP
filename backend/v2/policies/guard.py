"""Policy guard for the V2 bounded runtime.

Validates executor actions against the active permission policy.
Phase A.2 adds :meth:`PolicyGuard.check_permission` — a non-throwing
permission check that returns a :class:`PermissionResult` enum value
instead of raising :class:`PolicyGuardError`.
"""

from __future__ import annotations

import logging

from v2.shared.schemas import (
    AgentProfile,
    ExecutorActionV2,
    PermissionPolicy,
    PermissionResult,
    ToolSpecV2,
)

logger = logging.getLogger(__name__)


class PolicyGuardError(RuntimeError):
    """Raised when an action violates bounded runtime policy."""


class PolicyGuard:
    """Policy guard for the V2 bounded runtime.

    After Phase A.2 the guard supports two calling conventions:

    1. **Legacy** — :meth:`validate_action` raises on any violation.
    2. **Permission-first** — :meth:`check_permission` returns a
       :class:`PermissionResult` enum so the caller can decide how to
       handle approval / blocking gracefully.
    """

    # ── legacy validation (raises) ──

    def validate_action(
        self,
        *,
        action: ExecutorActionV2,
        policy: PermissionPolicy,
        visible_tools: list[ToolSpecV2],
        visible_agents: list[AgentProfile],
        replan_count: int,
        delegation_count: int,
    ) -> None:
        if replan_count > policy.max_replans:
            raise PolicyGuardError("replan_budget_exceeded")
        if delegation_count > policy.max_delegations:
            raise PolicyGuardError("delegation_budget_exceeded")

        if action.action_type == "invoke_tool":
            tool_names = {tool.name for tool in visible_tools}
            if action.tool_name is None or action.tool_name not in tool_names:
                raise PolicyGuardError("tool_not_visible")

        if action.action_type == "delegate":
            visible_agent_names = {agent.name for agent in visible_agents}
            if action.target_agent is None or action.target_agent not in visible_agent_names:
                raise PolicyGuardError("agent_not_visible")

    # ── permission-first check (returns enum, no throw) ──

    @staticmethod
    def check_permission(
        *,
        tool_spec: ToolSpecV2,
        policy: PermissionPolicy,
    ) -> PermissionResult:
        """Check whether a tool is allowed to execute under *policy*.

        Decision table:

        ============================== ===================
        Condition                      Result
        ============================== ===================
        ``safety_level == dangerous``  ``BLOCKED``
        ``user_confirmation_required`` ``NEEDS_APPROVAL``
        otherwise                      ``ALLOWED``
        ============================== ===================

        The *policy.approval_mode* is **not** consumed here — the
        caller decides whether ``NEEDS_APPROVAL`` means a hard block
        (``auto_approve``) or an asynchronous approval flow
        (``require_approval``).
        """
        if tool_spec.safety_level == "dangerous":
            logger.warning(
                "permission_blocked_dangerous | tool=%s",
                tool_spec.name,
            )
            return PermissionResult.BLOCKED

        if tool_spec.user_confirmation_required:
            return PermissionResult.NEEDS_APPROVAL

        return PermissionResult.ALLOWED

    @staticmethod
    def should_block(
        result: PermissionResult,
        *,
        policy: PermissionPolicy,
    ) -> bool:
        """Return True when *result* should cause a hard block under *policy*.

        ``NEEDS_APPROVAL`` is only treated as a block when the policy
        is in ``auto_approve`` mode (the default for backward compat).
        In ``require_approval`` mode the caller is expected to enter
        the approval flow instead.
        """
        if result == PermissionResult.BLOCKED:
            return True
        if result == PermissionResult.NEEDS_APPROVAL and policy.approval_mode == "auto_approve":
            return True
        return False
