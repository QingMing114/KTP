"""SQLite-backed submission store for the canonical product protocol.

Each submission wraps an engine stream execution and provides
an asyncio.Queue-backed SSE event stream for the frontend.

Lifecycle:
  1. create_submission() → submission in "queued" state (returned to client)
  2. launch worker thread → engine.stream() → translate + push to queue
  3. GET /events drains the queue as SSE
  4. close_submission() sends None sentinel → SSE stream ends

Persistence:
  - Submission metadata is stored in SQLite (product_submissions table).
  - SSE event queues remain in-memory (connection-level state).
  - On restart, existing submissions are lazy-loaded from SQLite.
"""

from __future__ import annotations

import asyncio
import json
import logging
import threading
from datetime import datetime, timezone
from uuid import uuid4

from schemas.canonical import SubmissionResponse
from runtime.db import open_db

logger = logging.getLogger(__name__)


class SubmissionStore:
    """SQLite-backed store for Submission resources with per-submission SSE queues."""

    def __init__(self, db_path: str | None = None, loop: asyncio.AbstractEventLoop | None = None) -> None:
        self._submissions: dict[str, SubmissionResponse] = {}
        self._event_queues: dict[str, asyncio.Queue] = {}
        self._lock = threading.Lock()
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
            self._event_queues[submission_id] = asyncio.Queue()
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

    def update_submission(self, submission_id: str, **fields) -> SubmissionResponse | None:
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

            updated = sub.model_copy(update=fields)
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

    def get_event_queue(self, submission_id: str) -> asyncio.Queue | None:
        """Return the SSE event queue for *submission_id*, or None."""
        with self._lock:
            return self._event_queues.get(submission_id)

    def push_event(self, submission_id: str, event_data: dict) -> None:
        """Push a canonical SSE event dict onto the submission's queue.

        Called from the worker thread (non-async).  Uses
        ``call_soon_threadsafe`` so the asyncio event loop picks it up.
        """
        queue = self.get_event_queue(submission_id)
        if queue is None:
            return
        if self._loop is None:
            logger.warning(
                "push_event: no event loop stored, event dropped: %s",
                event_data.get("event", event_data),
            )
            return
        self._loop.call_soon_threadsafe(queue.put_nowait, event_data)

    def close_submission(self, submission_id: str) -> None:
        """Signal that the SSE stream is complete by pushing a ``None`` sentinel."""
        queue = self.get_event_queue(submission_id)
        if queue is None:
            return
        if self._loop is not None:
            self._loop.call_soon_threadsafe(queue.put_nowait, None)

    # ── Cancel ──

    def cancel_submission(self, submission_id: str) -> bool:
        """Attempt to cancel a submission.  Returns True if cancellation was accepted."""
        sub = self.get_submission(submission_id)
        if sub is None or sub.status in ("completed", "failed", "cancelled"):
            return False
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
