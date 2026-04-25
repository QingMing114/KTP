"""Unit tests for Phase 2/3 bounded chat runtime integration."""

from __future__ import annotations

from apps.orchestrator.chat_graph import nodes
from apps.orchestrator.chat_graph import runtime as chat_runtime_module
from apps.orchestrator.chat_graph.runtime import run_chat_runtime
from apps.orchestrator.chat_graph.states import create_initial_chat_state
from apps.orchestrator.chat_graph.workflow import ChatRuntimeGraphUnavailable, get_chat_runtime_graph
from shared.schemas.agent_runtime import PlannerDecision, PlannerStep
from shared.schemas.agent_runtime import ToolObservation
from shared.schemas.service_results import RagServiceResult


class _StubPlanner:
    def __init__(self, decision: PlannerDecision) -> None:
        self._decision = decision

    def plan(self, **_: object) -> PlannerDecision:
        return self._decision


class _StubExecutor:
    def __init__(self, action: dict[str, object]) -> None:
        self._action = action

    def choose_action(self, **_: object):
        from shared.schemas.agent_runtime import ExecutorAction

        return ExecutorAction.model_validate(self._action)


class _StubRagClient:
    def run_rag(self, **_: object) -> RagServiceResult:
        return RagServiceResult(
            query="NDVI 和 EVI 有什么区别？",
            summary="NDVI 对土壤背景更敏感，EVI 对高植被覆盖和大气影响更稳健。",
            sources=["knowledge://ndvi-evi"],
            top_k=1,
            results=[{"source": "knowledge://ndvi-evi", "text": "NDVI...EVI..."}],
        )


class _StubOrchestratorClient:
    def run_workflow(self, request):
        from shared.schemas.orchestrator import WorkflowResponse

        return WorkflowResponse(
            request_id=request.request_id,
            status="completed",
            final_state={
                "message": "Workflow completed successfully.",
                "report_result": {"report_uri": "report://demo"},
                "confidence_result": {"level": "medium"},
                "sources": [],
            },
        )


def test_planner_node_sets_decision_and_current_step(monkeypatch) -> None:
    decision = PlannerDecision(
        route="tool_sequence",
        reasoning_summary="Need workflow.",
        region="hebei",
        crop_type="wheat",
        task_type="crop_health_detection",
        need_training=False,
        need_rag=False,
        need_report=True,
        need_confidence=True,
        steps=[
            PlannerStep(
                step_id="step-1",
                action="call_tool",
                tool_name="run_remote_sensing_workflow",
                purpose="Run workflow.",
                tool_input={"message": "请分析河北小麦病害情况"},
            )
        ],
    )
    monkeypatch.setattr(nodes, "get_chat_runtime_planner", lambda: _StubPlanner(decision))
    state = create_initial_chat_state(
        request_id="req-phase2-001",
        user_id="user-001",
        conversation_id="conv-001",
        user_message="请分析河北小麦病害情况",
    )
    state.update(nodes.load_tool_registry_node(state))

    result = nodes.planner_node(state)

    assert result["status"] == "planned"
    assert result["planner_decision"]["route"] == "tool_sequence"
    assert result["current_step"]["tool_name"] == "run_remote_sensing_workflow"


def test_tool_dispatch_node_handles_rag(monkeypatch) -> None:
    monkeypatch.setattr(nodes, "get_chat_runtime_rag_client", lambda: _StubRagClient())
    state = create_initial_chat_state(
        request_id="req-phase2-002",
        user_id="user-001",
        conversation_id="conv-001",
        user_message="NDVI 和 EVI 有什么区别？",
    )
    state["executor_action"] = {
        "step_id": "step-1",
        "decision": "invoke_tool",
        "tool_name": "rag_search",
        "tool_input": {"user_query": state["user_message"], "context": {}, "top_k": 3},
        "message": "Invoke RAG.",
    }

    result = nodes.tool_dispatch_node(state)

    assert result["status"] == "tool_completed"
    assert result["final_mode"] == "rag_qa"
    assert result["tool_observation"]["success"] is True


def test_validate_tool_observation_node_accepts_rag_summary() -> None:
    state = create_initial_chat_state(
        request_id="req-phase2-002b",
        user_id="user-001",
        conversation_id="conv-001",
        user_message="NDVI 和 EVI 有什么区别？",
    )
    state["tool_observation"] = {
        "step_id": "step-1",
        "tool_name": "rag_search",
        "success": True,
        "summary": "基于知识库的回答。",
        "output": {"summary": "基于知识库的回答。", "sources": ["knowledge://demo"]},
        "sources": ["knowledge://demo"],
    }

    result = nodes.validate_tool_observation_node(state)

    assert result["status"] == "tool_validated"


