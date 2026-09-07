"""SQLite-backed submission store for the canonical product protocol.

Each submission wraps an engine stream execution and provides persisted,
fan-out SSE events for the frontend.

Lifecycle:
  1. create_submission() → submission in "queued" state (returned to client)
  2. launch worker thread → engine.stream() → translate + push to queue
  3. GET /events drains the queue as SSE
  4. close_submission() sends None sentinel → SSE stream ends

Persistence:
  - Submission metadata is stored in SQLite (product_submissions table).
  - SSE events are persisted and replayable after reconnect/restart.
  - Per-connection queues remain in-memory and are released on disconnect.
  - On restart, existing submissions are lazy-loaded from SQLite.
"""

from __future__ import annotations

import asyncio
import json
import logging
import threading
from datetime import datetime, timezone
from uuid import uuid4

from schemas.canonical import SubmissionResponse, SubmissionStage, SubmissionStatus
from runtime.db import open_db

logger = logging.getLogger(__name__)


class SubmissionStore:
    """SQLite-backed store for Submission resources with per-submission SSE queues."""

    def __init__(self, db_path: str | None = None, loop: asyncio.AbstractEventLoop | None = None) -> None:
        self._submissions: dict[str, SubmissionResponse] = {}
        self._subscribers: dict[str, set[asyncio.Queue]] = {}
        self._legacy_queues: dict[str, asyncio.Queue] = {}
        self._closed_streams: set[str] = set()
        self._cancellation_events: dict[str, threading.Event] = {}
        self._lock = threading.RLock()
        self._db = open_db(db_path)
        self._loop = loop
        self._initialize_schema()

    def _initialize_schema(self) -> None:
        self._db.execute("""
            CREATE TABLE IF NOT EXISTS product_submissions (
                submission_id TEXT PRIMARY KEY,
                conversation_id TEXT NOT NULL,
                run_id TEXT,
                status TEXT NOT NULL DEFAULT 'queued',
                stage TEXT NOT NULL DEFAULT 'accepted',
                created_at TEXT NOT NULL,
                completed_at TEXT,
                payload_json TEXT NOT NULL
            )
        """)
        self._db.execute("""
            CREATE TABLE IF NOT EXISTS product_submission_events (
                submission_id TEXT NOT NULL,
                sequence INTEGER NOT NULL,
                payload_json TEXT NOT NULL,
                created_at TEXT NOT NULL,
                PRIMARY KEY (submission_id, sequence)
            )
        """)
        self._db.commit()

    # ── Submission CRUD ──

    def create_submission(self, *, conversation_id: str) -> SubmissionResponse:
        """Create a new submission in 'queued' state and persist to SQLite."""
        submission_id = str(uuid4())
        now = datetime.now(timezone.utc).isoformat()
        submission = SubmissionResponse(
            submission_id=submission_id,
            conversation_id=conversation_id,
            run_id=None,
            status="queued",
            stage="accepted",
            created_at=now,
            completed_at=None,
        )
        with self._lock:
            self._submissions[submission_id] = submission
            self._cancellation_events[submission_id] = threading.Event()
            self._db.execute(
                "INSERT INTO product_submissions (submission_id, conversation_id, status, stage, created_at, payload_json) VALUES (?,?,?,?,?,?)",
                (submission_id, conversation_id, submission.status, submission.stage, now, submission.model_dump_json()),
            )
            self._db.commit()
        logger.info("submission_created | submission_id=%s | conversation_id=%s", submission_id, conversation_id)
        return submission

    def get_submission(self, submission_id: str) -> SubmissionResponse | None:
        """Return the submission or None.

        Checks in-memory cache first; falls back to SQLite for submissions
        created before a service restart (lazy load).
        """
        with self._lock:
            if submission_id in self._submissions:
                return self._submissions[submission_id]
            # Lazy load from SQLite
            row = self._db.execute(
                "SELECT payload_json FROM product_submissions WHERE submission_id=?",
                (submission_id,),
            ).fetchone()
            if row is None:
                return None
            sub = SubmissionResponse.model_validate_json(row["payload_json"])
            self._submissions[submission_id] = sub
            return sub

    def update_submission(
        self,
        submission_id: str,
        *,
        run_id: str | None = None,
        status: SubmissionStatus | None = None,
        stage: SubmissionStage | None = None,
        completed_at: str | None = None,
    ) -> SubmissionResponse | None:
        """Update fields on the submission in place (thread-safe) and persist.

        Returns the updated submission or None if not found.
        """
        with self._lock:
            sub = self._submissions.get(submission_id)
            if sub is None:
                # Lazy load from SQLite
                row = self._db.execute(
                    "SELECT payload_json FROM product_submissions WHERE submission_id=?",
                    (submission_id,),
                ).fetchone()
                if row is None:
                    return None
                sub = SubmissionResponse.model_validate_json(row["payload_json"])

            if sub.status in ("completed", "failed", "cancelled"):
                logger.debug(
                    "submission_terminal_update_ignored | submission_id=%s | status=%s | fields=%s",
                    submission_id,
                    sub.status,
                    [name for name, value in {
                        "run_id": run_id, "status": status, "stage": stage, "completed_at": completed_at,
                    }.items() if value is not None],
                )
                self._submissions[submission_id] = sub
                return sub

            updates = {
                name: value for name, value in {
                    "run_id": run_id,
                    "status": status,
                    "stage": stage,
                    "completed_at": completed_at,
                }.items() if value is not None
            }
            updated = SubmissionResponse.model_validate({**sub.model_dump(), **updates})
            self._submissions[submission_id] = updated
            self._db.execute(
                """UPDATE product_submissions
                   SET run_id=?, status=?, stage=?, completed_at=?, payload_json=?
                   WHERE submission_id=?""",
                (updated.run_id, updated.status, updated.stage, updated.completed_at,
                 updated.model_dump_json(), submission_id),
            )
            self._db.commit()
            return updated

    # ── Event queue management ──

    def bind_loop(self, loop: asyncio.AbstractEventLoop) -> None:
        if loop.is_closed():
            raise RuntimeError("Cannot bind SubmissionStore to a closed event loop")
        with self._lock:
            self._loop = loop

    def get_event_queue(self, submission_id: str) -> asyncio.Queue | None:
        """Backward-compatible single subscriber used by older callers and tests."""
        with self._lock:
            if self.get_submission(submission_id) is None:
                return None
            queue = self._legacy_queues.get(submission_id)
            if queue is None:
                queue = asyncio.Queue()
                self._legacy_queues[submission_id] = queue
                self._subscribers.setdefault(submission_id, set()).add(queue)
                if submission_id in self._closed_streams:
                    queue.put_nowait(None)
            return queue

    def subscribe(self, submission_id: str) -> asyncio.Queue | None:
        """Create an isolated live queue for a single SSE connection."""
        with self._lock:
            if self.get_submission(submission_id) is None:
                return None
            queue: asyncio.Queue = asyncio.Queue()
            self._subscribers.setdefault(submission_id, set()).add(queue)
            if submission_id in self._closed_streams:
                queue.put_nowait(None)
            return queue

    def unsubscribe(self, submission_id: str, queue: asyncio.Queue) -> None:
        with self._lock:
            subscribers = self._subscribers.get(submission_id)
            if subscribers is not None:
                subscribers.discard(queue)
                if not subscribers:
                    self._subscribers.pop(submission_id, None)
            if self._legacy_queues.get(submission_id) is queue:
                self._legacy_queues.pop(submission_id, None)

    def push_event(self, submission_id: str, event_data: dict) -> None:
        """Push a canonical SSE event dict onto the submission's queue.

        Called from the worker thread (non-async).  Uses
        ``call_soon_threadsafe`` so the asyncio event loop picks it up.
        """
        with self._lock:
            if self.get_submission(submission_id) is None:
                return
            persisted = self._persist_event_locked(submission_id, event_data)
            self._db.commit()
            queues = tuple(self._subscribers.get(submission_id, ()))
            loop = self._loop
        if loop is None or loop.is_closed():
            logger.debug(
                "submission_event_persisted_without_live_delivery: %s",
                event_data.get("event", event_data),
            )
            return
        for queue in queues:
            loop.call_soon_threadsafe(queue.put_nowait, dict(persisted))

    def close_submission(self, submission_id: str) -> None:
        """Signal that the SSE stream is complete by pushing a ``None`` sentinel."""
        with self._lock:
            self._closed_streams.add(submission_id)
            queues = tuple(self._subscribers.get(submission_id, ()))
            loop = self._loop
        if loop is not None and not loop.is_closed():
            for queue in queues:
                loop.call_soon_threadsafe(queue.put_nowait, None)

    def list_events(self, submission_id: str, *, after_sequence: int = 0) -> list[dict]:
        rows = self._db.execute(
            "SELECT payload_json FROM product_submission_events "
            "WHERE submission_id=? AND sequence>? ORDER BY sequence ASC",
            (submission_id, max(0, int(after_sequence))),
        ).fetchall()
        return [json.loads(row["payload_json"]) for row in rows]

    def is_terminal(self, submission_id: str) -> bool:
        submission = self.get_submission(submission_id)
        return submission is not None and submission.status in ("completed", "failed", "cancelled")

    def cleanup_terminal_resources(self, *, retention_seconds: int = 300, now: datetime | None = None) -> int:
        """Release only expired in-memory stream resources; persisted history is retained."""
        cutoff = (now or datetime.now(timezone.utc)).timestamp() - max(0, retention_seconds)
        released = 0
        with self._lock:
            for submission in self.list_submissions():
                if submission.status not in ("completed", "failed", "cancelled") or not submission.completed_at:
                    continue
                try:
                    completed_at = datetime.fromisoformat(submission.completed_at).timestamp()
                except ValueError:
                    continue
                if completed_at > cutoff:
                    continue
                self._subscribers.pop(submission.submission_id, None)
                self._legacy_queues.pop(submission.submission_id, None)
                self._cancellation_events.pop(submission.submission_id, None)
                self._closed_streams.discard(submission.submission_id)
                released += 1
        return released

    # ── Cancel ──

    def get_cancellation_event(self, submission_id: str) -> threading.Event | None:
        """Return the cooperative cancellation event for an active submission."""
        with self._lock:
            return self._cancellation_events.get(submission_id)

    def is_cancel_requested(self, submission_id: str) -> bool:
        event = self.get_cancellation_event(submission_id)
        return event.is_set() if event is not None else False

    def cancel_submission(self, submission_id: str) -> bool:
        """Attempt to cancel a submission.  Returns True if cancellation was accepted."""
        sub = self.get_submission(submission_id)
        if sub is None or sub.status in ("completed", "failed", "cancelled"):
            return False
        event = self.get_cancellation_event(submission_id)
        if event is None:
            return False
        event.set()
        self.update_submission(submission_id, status="cancelling", stage="cancelling")
        return True

    # ── List ──

    def list_submissions(self, conversation_id: str | None = None) -> list[SubmissionResponse]:
        """Return all submissions, optionally filtered by conversation.

        Queries SQLite directly to survive restarts (in-memory cache may be empty).
        """
        rows = self._db.execute(
            "SELECT payload_json FROM product_submissions"
            + (" WHERE conversation_id=?" if conversation_id else ""),
            (conversation_id,) if conversation_id else (),
        ).fetchall()
        return [SubmissionResponse.model_validate_json(r["payload_json"]) for r in rows]

    def close(self) -> None:
        with self._lock:
            self._subscribers.clear()
            self._legacy_queues.clear()
            self._closed_streams.clear()
            self._cancellation_events.clear()
            self._db.close()

    def _persist_event_locked(self, submission_id: str, event_data: dict) -> dict:
        row = self._db.execute(
            "SELECT COALESCE(MAX(sequence), 0) + 1 AS next_sequence "
            "FROM product_submission_events WHERE submission_id=?",
            (submission_id,),
        ).fetchone()
        payload = dict(event_data)
        payload["sequence"] = int(row["next_sequence"])
        self._db.execute(
            "INSERT INTO product_submission_events (submission_id, sequence, payload_json, created_at) "
            "VALUES (?, ?, ?, ?)",
            (submission_id, payload["sequence"], json.dumps(payload, ensure_ascii=False),
             str(payload.get("timestamp") or datetime.now(timezone.utc).isoformat())),
        )
        return payload
