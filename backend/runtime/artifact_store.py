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
import hashlib
import json
import mimetypes
import threading
import uuid as _uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from pydantic import BaseModel, Field

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
    checksum: str | None = None
    size_bytes: int | None = None
    content_type: str | None = None
    provenance: dict[str, Any] = Field(default_factory=dict)
    version: int = 1
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
        content_path = getattr(artifact, "uri", None)
        content_inline = getattr(artifact, "content", None)
        checksum, size_bytes = self._content_fingerprint(content_path, content_inline)
        content_type = (
            getattr(artifact, "content_type", None)
            or self._infer_content_type(content_path, artifact.artifact_type, content_inline)
        )
        provenance = self._provenance(artifact, content_path)
        record = ArtifactRecord(
            artifact_id="art_" + _uuid.uuid4().hex[:8],
            run_id=run_id,
            pack_name=artifact.pack_name,
            artifact_type=artifact.artifact_type,
            kind=artifact.artifact_type,
            title=artifact.title,
            content_path=content_path,
            content_inline=content_inline,
            checksum=checksum,
            size_bytes=size_bytes,
            content_type=content_type,
            provenance=provenance,
            created_at=datetime.now(timezone.utc).isoformat(),
        )
        with self._lock:
            existing = self._find_same_content_locked(record)
            if existing is not None:
                return existing.artifact_id
            record.version = self._next_version_locked(record)
            artifact_id = record.artifact_id
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

    @staticmethod
    def _content_fingerprint(content_path: str | None, content_inline: str | None) -> tuple[str | None, int | None]:
        """Return a SHA-256 and byte count without following arbitrary URIs."""
        if content_inline is not None:
            raw = content_inline.encode("utf-8")
            return hashlib.sha256(raw).hexdigest(), len(raw)
        if not content_path:
            return None, None
        try:
            path = Path(content_path)
            if not path.is_file():
                return None, None
            digest = hashlib.sha256()
            with path.open("rb") as handle:
                for chunk in iter(lambda: handle.read(1024 * 1024), b""):
                    digest.update(chunk)
            return digest.hexdigest(), path.stat().st_size
        except OSError:
            logger.warning("artifact_fingerprint_failed | content_path=%s", content_path, exc_info=True)
            return None, None

    @staticmethod
    def _infer_content_type(content_path: str | None, artifact_type: str, content_inline: str | None) -> str | None:
        if content_path:
            guessed, _ = mimetypes.guess_type(content_path)
            if guessed:
                return guessed
        if artifact_type == "lai_html_report":
            return "text/html"
        if content_inline is not None:
            return "text/plain; charset=utf-8"
        return None

    @staticmethod
    def _provenance(artifact, content_path: str | None) -> dict[str, Any]:
        supplied = getattr(artifact, "provenance", None)
        if not isinstance(supplied, dict):
            supplied = {}
        # JSON round-trip rejects non-persistable values supplied by a tool.
        normalized = json.loads(json.dumps(supplied, default=str))
        return {
            "registration_source": "runtime_pack",
            "source_uri": content_path,
            "pack_name": artifact.pack_name,
            **normalized,
        }

    def _records_for_run_locked(self, run_id: str) -> list[ArtifactRecord]:
        rows = self._db.execute(
            "SELECT payload_json FROM product_artifacts WHERE run_id=?", (run_id,)
        ).fetchall()
        return [ArtifactRecord.model_validate_json(row["payload_json"]) for row in rows]

    def _find_same_content_locked(self, candidate: ArtifactRecord) -> ArtifactRecord | None:
        if candidate.checksum is None:
            return None
        for existing in self._records_for_run_locked(candidate.run_id):
            if (
                existing.pack_name == candidate.pack_name
                and existing.artifact_type == candidate.artifact_type
                and existing.content_path == candidate.content_path
                and existing.checksum == candidate.checksum
            ):
                self._artifacts[existing.artifact_id] = existing
                return existing
        return None

    def _next_version_locked(self, candidate: ArtifactRecord) -> int:
        versions = [
            record.version
            for record in self._records_for_run_locked(candidate.run_id)
            if (
                record.pack_name == candidate.pack_name
                and record.artifact_type == candidate.artifact_type
                and record.content_path == candidate.content_path
            )
        ]
        return max(versions, default=0) + 1

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

    def delete_registration(self, artifact_id: str) -> bool:
        """Remove metadata only; physical content is retained for explicit archival handling."""
        with self._lock:
            cursor = self._db.execute(
                "DELETE FROM product_artifacts WHERE artifact_id=?", (artifact_id,)
            )
            self._db.commit()
            self._artifacts.pop(artifact_id, None)
            return cursor.rowcount > 0

    def close(self) -> None:
        with self._lock:
            self._db.close()
