"""Unit tests for the Phase 1 chat-runtime scaffold."""

from __future__ import annotations

from apps.orchestrator.chat_graph.nodes import load_tool_registry_node
from apps.orchestrator.chat_graph.states import create_initial_chat_state


def test_create_initial_chat_state_sets_expected_defaults() -> None:
    state = create_initial_chat_state(
        request_id="req-chat-runtime-001",
        user_id="user-001",
        conversation_id="conv-001",
        user_message="NDVI 和 EVI 有什么区别？",
    )

    assert state["status"] == "received"
    assert state["available_tools"] == []
    assert state["planner_decision"] is None
    assert state["executor_action"] is None


def test_load_tool_registry_node_returns_bounded_tool_set() -> None:
    state = create_initial_chat_state(
        request_id="req-chat-runtime-002",
        user_id="user-001",
        conversation_id="conv-001",
        user_message="请分析河北省小麦病害情况，并生成报告。",
        task_type="crop_health_detection",
    )

    result = load_tool_registry_node(state)

    assert result["status"] == "tools_loaded"
    assert result["available_tools"]
    assert any(tool["name"] == "run_remote_sensing_workflow" for tool in result["available_tools"])
