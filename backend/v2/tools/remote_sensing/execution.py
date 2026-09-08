"""Runtime-owned progress, cancellation, and deadline bridge."""

from __future__ import annotations

from datetime import UTC, datetime
from threading import Event, Lock

from v2.runtime.cancellation import raise_if_cancelled
from v2.runtime.events import RunEventEmitter
from v2.tools.remote_sensing.contract import AlgorithmProgressEvent, ToolExecutionContext
from v2.tools.remote_sensing.errors import AlgorithmDeadlineExceeded


class RuntimeAlgorithmExecutionControl:
    def __init__(
        self,
        *,
        context: ToolExecutionContext,
        event_emitter: RunEventEmitter,
        cancellation_event: Event | None,
        call_id: str,
    ) -> None:
        self.context = context
        self._event_emitter = event_emitter
        self._cancellation_event = cancellation_event
        self._call_id = call_id
        self._last_progress = 0.0
        self._lock = Lock()

    def raise_if_cancelled(self) -> None:
        raise_if_cancelled(self._cancellation_event)
        if self.context.deadline_at:
            deadline = datetime.fromisoformat(self.context.deadline_at)
            if deadline.tzinfo is None:
                deadline = deadline.replace(tzinfo=UTC)
            if datetime.now(UTC) >= deadline:
                raise AlgorithmDeadlineExceeded()

    def emit_progress(self, event: AlgorithmProgressEvent) -> None:
        self.raise_if_cancelled()
        if event.execution_id != self.context.execution_id:
            raise ValueError("progress execution_id does not match execution context")
        with self._lock:
            if event.progress < self._last_progress:
                raise ValueError("algorithm progress must be monotonic")
            self._last_progress = event.progress
        self._event_emitter.emit(
            event="tool.progress",
            detail=event.message or event.stage,
            tool_progress={
                "current": event.progress,
                "total": 1.0,
                "call_id": self._call_id,
                "stage": event.stage,
                "detail": event.detail,
            },
        )


__all__ = ["RuntimeAlgorithmExecutionControl"]
