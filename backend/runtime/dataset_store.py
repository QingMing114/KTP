"""SQLite-backed dataset registry for the canonical product protocol.

Datasets are local file references registered with a stable *dataset_id*.
After registration, clients reference datasets by id, not by local path.

Rules (from canonical_api_spec.md):
  - v1 only supports source.kind = "local_path"
  - Registration stores metadata only, never copies/moves the source file
  - DELETE removes the registry entry, not the source file

Persistence:
  - Dataset metadata is stored in SQLite (product_datasets table).
  - Idempotency keys are enforced via SQLite UNIQUE index.
  - On restart, datasets are lazy-loaded from SQLite.
"""

from __future__ import annotations

import logging
import threading
from datetime import datetime, timezone
from uuid import uuid4

from runtime.db import open_db
from schemas.canonical import CanonicalDataset, DatasetSource

logger = logging.getLogger(__name__)


class DatasetStore:
    """SQLite-backed dataset registry with idempotency-key support."""

    def __init__(self, db_path: str | None = None) -> None:
        self._datasets: dict[str, CanonicalDataset] = {}
        self._lock = threading.Lock()
        self._db = open_db(db_path)
        self._initialize_schema()

    def _initialize_schema(self) -> None:
        self._db.execute("""
            CREATE TABLE IF NOT EXISTS product_datasets (
                dataset_id TEXT PRIMARY KEY,
                idempotency_key TEXT,
                payload_json TEXT NOT NULL
            )
        """)
        self._db.execute("""
            CREATE UNIQUE INDEX IF NOT EXISTS idx_datasets_idempotency
                ON product_datasets(idempotency_key)
                WHERE idempotency_key IS NOT NULL
        """)
        self._db.commit()

    # ── CRUD ──

    def create_dataset(
        self,
        *,
        source: DatasetSource,
        display_name: str,
        defaults: dict | None = None,
        metadata: dict | None = None,
        tags: list[str] | None = None,
        idempotency_key: str | None = None,
    ) -> CanonicalDataset:
        """Register a new dataset.  Returns existing if idempotency_key matches."""
        # Idempotency check
        if idempotency_key:
            with self._lock:
                row = self._db.execute(
                    "SELECT payload_json FROM product_datasets WHERE idempotency_key=?",
                    (idempotency_key,),
                ).fetchone()
                if row:
                    existing = CanonicalDataset.model_validate_json(row["payload_json"])
                    logger.info("dataset_idempotent_hit | key=%s | dataset_id=%s", idempotency_key, existing.dataset_id)
                    # Also cache in memory for fast subsequent access
                    self._datasets[existing.dataset_id] = existing
                    return existing

        dataset_id = str(uuid4())
        now = datetime.now(timezone.utc).isoformat()
        dataset = CanonicalDataset(
            dataset_id=dataset_id,
            source=source,
            display_name=display_name,
            defaults=defaults or {},
            metadata=metadata or {},
            tags=tags or [],
            created_at=now,
        )
        with self._lock:
            self._datasets[dataset_id] = dataset
            self._db.execute(
                "INSERT INTO product_datasets (dataset_id, idempotency_key, payload_json) VALUES (?,?,?)",
                (dataset_id, idempotency_key, dataset.model_dump_json()),
            )
            self._db.commit()
        logger.info("dataset_created | dataset_id=%s | display_name=%s", dataset_id, display_name)
        return dataset

    def get_dataset(self, dataset_id: str) -> CanonicalDataset | None:
        """Return the dataset or None.

        Checks in-memory cache first; falls back to SQLite lazy load.
        """
        with self._lock:
            existing = self._datasets.get(dataset_id)
            if existing is not None:
                return existing
            # Lazy load from SQLite
            row = self._db.execute(
                "SELECT payload_json FROM product_datasets WHERE dataset_id=?",
                (dataset_id,),
            ).fetchone()
            if row is None:
                return None
            ds = CanonicalDataset.model_validate_json(row["payload_json"])
            self._datasets[dataset_id] = ds
            return ds

    def list_datasets(self) -> list[CanonicalDataset]:
        """Return all registered datasets.

        Queries SQLite directly to survive restarts (in-memory cache may be empty).
        """
        rows = self._db.execute(
            "SELECT payload_json FROM product_datasets",
        ).fetchall()
        datasets = [CanonicalDataset.model_validate_json(r["payload_json"]) for r in rows]
        # Warm the in-memory cache
        with self._lock:
            for ds in datasets:
                self._datasets[ds.dataset_id] = ds
        return datasets

    def update_dataset(self, dataset_id: str, **fields) -> CanonicalDataset | None:
        """Patch mutable fields on a dataset. Returns updated or None if not found."""
        with self._lock:
            existing = self._datasets.get(dataset_id)
            if existing is None:
                # Try lazy load
                row = self._db.execute(
                    "SELECT payload_json FROM product_datasets WHERE dataset_id=?",
                    (dataset_id,),
                ).fetchone()
                if row is None:
                    return None
                existing = CanonicalDataset.model_validate_json(row["payload_json"])

            updated = existing.model_copy(update={k: v for k, v in fields.items() if v is not None})
            self._datasets[dataset_id] = updated
            # Re-read idempotency_key from DB (not in the model fields)
            row = self._db.execute(
                "SELECT idempotency_key FROM product_datasets WHERE dataset_id=?",
                (dataset_id,),
            ).fetchone()
            idem_key = row["idempotency_key"] if row else None
            self._db.execute(
                "UPDATE product_datasets SET payload_json=? WHERE dataset_id=?",
                (updated.model_dump_json(), dataset_id),
            )
            self._db.commit()
            return updated

    def delete_dataset(self, dataset_id: str) -> bool:
        """Remove a dataset registration.  Does NOT delete the source file."""
        with self._lock:
            if dataset_id not in self._datasets:
                # Check SQLite directly
                row = self._db.execute(
                    "SELECT 1 FROM product_datasets WHERE dataset_id=?", (dataset_id,)
                ).fetchone()
                if row is None:
                    return False
            self._datasets.pop(dataset_id, None)
            self._db.execute("DELETE FROM product_datasets WHERE dataset_id=?", (dataset_id,))
            self._db.commit()
            return True

    # ── Idempotency conflict detection ──

    def check_idempotency_conflict(self, key: str) -> str | None:
        """Return the existing dataset_id for *key*, or None.

        The caller should compare the request body against the stored dataset
        and raise 409 IDEMPOTENCY_CONFLICT if they differ.
        """
        row = self._db.execute(
            "SELECT dataset_id FROM product_datasets WHERE idempotency_key=?",
            (key,),
        ).fetchone()
        return row["dataset_id"] if row else None
