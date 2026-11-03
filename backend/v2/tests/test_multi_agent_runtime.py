"""Multi-agent runtime (M1) tests: roles, inbox, async spawn/settlement.

Children run on their own thread; settlement is delivered to the parent inbox
instead of being merged inline. The engine consumes settlements at its step
boundary and refuses to finish while children are unsettled.
"""

from __future__ import annotations

import time
from threading import Event

import pytest

from schemas.runtime import PermissionPolicy, RequestContextV2, RunDetail
from v2.agents.inbox import AgentInbox, AgentSettlement
from v2.agents.registry import build_default_agent_registry
from v2.agents.runtime import SubAgentError, SubAgentRuntime
from v2.runtime.sub_executor import SubExecutionResult


class _Emitter:
    def __init__(self) -> None:
        self.events: list[tuple[str, str]] = []

    def emit(self, *, event: str, detail: str = "", **kwargs) -> None:
        self.events.append((event, detail))


class _Registry:
    def __init__(self) -> None:
        self.subsets: list[list[str]] = []

    def subset_by_prefixes(self, prefixes):
        self.subsets.append(list(prefixes))
        return self

    def get_executor_subset(self):
        return self


def _run(run_id: str = "run-1") -> RunDetail:
    return RunDetail(
        run_id=run_id,
        session_id="session-1",
        status="running",
        input_message="分析这块地",
        output_message="",
    )


def _policy() -> PermissionPolicy:
    return PermissionPolicy(name="default", description="test", max_replans=3, max_delegations=3)


def _settlement(run_id: str = "run-1", **overrides) -> AgentSettlement:
    payload = {
        "agent_run_id": "child-1",
        "parent_run_id": run_id,
        "role": "remote_sensing_analyst",
        "goal": "算 LAI",
        "success": True,
        "summary": "LAI=2.5",
        "duration_seconds": 0.1,
    }
    payload.update(overrides)
    return AgentSettlement(**payload)


def test_builtin_roles_restrict_tools():
    registry = build_default_agent_registry()
    names = {profile.name for profile in registry.list_profiles()}

    assert {"planner_70b", "executor_30b", "remote_sensing_analyst", "reporter", "reviewer"} <= names
    analyst = registry.get("remote_sensing_analyst")
    assert analyst is not None
    assert "remote_sensing." in analyst.tool_prefixes
    assert analyst.system_prompt
    reviewer = registry.get("reviewer")
    assert reviewer is not None and reviewer.tool_prefixes == []


def test_inbox_delivers_settlements_once():
    inbox = AgentInbox()
    inbox.push(_settlement())
    inbox.push(_settlement(agent_run_id="child-2"))

    assert inbox.pending("run-1") == 2
    drained = inbox.drain("run-1")
    assert [s.agent_run_id for s in drained] == ["child-1", "child-2"]
    assert inbox.drain("run-1") == []
    assert drained[0].as_history_item()["tool_call_id"] == "settlement_child-1"


def test_inbox_wait_returns_on_timeout():
    inbox = AgentInbox()
    started = time.monotonic()
    assert inbox.wait("run-1", timeout_seconds=0.1) == []
    assert time.monotonic() - started >= 0.1


def test_spawn_runs_a_child_and_settles_it(monkeypatch):
    calls: list[str] = []

    class FakeSubExecutor:
        def __init__(self, **kwargs) -> None:
            self.kwargs = kwargs

        def execute(self, *, goal, **_kwargs):
            calls.append(goal)
            return SubExecutionResult(success=True, summary="LAI=2.5")

    monkeypatch.setattr("v2.runtime.sub_executor.SubExecutor", FakeSubExecutor)
    emitter = _Emitter()
    registry = _Registry()
    runtime = SubAgentRuntime(
        tool_registry=registry,
        llm_provider=None,
        profile_registry=build_default_agent_registry(),
    )

    handle = runtime.spawn(
        parent_run=_run(),
        parent_emitter=emitter,
        request_context=RequestContextV2(),
        role="remote_sensing_analyst",
        goal="算 LAI",
        policy=_policy(),
        cancellation_event=Event(),
    )

    deadline = time.monotonic() + 2
    while runtime.pending("run-1") > 0 and time.monotonic() < deadline:
        time.sleep(0.01)
    drained = runtime.drain("run-1")

    assert calls == ["算 LAI"]
    assert handle.role == "remote_sensing_analyst"
    assert drained and drained[0].success and drained[0].summary == "LAI=2.5"
    assert drained[0].parent_run_id == "run-1"
    # role tool subset was applied
    assert registry.subsets and "remote_sensing." in registry.subsets[0]
    # a progress event advertised the activation
    assert any("已激活子代理" in detail for _event, detail in emitter.events)


def test_spawn_rejects_planner_and_unknown_roles():
    runtime = SubAgentRuntime(
        tool_registry=_Registry(),
        llm_provider=None,
        profile_registry=build_default_agent_registry(),
    )

    with pytest.raises(SubAgentError, match="不能作为子代理目标"):
        runtime.spawn(
            parent_run=_run(), parent_emitter=_Emitter(), request_context=RequestContextV2(),
            role="planner_70b", goal="x", policy=_policy(),
        )
    with pytest.raises(SubAgentError, match="unknown agent role"):
        runtime.spawn(
            parent_run=_run(), parent_emitter=_Emitter(), request_context=RequestContextV2(),
            role="nobody", goal="x", policy=_policy(),
        )


def test_spawn_respects_the_concurrency_limit(monkeypatch):
    class SlowSubExecutor:
        def __init__(self, **kwargs) -> None:
            pass

        def execute(self, **_kwargs):
            time.sleep(0.3)
            return SubExecutionResult(success=True, summary="done")

    monkeypatch.setattr("v2.runtime.sub_executor.SubExecutor", SlowSubExecutor)
    runtime = SubAgentRuntime(
        tool_registry=_Registry(),
        llm_provider=None,
        profile_registry=build_default_agent_registry(),
        max_concurrent_children=1,
    )
    runtime.spawn(
        parent_run=_run(), parent_emitter=_Emitter(), request_context=RequestContextV2(),
        role="reviewer", goal="a", policy=_policy(),
    )

    with pytest.raises(SubAgentError, match="并发子代理已达上限"):
        runtime.spawn(
            parent_run=_run(), parent_emitter=_Emitter(), request_context=RequestContextV2(),
            role="reviewer", goal="b", policy=_policy(),
        )


def test_cancel_signals_children(monkeypatch):
    seen: list[bool] = []

    class BlockingSubExecutor:
        def __init__(self, **kwargs) -> None:
            self.cancel = kwargs["cancellation_event"]

        def execute(self, **_kwargs):
            deadline = time.monotonic() + 1
            while time.monotonic() < deadline:
                if self.cancel.is_set():
                    seen.append(True)
                    return SubExecutionResult(success=False, summary="cancelled")
                time.sleep(0.01)
            seen.append(False)
            return SubExecutionResult(success=True, summary="done")

    monkeypatch.setattr("v2.runtime.sub_executor.SubExecutor", BlockingSubExecutor)
    runtime = SubAgentRuntime(
        tool_registry=_Registry(),
        llm_provider=None,
        profile_registry=build_default_agent_registry(),
    )
    runtime.spawn(
        parent_run=_run(), parent_emitter=_Emitter(), request_context=RequestContextV2(),
        role="reviewer", goal="a", policy=_policy(),
    )
    runtime.cancel("run-1")

    deadline = time.monotonic() + 2
    while runtime.pending("run-1") > 0 and time.monotonic() < deadline:
        time.sleep(0.01)
    assert seen == [True]
