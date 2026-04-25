"""Runtime helpers for the bounded chat graph."""

from __future__ import annotations

from apps.orchestrator.chat_graph.nodes import (
    executor_node,
    finalize_response_node,
    load_tool_registry_node,
    planner_node,
    tool_dispatch_node,
    validate_tool_observation_node,
)
from apps.orchestrator.chat_graph.states import ChatRuntimeState
from apps.orchestrator.chat_graph.workflow import (
    ChatRuntimeGraphUnavailable,
    run_chat_runtime_graph,
)


def run_chat_runtime_dry_run(state: ChatRuntimeState) -> ChatRuntimeState:
    """Run the bounded chat runtime in-process without requiring LangGraph."""
    current_state = dict(state)
    current_state.update(load_tool_registry_node(current_state))

    while True:
        current_state.update(planner_node(current_state))
        if not current_state.get("current_step"):
            break

        current_state.update(executor_node(current_state))
        current_state.update(tool_dispatch_node(current_state))
        current_state.update(validate_tool_observation_node(current_state))

        status = current_state.get("status")
        if status in {"tool_validated", "tool_dispatch_skipped"}:
            break
        if status in {"tool_dispatch_failed", "tool_validation_failed", "executor_failed"}:
            replan_count = int(current_state.get("replan_count", 0))
            max_replans = int(current_state.get("max_replans", 1))
            if replan_count < max_replans:
                current_state["replan_count"] = replan_count + 1
                continue
            break
        break

    current_state.update(finalize_response_node(current_state))
    return current_state  # type: ignore[return-value]


def run_chat_runtime(state: ChatRuntimeState) -> ChatRuntimeState:
    """Run the bounded chat runtime, preferring LangGraph with dry-run fallback."""
    try:
        return run_chat_runtime_graph(state)
    except ChatRuntimeGraphUnavailable:
        return run_chat_runtime_dry_run(state)
