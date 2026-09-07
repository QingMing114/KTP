from __future__ import annotations

from schemas.runtime import (
    AgentStepV2,
    AgentToolCallV2,
    ObservationV2,
    PermissionPolicy,
    RequestContextV2,
    RunDetail,
    ToolSpecV2,
)
from v2.runtime.events import RunEventEmitter
from v2.runtime.sub_executor import SubExecutor
from v2.tools.registry import ToolDefinition, ToolRegistryV2


class _SequencePlanner:
    def __init__(self, *steps: AgentStepV2) -> None:
        self._steps = list(steps)

    def plan(self, **_kwargs) -> AgentStepV2:
        return self._steps.pop(0)


def _policy() -> PermissionPolicy:
    return PermissionPolicy(
        name="delegated-test",
        description="Delegated execution test policy.",
        max_replans=1,
        max_delegations=1,
    )


def _run() -> RunDetail:
    return RunDetail(
        run_id="run-parent",
        session_id="session-parent",
        status="running",
        input_message="run delegated tool",
        output_message="",
    )


def _registry(*, safety_level: str = "safe") -> ToolRegistryV2:
    spec = ToolSpecV2(
        name="prosail.test_delegate",
        display_name="Delegate test",
        description="A deterministic delegated test tool.",
        visibility="bounded",
        safety_level=safety_level,
    )

    def handler(value: int = 1):
        return (
            ObservationV2(
                source=spec.name,
                status="success",
                summary=f"value={value}",
                payload={"value": value},
            ),
            [],
        )

    return ToolRegistryV2(
        definitions={spec.name: ToolDefinition(spec=spec, handler=handler)}
    )


def test_sub_executor_uses_active_policy_for_safe_tool() -> None:
    sub = SubExecutor(
        tool_registry=_registry(),
        llm_provider=None,
        policy=_policy(),
    )
    sub._planner = _SequencePlanner(
        AgentStepV2(
            action="call_tools",
            reasoning="run the safe tool",
            tool_calls=[
                AgentToolCallV2(
                    call_id="call-safe",
                    tool_name="prosail.test_delegate",
                    tool_input={"value": 7},
                )
            ],
        ),
        AgentStepV2(
            action="reply",
            reasoning="summarize",
            response_message="delegated tool completed",
        ),
    )
    parent_run = _run()
    emitter = RunEventEmitter(
        sink=None,
        run_id=parent_run.run_id,
        session_id=parent_run.session_id,
    )

    result = sub.execute(
        goal="run the tool",
        request_context=RequestContextV2(),
        parent_emitter=emitter,
        parent_run=parent_run,
    )

    assert result.success is True
    assert result.summary == "delegated tool completed"
    assert parent_run.tool_invocations[-1].status == "success"


def test_sub_executor_rejects_tool_blocked_by_active_policy() -> None:
    sub = SubExecutor(
        tool_registry=_registry(safety_level="dangerous"),
        llm_provider=None,
        policy=_policy(),
    )
    sub._planner = _SequencePlanner(
        AgentStepV2(
            action="call_tools",
            reasoning="attempt dangerous tool",
            tool_calls=[
                AgentToolCallV2(
                    call_id="call-dangerous",
                    tool_name="prosail.test_delegate",
                    tool_input={},
                )
            ],
        )
    )
    parent_run = _run()
    emitter = RunEventEmitter(
        sink=None,
        run_id=parent_run.run_id,
        session_id=parent_run.session_id,
    )

    result = sub.execute(
        goal="run the dangerous tool",
        request_context=RequestContextV2(),
        parent_emitter=emitter,
        parent_run=parent_run,
    )

    assert result.success is False
    assert "blocked" in result.summary
    assert parent_run.tool_invocations[-1].status == "blocked"
