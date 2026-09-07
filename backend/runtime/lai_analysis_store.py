"""SQLite-backed state and replayable SSE events for typed LAI analyses."""

from __future__ import annotations

import asyncio
import json
import logging
import threading
from datetime import datetime, timezone
from uuid import uuid4

from runtime.db import open_db
from schemas.spatial import CreateLaiAnalysisRequest, LaiAnalysisSummary


logger = logging.getLogger(__name__)


_ACTIVE_STATUSES = {"queued", "running"}
_TERMINAL_STATUSES = {"completed", "failed", "cancelled"}


class LaiAnalysisStore:
    def __init__(self, db_path: str | None = None, loop: asyncio.AbstractEventLoop | None = None) -> None:
        self._db = open_db(db_path)
        self._loop = loop
        self._lock = threading.RLock()
        self._items: dict[str, LaiAnalysisSummary] = {}
        self._subscribers: dict[str, set[asyncio.Queue]] = {}
        self._legacy_queues: dict[str, asyncio.Queue] = {}
        self._initialize_schema()
        self._recover_interrupted_analyses()

    def _initialize_schema(self) -> None:
        self._db.execute("""CREATE TABLE IF NOT EXISTS product_lai_analyses (
            analysis_id TEXT PRIMARY KEY, payload_json TEXT NOT NULL)""")
        self._db.execute("""CREATE TABLE IF NOT EXISTS product_lai_analysis_events (
            analysis_id TEXT NOT NULL,
            sequence INTEGER NOT NULL,
            event_id TEXT NOT NULL UNIQUE,
            payload_json TEXT NOT NULL,
            created_at TEXT NOT NULL,
            PRIMARY KEY (analysis_id, sequence)
        )""")
        self._db.execute(
            "CREATE INDEX IF NOT EXISTS idx_lai_events_analysis "
            "ON product_lai_analysis_events(analysis_id, sequence)"
        )
        self._db.commit()

    def _recover_interrupted_analyses(self) -> None:
        """Archive work that cannot survive a process restart as an explicit failure."""
        rows = self._db.execute("SELECT payload_json FROM product_lai_analyses").fetchall()
        timestamp = datetime.now(timezone.utc).isoformat()
        with self._lock:
            for row in rows:
                try:
                    item = self._load_summary(row["payload_json"])
                except ValueError as exc:
                    logger.warning("lai_analysis_invalid_persisted_record_skipped | error=%s", exc)
                    continue
                if item.status not in _ACTIVE_STATUSES:
                    continue
                detail = "服务重启中断了正在执行的 LAI 分析，请重新提交任务。"
                recovered = LaiAnalysisSummary.model_validate({**item.model_dump(), **{
                    "status": "failed",
                    "stage": "failed",
                    "detail": detail,
                    "updated_at": timestamp,
                    "completed_at": timestamp,
                    "result": {"error": detail, "reason": "service_restarted"},
                }})
                self._items[item.analysis_id] = recovered
                self._save_locked(recovered)
                self._persist_event_locked(item.analysis_id, {
                    "event_id": str(uuid4()),
                    "analysis_id": item.analysis_id,
                    "kind": "error",
                    "stage": "failed",
                    "detail": detail,
                    "progress_percent": item.progress_percent,
                    "data": {"reason": "service_restarted"},
                    "timestamp": timestamp,
                })
            self._db.commit()

    def create(self, body: CreateLaiAnalysisRequest) -> LaiAnalysisSummary:
        try:
            self.bind_loop(asyncio.get_running_loop())
        except RuntimeError:
            # Synchronous callers can still use persistence without SSE delivery.
            pass
        now = datetime.now(timezone.utc).isoformat()
        item = LaiAnalysisSummary(
            analysis_id=str(uuid4()),
            status="queued",
            stage="accepted",
            aoi=body.aoi,
            farm_id=body.farm_id,
            imagery_item_id=body.imagery_item_id,
            imagery_snapshot=body.imagery_snapshot,
            parameters=body.parameters,
            created_at=now,
            updated_at=now,
            detail="任务已创建，等待影像准备",
        )
        with self._lock:
            self._items[item.analysis_id] = item
            self._save_locked(item)
            self._db.commit()
        return item

    def get(self, analysis_id: str) -> LaiAnalysisSummary | None:
        with self._lock:
            if analysis_id in self._items:
                return self._items[analysis_id]
            row = self._db.execute(
                "SELECT payload_json FROM product_lai_analyses WHERE analysis_id=?",
                (analysis_id,),
            ).fetchone()
            if row is None:
                return None
            try:
                item = self._load_summary(row["payload_json"])
            except ValueError as exc:
                logger.warning(
                    "lai_analysis_invalid_persisted_record | analysis_id=%s | error=%s",
                    analysis_id,
                    exc,
                )
                return None
            self._items[analysis_id] = item
            return item

    @staticmethod
    def _load_summary(payload_json: str) -> LaiAnalysisSummary:
        """Load current records and normalize the pre-Polygon-ring AOI encoding."""
        payload = json.loads(payload_json)
        aoi = payload.get("aoi") if isinstance(payload, dict) else None
        geometry = aoi.get("geometry") if isinstance(aoi, dict) else None
        coordinates = geometry.get("coordinates") if isinstance(geometry, dict) else None
        if (
            isinstance(coordinates, list)
            and coordinates
            and isinstance(coordinates[0], list)
            and coordinates[0]
            and isinstance(coordinates[0][0], (int, float))
        ):
            geometry["coordinates"] = [coordinates]
            aoi["area_hectares"] = None
        return LaiAnalysisSummary.model_validate(payload)

    def update(self, analysis_id: str, **fields: object) -> LaiAnalysisSummary | None:
        with self._lock:
            item = self.get(analysis_id)
            if item is None:
                return None
            item = LaiAnalysisSummary.model_validate({**item.model_dump(), **fields})
            self._items[analysis_id] = item
            self._save_locked(item)
            self._db.commit()
            return item

    def queue(self, analysis_id: str) -> asyncio.Queue | None:
        """Backward-compatible single subscriber used by older callers and tests."""
        with self._lock:
            if self.get(analysis_id) is None:
                return None
            queue = self._legacy_queues.get(analysis_id)
            if queue is None:
                queue = asyncio.Queue()
                self._legacy_queues[analysis_id] = queue
                self._subscribers.setdefault(analysis_id, set()).add(queue)
            return queue

    def subscribe(self, analysis_id: str) -> asyncio.Queue | None:
        """Create an independent live event queue for one SSE connection."""
        with self._lock:
            if self.get(analysis_id) is None:
                return None
            queue: asyncio.Queue = asyncio.Queue()
            self._subscribers.setdefault(analysis_id, set()).add(queue)
            return queue

    def unsubscribe(self, analysis_id: str, queue: asyncio.Queue) -> None:
        with self._lock:
            subscribers = self._subscribers.get(analysis_id)
            if subscribers is None:
                return
            subscribers.discard(queue)
            if not subscribers:
                self._subscribers.pop(analysis_id, None)

    def bind_loop(self, loop: asyncio.AbstractEventLoop) -> None:
        """Bind cross-thread event delivery to the server's active event loop."""
        with self._lock:
            if loop.is_closed():
                raise RuntimeError("Cannot bind LAI analysis events to a closed loop")
            self._loop = loop

    def push_event(self, analysis_id: str, event: dict) -> dict:
        """Persist one event, assign its sequence, then notify all live subscribers."""
        with self._lock:
            if self.get(analysis_id) is None:
                raise KeyError(f"Unknown LAI analysis: {analysis_id}")
            persisted = self._persist_event_locked(analysis_id, event)
            self._db.commit()
            subscribers = tuple(self._subscribers.get(analysis_id, ()))
            loop = self._loop
        if loop is not None and not loop.is_closed():
            for queue in subscribers:
                loop.call_soon_threadsafe(queue.put_nowait, dict(persisted))
        return persisted

    def update_and_push_event(self, analysis_id: str, event: dict, **fields: object) -> tuple[LaiAnalysisSummary, dict]:
        """Atomically persist an analysis state transition and its corresponding event."""
        with self._lock:
            item = self.get(analysis_id)
            if item is None:
                raise KeyError(f"Unknown LAI analysis: {analysis_id}")
            updated = LaiAnalysisSummary.model_validate({**item.model_dump(), **fields})
            self._items[analysis_id] = updated
            self._save_locked(updated)
            persisted = self._persist_event_locked(analysis_id, event)
            self._db.commit()
            subscribers = tuple(self._subscribers.get(analysis_id, ()))
            loop = self._loop
        if loop is not None and not loop.is_closed():
            for queue in subscribers:
                loop.call_soon_threadsafe(queue.put_nowait, dict(persisted))
        return updated, persisted

    def list_events(self, analysis_id: str, *, after_sequence: int = 0) -> list[dict]:
        rows = self._db.execute(
            "SELECT payload_json FROM product_lai_analysis_events "
            "WHERE analysis_id=? AND sequence>? ORDER BY sequence ASC",
            (analysis_id, max(0, int(after_sequence))),
        ).fetchall()
        return [json.loads(row["payload_json"]) for row in rows]

    def event_sequence(self, analysis_id: str, event_id: str | None) -> int:
        if not event_id:
            return 0
        row = self._db.execute(
            "SELECT sequence FROM product_lai_analysis_events WHERE analysis_id=? AND event_id=?",
            (analysis_id, event_id),
        ).fetchone()
        return int(row["sequence"]) if row is not None else 0

    def close(self, analysis_id: str) -> None:
        with self._lock:
            subscribers = tuple(self._subscribers.get(analysis_id, ()))
            loop = self._loop
        if loop is not None and not loop.is_closed():
            for queue in subscribers:
                loop.call_soon_threadsafe(queue.put_nowait, None)

    def is_terminal(self, analysis_id: str) -> bool:
        item = self.get(analysis_id)
        return item is not None and item.status in _TERMINAL_STATUSES

    def cleanup_terminal_resources(self, *, retention_seconds: int = 300, now: datetime | None = None) -> int:
        """Release expired connection queues while keeping persisted analyses and events."""
        cutoff = (now or datetime.now(timezone.utc)).timestamp() - max(0, retention_seconds)
        released = 0
        with self._lock:
            rows = self._db.execute("SELECT payload_json FROM product_lai_analyses").fetchall()
            for row in rows:
                item = self._load_summary(row["payload_json"])
                if item.status not in _TERMINAL_STATUSES:
                    continue
                timestamp_value = item.completed_at or item.updated_at
                if not timestamp_value:
                    continue
                try:
                    updated_at = datetime.fromisoformat(timestamp_value).timestamp()
                except ValueError:
                    continue
                if updated_at > cutoff:
                    continue
                self._subscribers.pop(item.analysis_id, None)
                self._legacy_queues.pop(item.analysis_id, None)
                released += 1
        return released

    def close_store(self) -> None:
        with self._lock:
            self._subscribers.clear()
            self._legacy_queues.clear()
            self._db.close()

    def _persist_event_locked(self, analysis_id: str, event: dict) -> dict:
        row = self._db.execute(
            "SELECT COALESCE(MAX(sequence), 0) + 1 AS next_sequence "
            "FROM product_lai_analysis_events WHERE analysis_id=?",
            (analysis_id,),
        ).fetchone()
        sequence = int(row["next_sequence"])
        payload = dict(event)
        payload.setdefault("event_id", str(uuid4()))
        payload.setdefault("analysis_id", analysis_id)
        payload.setdefault("timestamp", datetime.now(timezone.utc).isoformat())
        payload["sequence"] = sequence
        self._db.execute(
            "INSERT INTO product_lai_analysis_events "
            "(analysis_id, sequence, event_id, payload_json, created_at) VALUES (?, ?, ?, ?, ?)",
            (
                analysis_id,
                sequence,
                str(payload["event_id"]),
                json.dumps(payload, ensure_ascii=False),
                str(payload["timestamp"]),
            ),
        )
        return payload

    def _save_locked(self, item: LaiAnalysisSummary) -> None:
        self._db.execute(
            "INSERT OR REPLACE INTO product_lai_analyses (analysis_id, payload_json) VALUES (?, ?)",
            (item.analysis_id, item.model_dump_json()),
        )
