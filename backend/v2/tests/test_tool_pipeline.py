"""Tool execution pipeline tests.

The pipeline introduces ordered extension points without changing behavior:
``before`` middlewares short-circuit, ``dispatch`` runs the tool, ``finalize``
settles the run state, and ``after`` middlewares observe the settled state.
"""

from __future__ import annotations

from types import SimpleNamespace

import pytest

from schemas.runtime import PermissionPolicy, ToolInvocationView, ToolSpecV2
from v2.middleware import (
    PermissionMiddleware,
    PolicyGuardMiddleware,
    ToolCallState,
    ToolPipeline,
    build_default_tool_pipeline,
)
from v2.policies.guard import PolicyGuard


def _spec(**overrides) -> ToolSpecV2:
    payload = {
        "name": "demo.tool",
        "description": "Demo tool.",
        "visibility": "public",
    }
    payload.update(overrides)
    return ToolSpecV2(**payload)


def _policy() -> PermissionPolicy:
    return PermissionPolicy(
        name="test", description="test", max_replans=1, max_delegations=1
    )


def _state(*, spec: ToolSpecV2, visible_tools=None) -> tuple[ToolCallState, list[dict]]:
    events: list[dict] = []
    run = SimpleNamespace(
        assistant_message=None,
        tool_invocations=[],
        trace=[],
        input_message="hi",
    )
    state = ToolCallState(
        run=run,
        request_context=SimpleNamespace(),
        tool_call=SimpleNamespace(tool_name="demo.tool", tool_input={}, call_id="call-1"),
        spec=spec,
        policy=_policy(),
        visible_tools=[spec] if visible_tools is None else visible_tools,
        visible_agents=[],
        event_emitter=SimpleNamespace(emit=lambda **kwargs: events.append(kwargs)),
        invocation=ToolInvocationView(
            tool_name="demo.tool", status="running", output_summary="started"
        ),
    )
    return state, events


class _Recorder:
    def __init__(self, name: str, calls: list[str], early: dict | None = None) -> None:
        self.name = name
        self._calls = calls
        self._early = early

    def before(self, state: ToolCallState) -> dict[str, object] | None:
        self._calls.append(f"{self.name}.before")
        return self._early

    def after(self, state: ToolCallState) -> None:
        self._calls.append(f"{self.name}.after")


def test_pipeline_runs_stages_in_registration_order():
    calls: list[str] = []
    pipeline = ToolPipeline(
        before=(_Recorder("a", calls), _Recorder("b", calls)),
        after=(_Recorder("c", calls),),
    )
    state, _ = _state(spec=_spec())

    result = pipeline.run(
        state,
        dispatch=lambda s: calls.append("dispatch"),
        finalize=lambda s: calls.append("finalize"),
    )

    assert result is None
    assert calls == ["a.before", "b.before", "dispatch", "finalize", "c.after"]


def test_pipeline_short_circuits_on_early_result():
    calls: list[str] = []
    pipeline = ToolPipeline(before=(_Recorder("a", calls, early={"blocked": True}),))
    state, _ = _state(spec=_spec())

    result = pipeline.run(
        state,
        dispatch=lambda s: calls.append("dispatch"),
        finalize=lambda s: calls.append("finalize"),
    )

    assert result == {"blocked": True}
    assert calls == ["a.before"]


class _Skipper(_Recorder):
    def before(self, state: ToolCallState) -> dict[str, object] | None:
        self._calls.append(f"{self.name}.before")
        state.skip_dispatch = True
        return None


def test_pipeline_skips_dispatch_but_still_finalizes():
    calls: list[str] = []
    pipeline = ToolPipeline(before=(_Recorder("a", calls), _Skipper("skip", calls)))
    state, _ = _state(spec=_spec())

    pipeline.run(
        state,
        dispatch=lambda s: calls.append("dispatch"),
        finalize=lambda s: calls.append("finalize"),
    )

    assert calls == ["a.before", "skip.before", "finalize"]


def test_pipeline_rejects_duplicate_middleware_names():
    calls: list[str] = []

    with pytest.raises(ValueError, match="duplicate tool middleware names"):
        ToolPipeline(before=(_Recorder("a", calls),), after=(_Recorder("a", calls),))


def test_default_pipeline_declares_expected_middlewares():
    pipeline = build_default_tool_pipeline(PolicyGuard())

    assert pipeline.middleware_names == ["permission", "policy-guard"]


def test_permission_middleware_blocks_dangerous_tool():
    state, events = _state(spec=_spec(safety_level="dangerous"))

    result = PermissionMiddleware(PolicyGuard()).before(state)

    assert result is not None
    assert result["blocked"] is True
    assert state.run.tool_invocations[0].status == "blocked"
    assert events[-1]["event"] == "tool.blocked"


def test_permission_middleware_passes_safe_tool():
    state, _ = _state(spec=_spec())

    assert PermissionMiddleware(PolicyGuard()).before(state) is None


def test_policy_guard_middleware_skips_invisible_tool():
    state, _ = _state(spec=_spec(), visible_tools=[])

    assert PolicyGuardMiddleware(PolicyGuard()).before(state) is None

    assert state.skip_dispatch is True
    assert state.observation.status == "error"
    assert state.observation.summary == "tool_not_visible"
