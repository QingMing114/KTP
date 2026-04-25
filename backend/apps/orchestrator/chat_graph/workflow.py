"""LangGraph-backed builder for the bounded chat runtime."""

from __future__ import annotations

from functools import lru_cache

from apps.orchestrator.chat_graph.nodes import (
    executor_node,
    finalize_response_node,
    load_tool_registry_node,
    planner_node,
    tool_dispatch_node,
    validate_tool_observation_node,
)
from apps.orchestrator.chat_graph.states import ChatRuntimeState


class ChatRuntimeGraphUnavailable(RuntimeError):
    """Raised when the LangGraph runtime cannot be constructed locally."""


@lru_cache(maxsize=1)
def get_chat_runtime_graph():
    """Return the cached LangGraph runtime when the dependency is available."""
    try:
        from langgraph.graph import END, START, StateGraph
    except ModuleNotFoundError as exc:  # pragma: no cover - dependency varies by env
        raise ChatRuntimeGraphUnavailable("langgraph is not installed in the current environment.") from exc

    graph = StateGraph(ChatRuntimeState)
    graph.add_node("load_tool_registry", load_tool_registry_node)
    graph.add_node("planner", planner_node)
    graph.add_node("executor", executor_node)
    graph.add_node("tool_dispatch", tool_dispatch_node)
    graph.add_node("validate_observation", validate_tool_observation_node)
    graph.add_node("finalize_response", finalize_response_node)

    graph.add_edge(START, "load_tool_registry")
    graph.add_edge("load_tool_registry", "planner")
    graph.add_conditional_edges(
        "planner",
        _route_after_planner,
        {
            "executor": "executor",
            "finalize_response": "finalize_response",
        },
    )
    graph.add_edge("executor", "tool_dispatch")
    graph.add_edge("tool_dispatch", "validate_observation")
    graph.add_conditional_edges(
        "validate_observation",
        _route_after_validation,
        {
            "planner": "planner",
            "finalize_response": "finalize_response",
        },
    )
    graph.add_edge("finalize_response", END)
    return graph.compile()


def run_chat_runtime_graph(state: ChatRuntimeState) -> ChatRuntimeState:
    """Run the bounded chat runtime through LangGraph when available."""
    graph = get_chat_runtime_graph()
    result = graph.invoke(dict(state))
    return ChatRuntimeState(**result)


def _route_after_planner(state: ChatRuntimeState) -> str:
    return "executor" if state.get("current_step") else "finalize_response"


def _route_after_validation(state: ChatRuntimeState) -> str:
    status = state.get("status")
    if status in {"tool_validated", "tool_dispatch_skipped"}:
        return "finalize_response"
    if status in {"tool_dispatch_failed", "tool_validation_failed", "executor_failed"}:
        replan_count = int(state.get("replan_count", 0))
        max_replans = int(state.get("max_replans", 1))
        if replan_count < max_replans:
            state["replan_count"] = replan_count + 1
            return "planner"
    return "finalize_response"