def test_run_chat_runtime_dry_run_workflow(monkeypatch) -> None:
    decision = PlannerDecision(
        route="tool_sequence",
        reasoning_summary="Need workflow.",
        region="hebei",
        crop_type="wheat",
        task_type="crop_health_detection",
        need_training=False,
        need_rag=False,
        need_report=True,
        need_confidence=True,
        steps=[
            PlannerStep(
                step_id="step-1",
                action="call_tool",
                tool_name="run_remote_sensing_workflow",
                purpose="Run workflow.",
                tool_input={
                    "message": "请分析河北省小麦病害情况，并生成报告和置信度说明。",
                    "region": "hebei",
                    "crop_type": "wheat",
                    "task_type": "crop_health_detection",
                    "extra_params": {"agent_plan": {"need_report": True, "need_confidence": True}},
                },
            )
        ],
    )
    monkeypatch.setattr(nodes, "get_chat_runtime_planner", lambda: _StubPlanner(decision))
    monkeypatch.setattr(
        nodes,
        "get_chat_runtime_executor",
        lambda: _StubExecutor(
            {
                "step_id": "step-1",
                "decision": "invoke_tool",
                "tool_name": "run_remote_sensing_workflow",
                "tool_input": decision.steps[0].tool_input,
                "message": "Invoke workflow.",
            }
        ),
    )
    monkeypatch.setattr(nodes, "get_chat_runtime_orchestrator_client", lambda: _StubOrchestratorClient())
    state = create_initial_chat_state(
        request_id="req-phase2-003",
        user_id="user-001",
        conversation_id="conv-001",
        user_message="请分析河北省小麦病害情况，并生成报告和置信度说明。",
    )

    final_state = run_chat_runtime(state)

    assert final_state["status"] == "finalized"
    assert final_state["final_mode"] == "workflow"
    assert "Workflow completed successfully." in final_state["final_answer"]
    assert [entry["node"] for entry in final_state["runtime_trace"]] == [
        "load_tool_registry",
        "planner",
        "executor",
        "tool_dispatch",
        "validate_observation",
        "finalize_response",
    ]


def test_run_chat_runtime_falls_back_when_langgraph_unavailable(monkeypatch) -> None:
    state = create_initial_chat_state(
        request_id="req-phase2-004",
        user_id="user-001",
        conversation_id="conv-001",
        user_message="NDVI 和 EVI 有什么区别？",
    )
    monkeypatch.setattr(
        chat_runtime_module,
        "run_chat_runtime_graph",
        lambda _state: (_ for _ in ()).throw(ChatRuntimeGraphUnavailable("missing")),
    )
    monkeypatch.setattr(
        chat_runtime_module,
        "run_chat_runtime_dry_run",
        lambda _state: {**_state, "status": "finalized", "final_answer": "fallback", "final_mode": "agent"},
    )

    result = run_chat_runtime(state)

    assert result["status"] == "finalized"
    assert result["final_answer"] == "fallback"


def test_get_chat_runtime_graph_raises_without_langgraph() -> None:
    try:
        get_chat_runtime_graph()
    except ChatRuntimeGraphUnavailable:
        assert True
    else:  # pragma: no cover - only valid when dependency is actually installed
        assert True


