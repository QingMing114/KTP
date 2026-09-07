from __future__ import annotations

from dataclasses import dataclass

from schemas.runtime import (
    AgentStepV2,
    AgentToolCallV2,
    ObservationV2,
    PermissionPolicy,
    RequestContextV2,
    RunEventV2,
    ToolSpecV2,
)
from v2.agents.registry import build_default_agent_registry
from v2.packs.registry import build_default_pack_registry
from v2.policies.registry import PolicyRegistryV2
from v2.runtime.engine import BoundedRuntimeEngine
from v2.runtime.events import RunEventEmitter
from v2.runtime.planner import ChatFirstPlanner
from v2.runtime.store import InMemoryRuntimeStore
from v2.tools.registry import ToolDefinition, ToolRegistryV2


class _SequencePlanner:
    def __init__(self, *steps: AgentStepV2) -> None:
        self.steps = list(steps)

    def plan(self, **_kwargs) -> AgentStepV2:
        return self.steps.pop(0)


def _policy_registry(*, max_replans: int = 1, max_delegations: int = 1, approval_mode: str = "auto_approve"):
    return PolicyRegistryV2(policies=[PermissionPolicy(
        name="state-machine-test",
        description="Runtime state machine test policy.",
        max_replans=max_replans,
        max_delegations=max_delegations,
        approval_mode=approval_mode,
    )])


def _engine(*, handler, spec: ToolSpecV2 | None = None, policy_registry=None):
    tool_spec = spec or ToolSpecV2(
        name="prosail.state_probe",
        description="State machine probe.",
        visibility="bounded",
    )
    store = InMemoryRuntimeStore()
    store.create_session(session_id="state-session", title="state", created_by="test")
    engine = BoundedRuntimeEngine(
        store=store,
        tool_registry=ToolRegistryV2(definitions={
            tool_spec.name: ToolDefinition(spec=tool_spec, handler=handler),
        }),
        policy_registry=policy_registry or _policy_registry(),
        agent_registry=build_default_agent_registry(),
        pack_registry=build_default_pack_registry(),
    )
    return engine


def _tool_step(tool_name: str = "prosail.state_probe") -> AgentStepV2:
    return AgentStepV2(
        action="call_tools",
        reasoning="execute probe",
        tool_calls=[AgentToolCallV2(tool_name=tool_name, tool_input={})],
    )


def test_tool_failure_replans_once_then_completes_with_monotonic_events() -> None:
    attempts = 0

    def handler():
        nonlocal attempts
        attempts += 1
        status = "error" if attempts == 1 else "success"
        return ObservationV2(source="probe", status=status, summary=f"attempt={attempts}"), []

    engine = _engine(handler=handler)
    engine._planner = _SequencePlanner(
        _tool_step(),
        _tool_step(),
        AgentStepV2(action="reply", reasoning="summarize", response_message="recovered"),
    )

    events = list(engine.stream(session_id="state-session", user_message="run", user_id="test"))
    run = events[-1].run

    assert run is not None
    assert run.status == "completed"
    assert run.replan_count == 1
    assert attempts == 2
    sequences = [event.sequence for event in events]
    assert sequences == list(range(1, len(events) + 1))
    assert len(sequences) == len(set(sequences))


def test_replan_budget_exhaustion_fails_deterministically() -> None:
    def handler():
        return ObservationV2(source="probe", status="error", summary="still broken"), []

    engine = _engine(handler=handler, policy_registry=_policy_registry(max_replans=1))
    engine._planner = _SequencePlanner(_tool_step(), _tool_step())

    run = engine.run(session_id="state-session", user_message="run", user_id="test")

    assert run.status == "failed"
    assert run.replan_count == 1
    assert run.observation is not None
    assert run.observation.summary == "still broken"
    assert run.trace[-1].detail == "Run failed after exhausting the replan budget."


def test_delegation_budget_is_checked_before_second_delegation(monkeypatch) -> None:
    @dataclass
    class _Result:
        success: bool = True
        summary: str = "delegated"
        artifacts: list = None
        tool_invocations: list = None

        def __post_init__(self):
            self.artifacts = []
            self.tool_invocations = []

    class _SubExecutor:
        def __init__(self, **_kwargs) -> None:
            pass

        def execute(self, **_kwargs):
            return _Result()

    monkeypatch.setattr("v2.runtime.sub_executor.SubExecutor", _SubExecutor)
    engine = _engine(handler=lambda: (ObservationV2(source="probe", status="success", summary="ok"), []))
    delegate = AgentStepV2(
        action="delegate",
        reasoning="delegate",
        delegation_target="executor_30b",
        delegation_goal="bounded work",
    )
    engine._planner = _SequencePlanner(delegate, delegate.model_copy(deep=True))

    run = engine.run(session_id="state-session", user_message="delegate", user_id="test")

    assert run.status == "failed"
    assert run.delegation_count == 1
    assert run.observation is not None
    assert run.observation.payload["reason"] == "delegation_budget_exceeded"


def test_approval_uses_run_state_and_event_not_observation_status() -> None:
    spec = ToolSpecV2(
        name="prosail.state_probe",
        description="Approval probe.",
        visibility="bounded",
        user_confirmation_required=True,
    )
    engine = _engine(
        handler=lambda: (ObservationV2(source="probe", status="success", summary="should not run"), []),
        spec=spec,
        policy_registry=_policy_registry(approval_mode="require_approval"),
    )
    engine._planner = _SequencePlanner(_tool_step())

    events = list(engine.stream(session_id="state-session", user_message="approve", user_id="test"))
    run = events[-1].run

    assert run is not None
    assert run.status == "awaiting_approval"
    assert run.observation is None
    assert events[-1].event == "submission.approval_required"
    assert events[-1].run_status == "awaiting_approval"
    assert run.tool_invocations[-1].status == "approval_required"


def test_raw_events_are_normalized_by_the_emitter() -> None:
    captured: list[RunEventV2] = []
    emitter = RunEventEmitter(sink=captured.append, run_id="run-real", session_id="session-real")
    emitter.emit(event="run.started")
    emitter.send(RunEventV2(
        sequence=0,
        event="assistant.status",
        run_id="",
        session_id="",
        detail="raw",
    ))

    assert [event.sequence for event in captured] == [1, 2]
    assert captured[-1].run_id == "run-real"
    assert captured[-1].session_id == "session-real"


def test_valid_visible_planner_tool_decision_is_not_replaced_by_keywords() -> None:
    selected = ToolSpecV2(
        name="ktp.analysis_pipeline",
        description="Selected structured tool.",
        visibility="bounded",
    )
    keyword_candidate = ToolSpecV2(
        name="apsim.crop_simulation",
        description="Keyword candidate.",
        visibility="bounded",
    )
    step = ChatFirstPlanner._normalize_step(
        step=AgentStepV2(
            action="call_tools",
            reasoning="structured decision",
            tool_calls=[AgentToolCallV2(tool_name=selected.name, tool_input={})],
        ),
        message="Run an APSIM crop simulation",
        request_context=RequestContextV2(),
        visible_tools=[selected, keyword_candidate],
    )

    assert step.tool_calls is not None
    assert step.tool_calls[0].tool_name == selected.name
