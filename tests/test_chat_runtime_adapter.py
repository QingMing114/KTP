"""Unit tests for gateway chat runtime adapter."""

from __future__ import annotations

from apps.api_gateway.schemas.chat import ChatRequest
from apps.api_gateway.services.chat_runtime_adapter import ChatRuntimeAdapter
from apps.orchestrator.chat_graph.workflow import ChatRuntimeGraphUnavailable


def test_chat_runtime_adapter_marks_dry_run_fallback(monkeypatch) -> None:
    adapter = ChatRuntimeAdapter()
    monkeypatch.setattr(
        "apps.api_gateway.services.chat_runtime_adapter.run_chat_runtime_graph",
        lambda _state: (_ for _ in ()).throw(ChatRuntimeGraphUnavailable("missing")),
    )
    monkeypatch.setattr(
        "apps.api_gateway.services.chat_runtime_adapter.run_chat_runtime",
        lambda _state: {
            **_state,
            "status": "finalized",
            "final_mode": "rag_qa",
            "final_answer": "基于知识库的回答。",
            "replan_count": 0,
            "max_replans": 1,
            "runtime_trace": [
                {"node": "planner", "event": "tool_sequence", "detail": "Need RAG.", "replan_count": 0}
            ],
            "tool_observation": {
                "step_id": "step-1",
                "tool_name": "rag_search",
                "success": True,
                "summary": "基于知识库的回答。",
                "output": {"summary": "基于知识库的回答。", "sources": ["knowledge://demo"]},
                "sources": ["knowledge://demo"],
            },
        },
    )

    result = adapter.run(
        request_id="req-adapter-001",
        user_id="user-001",
        conversation_id="conv-001",
        request=ChatRequest(message="NDVI 和 EVI 有什么区别？", mode="agent"),
        history=[],
    )

    assert result.success is True
    assert result.response_mode == "qa"
    assert result.context["runtime_runner"] == "dry_run_fallback"
    assert result.context["runtime_trace"][0]["node"] == "planner"


def test_chat_runtime_adapter_maps_abstain_to_failed_agent(monkeypatch) -> None:
    adapter = ChatRuntimeAdapter()
    monkeypatch.setattr(
        "apps.api_gateway.services.chat_runtime_adapter.run_chat_runtime_graph",
        lambda _state: {
            **_state,
            "status": "finalized",
            "final_mode": "abstain",
            "final_answer": "bounded runtime stops after the allowed replan.\n\n最近一次错误：workflow failed",
            "errors": ["workflow failed"],
            "replan_count": 1,
            "max_replans": 1,
            "runtime_trace": [
                {"node": "validate_observation", "event": "failed", "detail": "workflow failed", "replan_count": 1}
            ],
            "tool_observation": {
                "step_id": "step-1",
                "tool_name": "run_remote_sensing_workflow",
                "success": False,
                "summary": "workflow failed",
                "output": {},
                "sources": [],
            },
        },
    )

    result = adapter.run(
        request_id="req-adapter-002",
        user_id="user-001",
        conversation_id="conv-001",
        request=ChatRequest(message="请分析河北小麦病害情况", mode="agent"),
        history=[],
    )

    assert result.success is False
    assert result.response_mode == "agent"
    assert result.final_mode == "abstain"
    assert result.route_reason_suffix == "chat_graph:abstain"
    assert result.context["replan_count"] == 1


def test_chat_runtime_adapter_passes_configured_max_replans(monkeypatch) -> None:
    captured_state: dict[str, object] = {}

    def _graph_runner(state):
        captured_state.update(state)
        return {
            **state,
            "status": "finalized",
            "final_mode": "direct_answer",
            "final_answer": "直接回答。",
            "replan_count": 0,
            "max_replans": state["max_replans"],
            "runtime_trace": [],
            "tool_observation": {},
        }

    adapter = ChatRuntimeAdapter(max_replans=3)
    monkeypatch.setattr(
        "apps.api_gateway.services.chat_runtime_adapter.run_chat_runtime_graph",
        _graph_runner,
    )

    result = adapter.run(
        request_id="req-adapter-003",
        user_id="user-001",
        conversation_id="conv-001",
        request=ChatRequest(message="直接回答这个问题", mode="agent"),
        history=[],
    )

    assert captured_state["max_replans"] == 3
    assert result.context["max_replans"] == 3
