from __future__ import annotations

from v2.shared.schemas import AgentProfile, ExecutorActionV2, PermissionPolicy, ToolSpecV2


class PolicyGuardError(RuntimeError):
    """Raised when an action violates bounded runtime policy."""


class PolicyGuard:
    """Minimal policy guard for V2 Phase 2."""

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
