"""SQLite-backed state and SSE queues for typed LAI analyses."""

from __future__ import annotations

import asyncio
import threading
from datetime import datetime, timezone
from uuid import uuid4

from runtime.db import open_db
from schemas.spatial import CreateLaiAnalysisRequest, LaiAnalysisSummary


class LaiAnalysisStore:
    def __init__(self, db_path: str | None = None, loop: asyncio.AbstractEventLoop | None = None) -> None:
        self._db = open_db(db_path)
        self._loop = loop
        self._lock = threading.RLock()
        self._items: dict[str, LaiAnalysisSummary] = {}
        self._queues: dict[str, asyncio.Queue] = {}
        self._db.execute("""CREATE TABLE IF NOT EXISTS product_lai_analyses (
            analysis_id TEXT PRIMARY KEY, payload_json TEXT NOT NULL)""")
        self._db.commit()

    def create(self, body: CreateLaiAnalysisRequest) -> LaiAnalysisSummary:
        try:
            self.bind_loop(asyncio.get_running_loop())
        except RuntimeError:
            # Synchronous callers can still use persistence without SSE delivery.
            pass
        now = datetime.now(timezone.utc).isoformat()
        item = LaiAnalysisSummary(analysis_id=str(uuid4()), status="queued", stage="accepted", aoi=body.aoi,
            farm_id=body.farm_id, imagery_item_id=body.imagery_item_id, parameters=body.parameters,
            created_at=now, updated_at=now, detail="任务已创建，等待影像准备")
        with self._lock:
            self._items[item.analysis_id] = item
            self._queues[item.analysis_id] = asyncio.Queue()
            self._save(item)
        return item

    def get(self, analysis_id: str) -> LaiAnalysisSummary | None:
        with self._lock:
            if analysis_id in self._items:
                return self._items[analysis_id]
            row = self._db.execute("SELECT payload_json FROM product_lai_analyses WHERE analysis_id=?", (analysis_id,)).fetchone()
            if row is None:
                return None
            item = LaiAnalysisSummary.model_validate_json(row["payload_json"])
            self._items[analysis_id] = item
            return item

    def update(self, analysis_id: str, **fields: object) -> LaiAnalysisSummary | None:
        with self._lock:
            item = self.get(analysis_id)
            if item is None:
                return None
            item = item.model_copy(update=fields)
            self._items[analysis_id] = item
            self._save(item)
            return item

    def queue(self, analysis_id: str) -> asyncio.Queue | None:
        return self._queues.get(analysis_id)

    def bind_loop(self, loop: asyncio.AbstractEventLoop) -> None:
        """Bind cross-thread event delivery to the server's active event loop."""
        with self._lock:
            if loop.is_closed():
                raise RuntimeError("Cannot bind LAI analysis events to a closed event loop")
            self._loop = loop

    def push_event(self, analysis_id: str, event: dict) -> None:
        queue = self.queue(analysis_id)
        if queue is not None and self._loop is not None:
            self._loop.call_soon_threadsafe(queue.put_nowait, event)

    def close(self, analysis_id: str) -> None:
        queue = self.queue(analysis_id)
        if queue is not None and self._loop is not None:
            self._loop.call_soon_threadsafe(queue.put_nowait, None)

    def _save(self, item: LaiAnalysisSummary) -> None:
        self._db.execute("INSERT OR REPLACE INTO product_lai_analyses (analysis_id, payload_json) VALUES (?, ?)",
            (item.analysis_id, item.model_dump_json()))
        self._db.commit()
