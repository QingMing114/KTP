"""Persist crop classification jobs independently of the request connection."""

from __future__ import annotations

import threading
from datetime import datetime, timezone
from uuid import uuid4

from runtime.db import open_db
from schemas.spatial import CreateCropAnalysisRequest, CropAnalysisSummary


class CropAnalysisStore:
    def __init__(self, db_path: str | None = None) -> None:
        self._db = open_db(db_path)
        self._lock = threading.RLock()
        self._db.execute(
            "CREATE TABLE IF NOT EXISTS product_crop_analyses "
            "(analysis_id TEXT PRIMARY KEY, payload_json TEXT NOT NULL)"
        )
        self._db.commit()
        self._recover_interrupted()

    def _recover_interrupted(self) -> None:
        rows = self._db.execute("SELECT payload_json FROM product_crop_analyses").fetchall()
        for row in rows:
            item = CropAnalysisSummary.model_validate_json(row["payload_json"])
            if item.status in {"queued", "running"}:
                now = datetime.now(timezone.utc).isoformat()
                self._save(item.model_copy(update={
                    "status": "failed", "stage": "failed", "updated_at": now,
                    "completed_at": now, "detail": "服务重启中断了作物识别，请重新提交。",
                    "result": {"error": "服务重启中断了作物识别，请重新提交。"},
                }))
        self._db.commit()

    def _save(self, item: CropAnalysisSummary) -> None:
        self._db.execute(
            "INSERT OR REPLACE INTO product_crop_analyses (analysis_id, payload_json) VALUES (?, ?)",
            (item.analysis_id, item.model_dump_json()),
        )

    def create(self, body: CreateCropAnalysisRequest, *, owner_id: str = "anonymous") -> CropAnalysisSummary:
        now = datetime.now(timezone.utc).isoformat()
        item = CropAnalysisSummary(
            analysis_id=str(uuid4()), owner_id=owner_id, status="queued", stage="accepted", aoi=body.aoi,
            imagery_item_id=body.imagery_item_id, imagery_snapshot=body.imagery_snapshot,
            farm_id=body.farm_id, created_at=now, updated_at=now,
            detail="作物识别任务已创建，等待影像准备",
        )
        with self._lock:
            self._save(item)
            self._db.commit()
        return item

    def get(self, analysis_id: str) -> CropAnalysisSummary | None:
        with self._lock:
            row = self._db.execute(
                "SELECT payload_json FROM product_crop_analyses WHERE analysis_id=?", (analysis_id,)
            ).fetchone()
            return CropAnalysisSummary.model_validate_json(row["payload_json"]) if row else None

    def owner_of(self, analysis_id: str) -> str | None:
        item = self.get(analysis_id)
        return item.owner_id if item is not None else None

    def update(self, analysis_id: str, **fields: object) -> CropAnalysisSummary:
        with self._lock:
            current = self.get(analysis_id)
            if current is None:
                raise KeyError(analysis_id)
            fields.setdefault("updated_at", datetime.now(timezone.utc).isoformat())
            item = CropAnalysisSummary.model_validate({**current.model_dump(), **fields})
            self._save(item)
            self._db.commit()
            return item

    def close(self) -> None:
        self._db.close()
