"""SQLite-backed artifact store for the canonical product protocol.

Provides stable, UUID-based artifact IDs that are independent of enumeration
order.  Tools generate ``PackArtifactView`` objects during run execution;
the router registers them into the ArtifactStore at run completion, mapping
each to a stable ``art_{8hex}`` identifier.

Persistence:
  - Artifact metadata is stored in SQLite (product_artifacts table).
  - On restart, artifacts are lazy-loaded from SQLite.
"""

from __future__ import annotations

import logging
import threading
import uuid as _uuid
from datetime import datetime, timezone

from pydantic import BaseModel

from runtime.db import open_db

logger = logging.getLogger(__name__)


class ArtifactRecord(BaseModel):
    """A registered artifact with a stable identifier."""

    artifact_id: str          # "art_{uuid4 hex[:8]}"
    run_id: str               # parent run
    pack_name: str
    artifact_type: str        # "lai_html_report" etc.
    kind: str                 # same as artifact_type — canonical field name
    title: str
    content_path: str | None = None   # file-system path or URI (e.g. /v2/reports/xxx.html)
    content_inline: str | None = None # inline text content
    created_at: str = ""


class ArtifactStore:
    """SQLite-backed registry of artifacts keyed by stable UUID."""

    def __init__(self, db_path: str | None = None) -> None:
        self._artifacts: dict[str, ArtifactRecord] = {}
        self._lock = threading.Lock()
        self._db = open_db(db_path)
        self._initialize_schema()

    def _initialize_schema(self) -> None:
        self._db.execute("""
            CREATE TABLE IF NOT EXISTS product_artifacts (
                artifact_id TEXT PRIMARY KEY,
                run_id TEXT NOT NULL,
                payload_json TEXT NOT NULL
            )
        """)
        self._db.execute(
            "CREATE INDEX IF NOT EXISTS idx_artifacts_run_id ON product_artifacts(run_id)"
        )
        self._db.commit()

    # ── Registration ──

    def register(self, run_id: str, artifact) -> str:
        """Register a ``PackArtifactView`` and return a stable ``artifact_id``.

        *artifact* must have at minimum: ``pack_name``, ``artifact_type``,
        ``title``, and optionally ``uri`` / ``content``.
        """
        artifact_id = "art_" + _uuid.uuid4().hex[:8]
        record = ArtifactRecord(
            artifact_id=artifact_id,
            run_id=run_id,
            pack_name=artifact.pack_name,
            artifact_type=artifact.artifact_type,
            kind=artifact.artifact_type,
            title=artifact.title,
            content_path=getattr(artifact, "uri", None),
            content_inline=getattr(artifact, "content", None),
            created_at=datetime.now(timezone.utc).isoformat(),
        )
        with self._lock:
            self._artifacts[artifact_id] = record
            self._db.execute(
                "INSERT OR IGNORE INTO product_artifacts (artifact_id, run_id, payload_json) VALUES (?,?,?)",
                (artifact_id, run_id, record.model_dump_json()),
            )
            self._db.commit()
        logger.debug(
            "artifact_registered | artifact_id=%s | run_id=%s | type=%s",
            artifact_id, run_id, artifact.artifact_type,
        )
        return artifact_id

    # ── Lookup ──

    def get(self, artifact_id: str) -> ArtifactRecord | None:
        """Return the record for *artifact_id* or ``None``.

        Checks in-memory cache first; falls back to SQLite lazy load.
        """
        with self._lock:
            existing = self._artifacts.get(artifact_id)
            if existing is not None:
                return existing
            # Lazy load from SQLite
            row = self._db.execute(
                "SELECT payload_json FROM product_artifacts WHERE artifact_id=?",
                (artifact_id,),
            ).fetchone()
            if row is None:
                return None
            rec = ArtifactRecord.model_validate_json(row["payload_json"])
            self._artifacts[artifact_id] = rec
            return rec

    def list_by_run(self, run_id: str) -> list[ArtifactRecord]:
        """Return all artifacts belonging to *run_id*.

        Queries SQLite directly to survive restarts.
        """
        rows = self._db.execute(
            "SELECT payload_json FROM product_artifacts WHERE run_id=?", (run_id,)
        ).fetchall()
        records = [ArtifactRecord.model_validate_json(r["payload_json"]) for r in rows]
        # Warm the in-memory cache
        with self._lock:
            for rec in records:
                self._artifacts[rec.artifact_id] = rec
        return records

    def list_all(self) -> list[ArtifactRecord]:
        """Return every registered artifact.

        Queries SQLite directly to survive restarts.
        """
        rows = self._db.execute(
            "SELECT payload_json FROM product_artifacts"
        ).fetchall()
        records = [ArtifactRecord.model_validate_json(r["payload_json"]) for r in rows]
        # Warm the in-memory cache
        with self._lock:
            for rec in records:
                self._artifacts[rec.artifact_id] = rec
        return records
