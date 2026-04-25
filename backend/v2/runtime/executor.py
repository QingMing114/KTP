from __future__ import annotations

from v2.shared.schemas import ExecutorActionV2, PlannerDecisionV2


class DeterministicExecutor:
    """Temporary clean-room executor for Phase 2 runtime work."""

    def build_action(self, decision: PlannerDecisionV2) -> ExecutorActionV2:
        if decision.action == "direct_answer":
            return ExecutorActionV2(
                action_type="respond",
                response_message=decision.response_message or "No direct response available.",
            )
        if decision.action == "call_tool":
            return ExecutorActionV2(
                action_type="invoke_tool",
                tool_name=decision.tool_name,
                tool_input=decision.tool_input,
            )
        if decision.action == "pack_flow":
            return ExecutorActionV2(
                action_type="run_pack_flow",
                tool_input=decision.tool_input,
                pack_name=decision.pack_name,
                flow_name=decision.flow_name,
            )
        if decision.action == "delegate":
            return ExecutorActionV2(
                action_type="delegate",
                target_agent=decision.target_agent,
            )
        return ExecutorActionV2(
            action_type="abstain",
            response_message=decision.response_message
            or "Runtime abstained because no safe bounded action was available.",
        )