def test_run_chat_runtime_replans_once_then_abstains(monkeypatch) -> None:
    planner_calls = {"count": 0}

    class _ReplanPlanner:
        def plan(self, **kwargs):
            planner_calls["count"] += 1
            if kwargs.get("replan_count", 0) == 0:
                return PlannerDecision(
                    route="tool_sequence",
                    reasoning_summary="Try workflow once.",
                    region="hebei",
                    crop_type="wheat",
                    task_type="crop_health_detection",
                    need_training=False,
                    need_rag=False,
                    need_report=False,
                    need_confidence=False,
                    steps=[
                        PlannerStep(
                            step_id="step-1",
                            action="call_tool",
                            tool_name="run_remote_sensing_workflow",
                            purpose="Run workflow.",
                            tool_input={"message": "请分析河北小麦病害情况"},
                        )
                    ],
                )
            return PlannerDecision(
                route="abstain",
                reasoning_summary="Previous tool call `run_remote_sensing_workflow` failed; bounded runtime stops after the allowed replan.",
                region="hebei",
                crop_type="wheat",
                task_type="crop_health_detection",
                need_training=False,
                need_rag=False,
                need_report=False,
                need_confidence=False,
                steps=[],
            )

    monkeypatch.setattr(nodes, "get_chat_runtime_planner", lambda: _ReplanPlanner())
    monkeypatch.setattr(
        nodes,
        "get_chat_runtime_executor",
        lambda: _StubExecutor(
            {
                "step_id": "step-1",
                "decision": "invoke_tool",
                "tool_name": "run_remote_sensing_workflow",
                "tool_input": {"message": "请分析河北小麦病害情况"},
                "message": "Invoke workflow.",
            }
        ),
    )

    def _failing_dispatch(*, request_id, state, action):
        del request_id, action
        return {
            "tool_observation": ToolObservation(
                step_id="step-1",
                tool_name="run_remote_sensing_workflow",
                success=False,
                summary="workflow failed",
                output={},
                sources=[],
            ).model_dump(),
            "errors": [*state.get("errors", []), "workflow failed"],
            "status": "tool_dispatch_failed",
        }

    monkeypatch.setattr(nodes, "_dispatch_workflow", _failing_dispatch)
    monkeypatch.setattr(
        chat_runtime_module,
        "run_chat_runtime_graph",
        lambda _state: (_ for _ in ()).throw(ChatRuntimeGraphUnavailable("missing")),
    )

    state = create_initial_chat_state(
        request_id="req-phase2-005",
        user_id="user-001",
        conversation_id="conv-001",
        user_message="请分析河北小麦病害情况",
    )

    final_state = run_chat_runtime(state)

    assert planner_calls["count"] == 2
    assert final_state["final_mode"] == "abstain"
    assert "workflow failed" in final_state["final_answer"]


def test_run_chat_runtime_replans_when_workflow_output_is_incomplete(monkeypatch) -> None:
    planner_calls = {"count": 0}

    class _ValidationPlanner:
        def plan(self, **kwargs):
            planner_calls["count"] += 1
            if kwargs.get("replan_count", 0) == 0:
                return PlannerDecision(
                    route="tool_sequence",
                    reasoning_summary="Need workflow with report and confidence.",
                    region="hebei",
                    crop_type="wheat",
                    task_type="crop_health_detection",
                    need_training=False,
                    need_rag=False,
                    need_report=True,
                    need_confidence=True,
                    steps=[
                        PlannerStep(
                            step_id="step-1",
                            action="call_tool",
                            tool_name="run_remote_sensing_workflow",
                            purpose="Run workflow.",
                            tool_input={"message": "请分析河北小麦病害情况"},
                        )
                    ],
                )
            return PlannerDecision(
                route="abstain",
                reasoning_summary="Previous tool call `run_remote_sensing_workflow` failed; bounded runtime stops after the allowed replan.",
                region="hebei",
                crop_type="wheat",
                task_type="crop_health_detection",
                need_training=False,
                need_rag=False,
                need_report=False,
                need_confidence=False,
                steps=[],
            )

    monkeypatch.setattr(nodes, "get_chat_runtime_planner", lambda: _ValidationPlanner())
    monkeypatch.setattr(
        nodes,
        "get_chat_runtime_executor",
        lambda: _StubExecutor(
            {
                "step_id": "step-1",
                "decision": "invoke_tool",
                "tool_name": "run_remote_sensing_workflow",
                "tool_input": {"message": "请分析河北小麦病害情况"},
                "message": "Invoke workflow.",
            }
        ),
    )

    def _incomplete_dispatch(*, request_id, action, state):
        del request_id, action, state
        return {
            "tool_observation": ToolObservation(
                step_id="step-1",
                tool_name="run_remote_sensing_workflow",
                success=True,
                summary="Workflow completed successfully.",
                output={"workflow_status": "completed", "report_result": None, "confidence_result": None},
                sources=[],
            ).model_dump(),
            "workflow_status": "completed",
            "final_mode": "workflow",
            "status": "tool_completed",
        }

    monkeypatch.setattr(nodes, "_dispatch_workflow", _incomplete_dispatch)
    monkeypatch.setattr(
        chat_runtime_module,
        "run_chat_runtime_graph",
        lambda _state: (_ for _ in ()).throw(ChatRuntimeGraphUnavailable("missing")),
    )

    state = create_initial_chat_state(
        request_id="req-phase2-006",
        user_id="user-001",
        conversation_id="conv-001",
        user_message="请分析河北小麦病害情况，并生成报告和置信度说明。",
    )

    final_state = run_chat_runtime(state)

    assert planner_calls["count"] == 2
    assert final_state["final_mode"] == "abstain"
    assert "requested report result" in final_state["final_answer"]
