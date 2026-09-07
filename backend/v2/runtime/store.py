from __future__ import annotations

from typing import Protocol
from typing import Dict

from schemas.runtime import RunDetail, SessionDetail, SessionMessage, TraceEventV2


class RuntimeStore(Protocol):
    def create_session(self, *, session_id: str, title: str, created_by: str | None) -> SessionDetail: ...
    def get_session(self, session_id: str) -> SessionDetail | None: ...
    def list_sessions(self) -> list[SessionDetail]: ...
    def save_session(self, session: SessionDetail) -> None: ...
    def delete_session(self, session_id: str) -> None: ...
    def save_run(self, run: RunDetail) -> None: ...
    def get_run(self, run_id: str) -> RunDetail | None: ...
    def list_runs(self) -> list[RunDetail]: ...
    def list_runs_for_session(self, session_id: str) -> list[RunDetail]: ...
    def append_message(self, session_id: str, message: SessionMessage) -> None: ...
    def append_trace(self, run_id: str, event: TraceEventV2) -> None: ...


class InMemoryRuntimeStore:
    """Minimal in-memory runtime store for V2 skeleton work."""

    def __init__(self) -> None:
        self._sessions: Dict[str, SessionDetail] = {}
        self._runs: Dict[str, RunDetail] = {}

    def create_session(self, *, session_id: str, title: str, created_by: str | None) -> SessionDetail:
        session = SessionDetail(
            session_id=session_id,
            title=title,
            created_by=created_by,
            messages=[],
            latest_run_id=None,
        )
        self._sessions[session_id] = session
        return session

    def get_session(self, session_id: str) -> SessionDetail | None:
        return self._sessions.get(session_id)

    def list_sessions(self) -> list[SessionDetail]:
        return list(self._sessions.values())

    def save_session(self, session: SessionDetail) -> None:
        self._sessions[session.session_id] = session

    def delete_session(self, session_id: str) -> None:
        if session_id in self._sessions:
            del self._sessions[session_id]
        self._runs = {k: v for k, v in self._runs.items() if v.session_id != session_id}

    def save_run(self, run: RunDetail) -> None:
        self._runs[run.run_id] = run

    def get_run(self, run_id: str) -> RunDetail | None:
        return self._runs.get(run_id)

    def list_runs(self) -> list[RunDetail]:
        return list(self._runs.values())

    def list_runs_for_session(self, session_id: str) -> list[RunDetail]:
        return [run for run in self._runs.values() if run.session_id == session_id]

    def append_message(self, session_id: str, message: SessionMessage) -> None:
        session = self._sessions[session_id]
        session.messages.append(message)
        self._sessions[session_id] = session

    def append_trace(self, run_id: str, event: TraceEventV2) -> None:
        run = self._runs[run_id]
        run.trace.append(event)
        self._runs[run_id] = run
