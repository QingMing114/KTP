from __future__ import annotations

import json
import logging
import sqlite3
import threading
from datetime import datetime, timezone
from pathlib import Path

from v2.shared.schemas import RunDetail, SessionDetail, SessionMessage, TraceEventV2

logger = logging.getLogger(__name__)


class SQLiteRuntimeStore:
    """SQLite-backed runtime store for V2 Phase 3 work."""

    def __init__(self, *, database_path: str) -> None:
        self._database_path = Path(database_path)
        self._database_path.parent.mkdir(parents=True, exist_ok=True)
        self._lock = threading.Lock()
        self._initialize_schema()

    def create_session(self, *, session_id: str, title: str, created_by: str | None) -> SessionDetail:
        now = datetime.now(timezone.utc).isoformat()
        session = SessionDetail(
            session_id=session_id,
            title=title,
            created_by=created_by,
            messages=[],
            latest_run_id=None,
            created_at=now,
            updated_at=now,
        )
        with self._connect() as connection:
            connection.execute(
                """
                INSERT INTO v2_sessions (session_id, title, created_by, latest_run_id, messages_json, created_at, updated_at, summary)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (session.session_id, session.title, session.created_by, session.latest_run_id, "[]", now, now, session.summary),
            )
        return session

    def get_session(self, session_id: str) -> SessionDetail | None:
        with self._connect() as connection:
            row = connection.execute(
                """
                SELECT session_id, title, created_by, latest_run_id, messages_json, created_at, updated_at, summary
                FROM v2_sessions
                WHERE session_id = ?
                """,
                (session_id,),
            ).fetchone()
        if row is None:
            return None
        return self._session_from_row(row)

    def list_sessions(self) -> list[SessionDetail]:
        with self._connect() as connection:
            rows = connection.execute(
                """
                SELECT session_id, title, created_by, latest_run_id, messages_json, created_at, updated_at, summary
                FROM v2_sessions
                ORDER BY updated_at DESC, rowid ASC
                """
            ).fetchall()
        return [self._session_from_row(row) for row in rows]

    def save_session(self, session: SessionDetail) -> None:
        now = datetime.now(timezone.utc).isoformat()
        session.updated_at = now
        with self._connect() as connection:
            connection.execute(
                """
                UPDATE v2_sessions
                SET title = ?, created_by = ?, latest_run_id = ?, messages_json = ?, updated_at = ?, summary = ?
                WHERE session_id = ?
                """,
                (
                    session.title,
                    session.created_by,
                    session.latest_run_id,
                    self._dump_messages(session.messages),
                    now,
                    session.summary,
                    session.session_id,
                ),
            )

    def delete_session(self, session_id: str) -> None:
        with self._connect() as connection:
            connection.execute("DELETE FROM v2_sessions WHERE session_id = ?", (session_id,))
            connection.execute("DELETE FROM v2_runs WHERE session_id = ?", (session_id,))

    def save_run(self, run: RunDetail) -> None:
        payload_json = run.model_dump_json()
        with self._connect() as connection:
            connection.execute(
                """
                INSERT INTO v2_runs (run_id, session_id, payload_json)
                VALUES (?, ?, ?)
                ON CONFLICT(run_id) DO UPDATE SET
                    session_id = excluded.session_id,
                    payload_json = excluded.payload_json
                """,
                (run.run_id, run.session_id, payload_json),
            )

    def get_run(self, run_id: str) -> RunDetail | None:
        with self._connect() as connection:
            row = connection.execute(
                """
                SELECT payload_json
                FROM v2_runs
                WHERE run_id = ?
                """,
                (run_id,),
            ).fetchone()
        if row is None:
            return None
        return RunDetail.model_validate_json(row[0])

    def list_runs(self) -> list[RunDetail]:
        with self._connect() as connection:
            rows = connection.execute(
                """
                SELECT payload_json
                FROM v2_runs
                ORDER BY rowid ASC
                """
            ).fetchall()
        return [RunDetail.model_validate_json(row[0]) for row in rows]

    def list_runs_for_session(self, session_id: str) -> list[RunDetail]:
        with self._connect() as connection:
            rows = connection.execute(
                """
                SELECT payload_json
                FROM v2_runs
                WHERE session_id = ?
                ORDER BY rowid ASC
                """,
                (session_id,),
            ).fetchall()
        return [RunDetail.model_validate_json(row[0]) for row in rows]

    def append_message(self, session_id: str, message: SessionMessage) -> None:
        with self._lock:
            session = self.get_session(session_id)
            if session is None:
                raise KeyError(session_id)
            session.messages.append(message)
            self.save_session(session)

    def append_trace(self, run_id: str, event: TraceEventV2) -> None:
        with self._lock:
            run = self.get_run(run_id)
            if run is None:
                raise KeyError(run_id)
            run.trace.append(event)
            self.save_run(run)

    def _initialize_schema(self) -> None:
        with self._connect() as connection:
            connection.execute(
                """
                CREATE TABLE IF NOT EXISTS v2_sessions (
                    session_id TEXT PRIMARY KEY,
                    title TEXT NOT NULL,
                    created_by TEXT,
                    latest_run_id TEXT,
                    messages_json TEXT NOT NULL,
                    created_at TEXT,
                    updated_at TEXT,
                    summary TEXT
                )
                """
            )
            existing_columns = {row[1] for row in connection.execute("PRAGMA table_info(v2_sessions)").fetchall()}
            if "created_at" not in existing_columns:
                connection.execute("ALTER TABLE v2_sessions ADD COLUMN created_at TEXT")
            if "updated_at" not in existing_columns:
                connection.execute("ALTER TABLE v2_sessions ADD COLUMN updated_at TEXT")
            if "summary" not in existing_columns:
                connection.execute("ALTER TABLE v2_sessions ADD COLUMN summary TEXT")
            connection.execute(
                """
                CREATE TABLE IF NOT EXISTS v2_runs (
                    run_id TEXT PRIMARY KEY,
                    session_id TEXT NOT NULL,
                    payload_json TEXT NOT NULL
                )
                """
            )
            existing_run_columns = {row[1] for row in connection.execute("PRAGMA table_info(v2_runs)").fetchall()}
            if "session_id" not in existing_run_columns:
                connection.execute("ALTER TABLE v2_runs ADD COLUMN session_id TEXT NOT NULL DEFAULT ''")
            run_indexes = {row[1] for row in connection.execute("PRAGMA index_list(v2_runs)").fetchall()}
            if "idx_v2_runs_session_id" not in run_indexes:
                connection.execute("CREATE INDEX IF NOT EXISTS idx_v2_runs_session_id ON v2_runs(session_id)")

    def _connect(self) -> sqlite3.Connection:
        connection = sqlite3.connect(self._database_path, check_same_thread=False)
        connection.execute("PRAGMA journal_mode=WAL")
        connection.execute("PRAGMA synchronous=NORMAL")
        connection.execute("PRAGMA busy_timeout=5000")
        connection.execute("PRAGMA foreign_keys=ON")
        return connection

    @staticmethod
    def _dump_messages(messages: list[SessionMessage]) -> str:
        return json.dumps([message.model_dump() for message in messages], ensure_ascii=False)

    @staticmethod
    def _session_from_row(row: sqlite3.Row | tuple[object, ...]) -> SessionDetail:
        session_id, title, created_by, latest_run_id, messages_json, created_at, updated_at, *rest = row
        summary = rest[0] if rest else None
        messages = [SessionMessage.model_validate(item) for item in json.loads(messages_json)]
        return SessionDetail(
            session_id=session_id,
            title=title,
            created_by=created_by,
            latest_run_id=latest_run_id,
            messages=messages,
            created_at=created_at,
            updated_at=updated_at,
            summary=summary,
        )
