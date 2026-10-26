"""Built-in tool middleware.

The permission and policy-guard stages were extracted from
``ToolExecutor.execute_tool_call`` without changing behavior. Each middleware
is small and independently testable; the executor only composes them.
"""

from __future__ import annotations

from schemas.runtime import (
    AssistantMessagePartV2,
    ExecutorActionV2,
    ObservationV2,
    PermissionResult,
    TraceEventV2,
)
from v2.middleware.tool_pipeline import ToolCallState, ToolPipeline
from v2.policies.guard import PolicyGuard, PolicyGuardError
from v2.runtime.run_parts import append_assistant_part


class PermissionMiddleware:
    """Permission-first gate: hard blocks and approval-required early returns."""

    name = "permission"

    def __init__(self, guard: PolicyGuard) -> None:
        self._guard = guard

    def before(self, state: ToolCallState) -> dict[str, object] | None:
        tool_call = state.tool_call
        perm_result = self._guard.check_permission(tool_spec=state.spec, policy=state.policy)

        if self._guard.should_block(perm_result, policy=state.policy):
            blocked_invocation = state.invocation.model_copy(
                update={
                    "status": "blocked",
                    "output_summary": "blocked" if perm_result == PermissionResult.BLOCKED else "approval_required",
                    "result_preview": "blocked" if perm_result == PermissionResult.BLOCKED else "approval_required",
                }
            )
            state.run.tool_invocations.append(blocked_invocation)
            event_label = "tool.blocked" if perm_result == PermissionResult.BLOCKED else "approval_required"
            state.run.trace.append(
                TraceEventV2(
                    node="policy_guard",
                    event=event_label,
                    detail=f"Tool {tool_call.tool_name} blocked by policy: {perm_result.value}.",
                )
            )
            observation = ObservationV2(
                source=tool_call.tool_name,
                status="error",
                summary=perm_result.value,
                payload={"tool_name": tool_call.tool_name, "tool_input": tool_call.tool_input},
            )
            append_assistant_part(
                state.run,
                AssistantMessagePartV2(
                    type="tool_result",
                    tool_invocation=blocked_invocation,
                    text=perm_result.value,
                    status="blocked",
                ),
            )
            state.event_emitter.emit(
                event="tool.blocked",
                detail=f"Tool {tool_call.tool_name} blocked by policy: {perm_result.value}.",
                observation=observation,
                tool_invocation=blocked_invocation,
            )
            return {
                "blocked": True,
                "observation": observation,
                "final_message": f"Tool {tool_call.tool_name} blocked by policy: {perm_result.value}.",
                "history_item": {
                    "tool_name": tool_call.tool_name,
                    "status": "blocked",
                    "summary": perm_result.value,
                },
            }

        if perm_result == PermissionResult.NEEDS_APPROVAL:
            awaiting_invocation = state.invocation.model_copy(
                update={
                    "status": "approval_required",
                    "output_summary": "awaiting_approval",
                    "result_preview": "awaiting_approval",
                }
            )
            state.run.tool_invocations.append(awaiting_invocation)
            state.run.trace.append(
                TraceEventV2(
                    node="policy_guard",
                    event="approval_required",
                    detail=f"Tool {tool_call.tool_name} requires approval before execution.",
                )
            )
            append_assistant_part(
                state.run,
                AssistantMessagePartV2(
                    type="tool_result",
                    tool_invocation=awaiting_invocation,
                    text="awaiting_approval",
                    status="awaiting_approval",
                ),
            )
            return {
                "blocked": False,
                "approval_required": True,
                "observation": None,
                "final_message": f"Tool {tool_call.tool_name} is awaiting user approval.",
                "history_item": {
                    "tool_name": tool_call.tool_name,
                    "status": "awaiting_approval",
                    "summary": "awaiting_approval",
                },
            }

        return None

    def after(self, state: ToolCallState) -> None:
        """No post-processing."""


class PolicyGuardMiddleware:
    """Guard visible-tool/agent rules before dispatch.

    A rejection becomes an error observation and skips dispatch, matching the
    previous inline behavior: the call still settles as a tool result.
    """

    name = "policy-guard"

    def __init__(self, guard: PolicyGuard) -> None:
        self._guard = guard

    def before(self, state: ToolCallState) -> dict[str, object] | None:
        action = ExecutorActionV2(
            action_type="invoke_tool",
            tool_name=state.tool_call.tool_name,
            tool_input=state.tool_call.tool_input,
        )
        try:
            self._guard.validate_action(
                action=action,
                policy=state.policy,
                visible_tools=state.visible_tools,
                visible_agents=state.visible_agents,
                replan_count=0,
                delegation_count=0,
            )
        except PolicyGuardError as exc:
            state.observation = ObservationV2(
                source=state.tool_call.tool_name,
                status="error",
                summary=str(exc),
                payload={
                    "tool_name": state.tool_call.tool_name,
                    "tool_input": state.tool_call.tool_input,
                },
            )
            state.artifacts = []
            state.final_message = str(exc)
            state.skip_dispatch = True
        return None

    def after(self, state: ToolCallState) -> None:
        """No post-processing."""


def build_default_tool_pipeline(guard: PolicyGuard) -> ToolPipeline:
    """Return the pipeline used by the current single-engine deployment."""
    return ToolPipeline(
        before=(PermissionMiddleware(guard), PolicyGuardMiddleware(guard)),
        after=(),
    )
