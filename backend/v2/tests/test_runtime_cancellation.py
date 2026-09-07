from __future__ import annotations

import threading

from schemas.runtime import AgentStepV2, AgentToolCallV2, ObservationV2, ToolSpecV2
from v2.agents.registry import build_default_agent_registry
from v2.packs.registry import build_default_pack_registry
from v2.policies.registry import build_default_policy_registry
from v2.runtime.engine import BoundedRuntimeEngine
from v2.runtime.store import InMemoryRuntimeStore
from v2.tools.registry import ToolDefinition, ToolRegistryV2


class _BlockingPlanner:
    def __init__(self, started: threading.Event, release: threading.Event) -> None:
        self._started = started
        self._release = release

    def plan(self, **_kwargs) -> AgentStepV2:
        self._started.set()
        assert self._release.wait(timeout=3), "test did not release the planner"
        return AgentStepV2(
            action="call_tools",
            reasoning="invoke after planner returns",
            tool_calls=[
                AgentToolCallV2(
                    call_id="call-after-cancel",
                    tool_name="prosail.cancel_probe",
                    tool_input={},
                )
            ],
        )


def test_runtime_cancellation_stops_before_next_tool_step() -> None:
    tool_calls: list[str] = []
    spec = ToolSpecV2(
        name="prosail.cancel_probe",
        description="Records whether a tool was invoked after cancellation.",
        visibility="bounded",
    )

    def handler():
        tool_calls.append("called")
        return ObservationV2(
            source=spec.name,
            status="success",
            summary="called",
            payload={},
        ), []

    store = InMemoryRuntimeStore()
    store.create_session(session_id="session-cancel", title="cancel", created_by="test")
    engine = BoundedRuntimeEngine(
        store=store,
        tool_registry=ToolRegistryV2(
            definitions={spec.name: ToolDefinition(spec=spec, handler=handler)}
        ),
        policy_registry=build_default_policy_registry(),
        agent_registry=build_default_agent_registry(),
        pack_registry=build_default_pack_registry(),
    )
    planner_started = threading.Event()
    release_planner = threading.Event()
    cancellation_event = threading.Event()
    engine._planner = _BlockingPlanner(planner_started, release_planner)
    captured_events = []
    errors: list[BaseException] = []

    def consume() -> None:
        try:
            captured_events.extend(engine.stream(
                session_id="session-cancel",
                user_message="run then cancel",
                user_id="test",
                cancellation_event=cancellation_event,
            ))
        except BaseException as exc:  # test captures worker/consumer failures
            errors.append(exc)

    consumer = threading.Thread(target=consume)
    consumer.start()
    assert planner_started.wait(timeout=3)
    cancellation_event.set()
    release_planner.set()
    consumer.join(timeout=5)

    assert not consumer.is_alive()
    assert errors == []
    assert tool_calls == []
    assert captured_events[-1].event == "run.cancelled"
    assert captured_events[-1].run is not None
    assert captured_events[-1].run.status == "cancelled"
    assert store.list_runs()[0].status == "cancelled"
