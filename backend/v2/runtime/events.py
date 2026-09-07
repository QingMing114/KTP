"""Event emitter for the V2 bounded runtime.

Extracted from BoundedRuntimeEngine._execute() — encapsulates the
event_sink, sequence counter, and RunEventV2 construction so the
engine doesn't need a 60-line closure.

Supports two calling conventions (for backward compatibility):

1. Keyword-arg style (primary, from the emit_event closure):
   emitter(event="tool.started", detail="...", tool_invocation=inv)

2. Raw-passthrough style (used by pack flow for file-size warnings):
   emitter(RunEventV2(sequence=0, event="assistant.status", ...))
"""

from __future__ import annotations

from typing import Callable, Literal

from schemas.runtime import (
    AssistantMessagePartV2,
    AssistantMessageV2,
    DelegationResult,
    ObservationV2,
    RunDetail,
    RunEventV2,
    RuntimeEventKind,
    RuntimeRunStatus,
    SessionMessage,
    ToolInvocationView,
)


class RunEventEmitter:
    """Wraps an event sink with auto-incrementing sequence numbers.

    Designed to replace the ``emit_event`` closure inside
    ``BoundedRuntimeEngine._execute()``.
    """

    def __init__(
        self,
        *,
        sink: Callable[[RunEventV2], None] | None,
        run_id: str,
        session_id: str,
    ) -> None:
        self._sink = sink
        self.run_id = run_id
        self.session_id = session_id
        self.sequence = 0
        self._run: RunDetail | None = None

    @property
    def run(self) -> RunDetail | None:
        """The run object being built (set by the engine after creation)."""
        return self._run

    @run.setter
    def run(self, value: RunDetail | None) -> None:
        self._run = value

    # ── primary API: keyword-arg construction ──

    def emit(
        self,
        *,
        event: RuntimeEventKind,
        detail: str = "",
        message: SessionMessage | None = None,
        planner_decision=None,
        executor_action=None,
        observation: ObservationV2 | None = None,
        delegation: DelegationResult | None = None,
        tool_invocation: ToolInvocationView | None = None,
        artifact=None,
        output_message: str | None = None,
        run_status: RuntimeRunStatus | None = None,
        include_run: bool = False,
        tool_progress: dict | None = None,
        assistant_message: AssistantMessageV2 | None = None,
    ) -> None:
        """Emit a single RunEventV2 constructed from keyword arguments.

        Mirrors the original ``emit_event`` closure signature exactly.
        """
        if self._sink is None:
            return
        self.sequence += 1
        self._sink(
            RunEventV2(
                sequence=self.sequence,
                event=event,
                run_id=self.run_id,
                session_id=self.session_id,
                detail=detail,
                message=message,
                planner_decision=planner_decision,
                executor_action=executor_action,
                observation=observation,
                delegation=delegation,
                tool_invocation=tool_invocation,
                artifact=artifact,
                assistant_part=(
                    AssistantMessagePartV2(type="text", text=output_message)
                    if event == "assistant.delta" and output_message is not None
                    else None
                ),
                assistant_message=assistant_message,
                output_message=output_message,
                run_status=run_status,
                run=self._run if include_run else None,
                tool_progress=tool_progress,
            )
        )

    # ── raw-passthrough API ──

    def send(self, raw_event: RunEventV2) -> None:
        """Normalize and send a pre-built event through the run sequence.

        Used by KTP pack flow for one-off events (e.g. file-size warnings)
        that bypass the standard emit closure convention.
        """
        if self._sink is None:
            return
        self.sequence += 1
        self._sink(RunEventV2.model_validate({
            **raw_event.model_dump(),
            "sequence": self.sequence,
            "run_id": self.run_id,
            "session_id": self.session_id,
        }))

    # ── callable interface for backward compatibility ──

    def __call__(
        self,
        raw_event: RunEventV2 | None = None,
        *,
        event: RuntimeEventKind | Literal[""] = "",
        detail: str = "",
        **kwargs: object,
    ) -> None:
        """Backward-compatible callable interface.

        When called positionally with a RunEventV2, forwards to :meth:`send`.
        When called with keyword arguments, forwards to :meth:`emit`.
        """
        if raw_event is not None:
            self.send(raw_event)
            return
        self.emit(event=event, detail=detail, **kwargs)

    @property
    def is_active(self) -> bool:
        """True when a sink is attached (i.e. events will be delivered)."""
        return self._sink is not None
