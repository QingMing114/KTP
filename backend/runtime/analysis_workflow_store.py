"""Durable workflow registration and event history for map analysis tasks."""

from __future__ import annotations

import threading
import hashlib
import json
from datetime import datetime, timezone
from uuid import uuid4

from runtime.db import open_db
from schemas.workspace import WorkspaceContext
from schemas.workspace import ProfessionalReview
from schemas.analysis_workflow import (
    AnalysisWorkflowEvent, AnalysisWorkflowSummary, CreateAnalysisWorkflowRequest,
    StepId, WorkflowStatus, YieldAgronomicInputs, planned_steps,
)


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


class AnalysisWorkflowStore:
    def __init__(self, db_path: str | None = None) -> None:
        self._db = open_db(db_path)
        self._lock = threading.RLock()
        self._db.execute(
            "CREATE TABLE IF NOT EXISTS product_analysis_workflows "
            "(workflow_id TEXT PRIMARY KEY, owner_id TEXT NOT NULL, payload_json TEXT NOT NULL)"
        )
        self._db.execute(
            "CREATE TABLE IF NOT EXISTS product_analysis_workflow_events "
            "(workflow_id TEXT NOT NULL, sequence INTEGER NOT NULL, payload_json TEXT NOT NULL, "
            "PRIMARY KEY (workflow_id, sequence))"
        )
        self._db.commit()

        self._db.execute("CREATE TABLE IF NOT EXISTS product_workspace_contexts "
                         "(owner_id TEXT NOT NULL, workspace_id TEXT NOT NULL, revision INTEGER NOT NULL, "
                         "payload_json TEXT NOT NULL, PRIMARY KEY(owner_id, workspace_id))")
        self._db.execute("CREATE TABLE IF NOT EXISTS product_workflow_actions "
                         "(owner_id TEXT NOT NULL, action_id TEXT NOT NULL, request_hash TEXT NOT NULL, "
                         "workflow_id TEXT NOT NULL, PRIMARY KEY(owner_id, action_id))")
        self._db.commit()
        self._recover_interrupted()
        self._db.execute("CREATE TABLE IF NOT EXISTS product_professional_reviews "
                         "(review_id TEXT PRIMARY KEY, owner_id TEXT NOT NULL, workspace_id TEXT NOT NULL, payload_json TEXT NOT NULL)")
        self._db.commit()
        # An interrupted accepted operation must not be silently repeated.
        for row in self._db.execute("SELECT review_id, payload_json FROM product_professional_reviews").fetchall():
            review = ProfessionalReview.model_validate_json(row["payload_json"])
            if review.status == "processing":
                recovered = review.model_copy(update={"status": "failed", "detail": "服务重启中断了本次确认，请查看任务记录后重新生成配置"})
                self._db.execute("UPDATE product_professional_reviews SET payload_json=? WHERE review_id=?", (recovered.model_dump_json(), review.review_id))
        self._db.commit()

    def sync_workspace(self, context: WorkspaceContext, *, owner_id: str) -> None:
        with self._lock:
            self._db.execute("BEGIN IMMEDIATE")
            try:
                previous = self._db.execute(
                    "SELECT revision, payload_json FROM product_workspace_contexts WHERE owner_id=? AND workspace_id=?",
                    (owner_id, context.workspace_id),
                ).fetchone()
                payload = context.model_dump_json()
                if previous and (previous["revision"] > context.revision or
                                 (previous["revision"] == context.revision and previous["payload_json"] != payload)):
                    raise ValueError("工作台上下文已变化，请使用当前选区和影像重新提交。")
                self._db.execute("INSERT OR REPLACE INTO product_workspace_contexts VALUES (?, ?, ?, ?)",
                                 (owner_id, context.workspace_id, context.revision, payload))
                self._db.commit()
            except Exception:
                self._db.rollback()
                raise

    def _check_workspace(self, context: WorkspaceContext, owner_id: str) -> None:
        row = self._db.execute(
            "SELECT payload_json FROM product_workspace_contexts WHERE owner_id=? AND workspace_id=?",
            (owner_id, context.workspace_id),
        ).fetchone()
        if not row or row["payload_json"] != context.model_dump_json():
            raise ValueError("选区、影像或任务配置已变化，本次草案已失效，请重新提交。")

    def check_workspace(self, context: WorkspaceContext, *, owner_id: str) -> None:
        with self._lock:
            self._check_workspace(context, owner_id)

    def get_workspace(self, workspace_id: str, *, owner_id: str) -> WorkspaceContext | None:
        with self._lock:
            row = self._db.execute("SELECT payload_json FROM product_workspace_contexts WHERE owner_id=? AND workspace_id=?",
                                   (owner_id, workspace_id)).fetchone()
            return WorkspaceContext.model_validate_json(row["payload_json"]) if row else None

    def list_for_workspace(self, workspace_id: str, *, owner_id: str) -> list[AnalysisWorkflowSummary]:
        with self._lock:
            rows = self._db.execute("SELECT payload_json FROM product_analysis_workflows WHERE owner_id=? ORDER BY rowid", (owner_id,)).fetchall()
            items = [AnalysisWorkflowSummary.model_validate_json(row["payload_json"]) for row in rows]
            return [item for item in items if item.workspace_id == workspace_id]

    def _save(self, item: AnalysisWorkflowSummary) -> None:
        self._db.execute(
            "INSERT OR REPLACE INTO product_analysis_workflows "
            "(workflow_id, owner_id, payload_json) VALUES (?, ?, ?)",
            (item.workflow_id, item.owner_id, item.model_dump_json()),
        )

    def _add_event(self, event: AnalysisWorkflowEvent) -> None:
        self._db.execute(
            "INSERT INTO product_analysis_workflow_events "
            "(workflow_id, sequence, payload_json) VALUES (?, ?, ?)",
            (event.workflow_id, event.sequence, event.model_dump_json()),
        )

    def _next_sequence(self, workflow_id: str) -> int:
        row = self._db.execute(
            "SELECT COALESCE(MAX(sequence), 0) + 1 FROM product_analysis_workflow_events WHERE workflow_id=?",
            (workflow_id,),
        ).fetchone()
        return int(row[0])

    def _recover_interrupted(self) -> None:
        # Planned workflows have no worker yet and survive restarts unchanged.
        with self._lock:
            rows = self._db.execute("SELECT payload_json FROM product_analysis_workflows").fetchall()
            for row in rows:
                item = AnalysisWorkflowSummary.model_validate_json(row["payload_json"])
                if item.status != "running":
                    continue
                timestamp = _now()
                detail = "服务重启中断了工作流，请重新提交。"
                steps = [step.model_copy(update={
                    "status": "failed", "detail": detail, "updated_at": timestamp,
                }) if step.status == "running" else step for step in item.steps]
                recovered = item.model_copy(update={
                    "status": "failed", "detail": detail, "steps": steps,
                    "updated_at": timestamp, "completed_at": timestamp,
                })
                self._save(recovered)
                sequence = self._next_sequence(item.workflow_id)
                self._add_event(AnalysisWorkflowEvent(
                    event_id=str(uuid4()), workflow_id=item.workflow_id,
                    sequence=sequence, kind="status_updated", detail=detail, timestamp=timestamp,
                ))
            self._db.commit()

    def create(self, body: CreateAnalysisWorkflowRequest, *, owner_id: str,
               workspace: WorkspaceContext | None = None) -> AnalysisWorkflowSummary:
        if body.imagery_snapshot is None:
            raise ValueError("verified imagery_snapshot is required")
        timestamp = _now()
        effective, steps = planned_steps(body.requested_task_ids, body.data_mode)
        item = AnalysisWorkflowSummary(
            professional_mode=body.professional_mode,
            data_mode=body.data_mode, demo_crop=body.demo_crop,
            workflow_id=str(uuid4()), owner_id=owner_id, aoi=body.aoi,
            action_id=body.action_id, workspace_id=body.workspace_id,
            workspace_revision=body.workspace_revision, conversation_id=body.conversation_id, run_id=body.run_id,
            imagery_item_id=body.imagery_item_id, imagery_snapshot=body.imagery_snapshot,
            farm_id=body.farm_id, yield_inputs=body.yield_inputs,
            lai_query=body.lai_query,
            requested_task_ids=body.requested_task_ids,
            effective_task_ids=effective, steps=steps,
            created_at=timestamp, updated_at=timestamp,
        )
        event = AnalysisWorkflowEvent(
            event_id=str(uuid4()), workflow_id=item.workflow_id,
            sequence=1, kind="created", detail=item.detail, timestamp=timestamp,
        )
        with self._lock:
            self._db.execute("BEGIN IMMEDIATE")
            try:
                if workspace is not None:
                    self._check_workspace(workspace, owner_id)
                request_data = body.model_dump(mode="json", exclude={"run_id", "conversation_id"})
                request_hash = hashlib.sha256(json.dumps(request_data, sort_keys=True).encode()).hexdigest()
                if body.action_id:
                    prior = self._db.execute("SELECT request_hash, workflow_id FROM product_workflow_actions "
                                             "WHERE owner_id=? AND action_id=?", (owner_id, body.action_id)).fetchone()
                    if prior:
                        if prior["request_hash"] != request_hash:
                            raise ValueError("同一动作不能使用不同任务或输入，请创建新动作。")
                        existing = self.get(prior["workflow_id"], owner_id=owner_id)
                        self._db.commit()
                        assert existing is not None
                        return existing
                if item.workspace_id:
                    for existing in self.list_for_workspace(item.workspace_id, owner_id=owner_id):
                        if (existing.status in {"planned", "running"} and
                            existing.aoi.geometry == item.aoi.geometry and
                            existing.imagery_item_id == item.imagery_item_id):
                            raise ValueError("当前选区和影像已有任务正在执行，请查看进度，完成后再启动。")
                self._save(item)
                self._add_event(event)
                if body.action_id:
                    self._db.execute("INSERT INTO product_workflow_actions VALUES (?, ?, ?, ?)",
                                     (owner_id, body.action_id, request_hash, item.workflow_id))
                self._db.commit()
            except Exception:
                self._db.rollback()
                raise
        return item

    def claim_start(self, workflow_id: str, *, owner_id: str) -> bool:
        """Only one worker can transition a registered workflow into running."""
        with self._lock:
            self._db.execute("BEGIN IMMEDIATE")
            try:
                current = self.get(workflow_id, owner_id=owner_id)
                if current is None or current.status != "planned":
                    self._db.commit()
                    return False
                current = current.model_copy(update={"status": "running", "detail": "正在准备选区影像", "updated_at": _now()})
                self._save(current)
                self._add_event(AnalysisWorkflowEvent(event_id=str(uuid4()), workflow_id=workflow_id,
                    sequence=self._next_sequence(workflow_id), kind="status_updated", detail=current.detail, timestamp=current.updated_at))
                self._db.commit()
                return True
            except Exception:
                self._db.rollback()
                raise

    def get(self, workflow_id: str, *, owner_id: str) -> AnalysisWorkflowSummary | None:
        with self._lock:
            row = self._db.execute(
                "SELECT payload_json FROM product_analysis_workflows WHERE workflow_id=? AND owner_id=?",
                (workflow_id, owner_id),
            ).fetchone()
            return AnalysisWorkflowSummary.model_validate_json(row["payload_json"]) if row else None

    def owner_of(self, workflow_id: str) -> str | None:
        with self._lock:
            row = self._db.execute(
                "SELECT owner_id FROM product_analysis_workflows WHERE workflow_id=?", (workflow_id,),
            ).fetchone()
            return str(row["owner_id"]) if row else None

    def update_status(
        self, workflow_id: str, *, owner_id: str, status: WorkflowStatus, detail: str,
    ) -> AnalysisWorkflowSummary:
        with self._lock:
            current = self.get(workflow_id, owner_id=owner_id)
            if current is None:
                raise KeyError(workflow_id)
            timestamp = _now()
            updated = AnalysisWorkflowSummary.model_validate({
                **current.model_dump(), "status": status, "detail": detail,
                "updated_at": timestamp,
                "completed_at": timestamp if status in {"completed", "blocked", "failed", "cancelled"} else None,
            })
            self._save(updated)
            self._add_event(AnalysisWorkflowEvent(
                event_id=str(uuid4()), workflow_id=workflow_id,
                sequence=self._next_sequence(workflow_id), kind="status_updated",
                detail=detail, timestamp=timestamp,
            ))
            self._db.commit()
            return updated

    def update_step(
        self, workflow_id: str, step_id: StepId, *, owner_id: str, **fields: object,
    ) -> AnalysisWorkflowSummary:
        with self._lock:
            current = self.get(workflow_id, owner_id=owner_id)
            if current is None:
                raise KeyError(workflow_id)
            timestamp = _now()
            steps = []
            found = False
            for step in current.steps:
                if step.step_id != step_id:
                    steps.append(step)
                    continue
                found = True
                updated_step = type(step).model_validate({
                    **step.model_dump(), **fields, "updated_at": timestamp,
                })
                steps.append(updated_step)
            if not found:
                raise KeyError(step_id)
            updated = AnalysisWorkflowSummary.model_validate({
                **current.model_dump(), "steps": [step.model_dump() for step in steps],
                "updated_at": timestamp,
            })
            step = next(step for step in steps if step.step_id == step_id)
            self._save(updated)
            self._add_event(AnalysisWorkflowEvent(
                event_id=str(uuid4()), workflow_id=workflow_id,
                sequence=self._next_sequence(workflow_id), kind="step_updated",
                step_id=step_id, detail=step.detail,
                progress_percent=step.progress_percent, timestamp=timestamp,
            ))
            self._db.commit()
            return updated

    def update_yield_inputs(
        self, workflow_id: str, *, owner_id: str, inputs: YieldAgronomicInputs,
    ) -> AnalysisWorkflowSummary:
        with self._lock:
            current = self.get(workflow_id, owner_id=owner_id)
            if current is None:
                raise KeyError(workflow_id)
            timestamp = _now()
            updated = current.model_copy(update={
                "yield_inputs": inputs, "updated_at": timestamp,
            })
            self._save(updated)
            self._add_event(AnalysisWorkflowEvent(
                event_id=str(uuid4()), workflow_id=workflow_id,
                sequence=self._next_sequence(workflow_id), kind="status_updated",
                detail="产量估计农学输入已更新，正在重新校验启动条件", timestamp=timestamp,
            ))
            self._db.commit()
            return updated

    def set_report(self, workflow_id: str, *, owner_id: str, references: dict[str, str]) -> AnalysisWorkflowSummary:
        with self._lock:
            current = self.get(workflow_id, owner_id=owner_id)
            if current is None:
                raise KeyError(workflow_id)
            updated = current.model_copy(update=references)
            self._save(updated)
            self._db.commit()
            return updated

    def list_events(self, workflow_id: str, *, owner_id: str) -> list[AnalysisWorkflowEvent] | None:
        with self._lock:
            if self.get(workflow_id, owner_id=owner_id) is None:
                return None
            rows = self._db.execute(
                "SELECT payload_json FROM product_analysis_workflow_events "
                "WHERE workflow_id=? ORDER BY sequence", (workflow_id,),
            ).fetchall()
            return [AnalysisWorkflowEvent.model_validate_json(row["payload_json"]) for row in rows]

    def close(self) -> None:
        self._db.close()

    def save_review(self, review: ProfessionalReview, *, owner_id: str) -> None:
        with self._lock:
            self._db.execute("INSERT INTO product_professional_reviews VALUES (?, ?, ?, ?)",
                             (review.review_id, owner_id, review.workspace_id, review.model_dump_json()))
            self._db.commit()

    def get_review(self, review_id: str, *, owner_id: str) -> ProfessionalReview | None:
        with self._lock:
            row = self._db.execute("SELECT payload_json FROM product_professional_reviews WHERE review_id=? AND owner_id=?",
                                   (review_id, owner_id)).fetchone()
            return ProfessionalReview.model_validate_json(row["payload_json"]) if row else None

    def list_reviews(self, workspace_id: str, *, owner_id: str) -> list[ProfessionalReview]:
        with self._lock:
            rows = self._db.execute("SELECT payload_json FROM product_professional_reviews WHERE workspace_id=? AND owner_id=? ORDER BY rowid",
                                    (workspace_id, owner_id)).fetchall()
            return [ProfessionalReview.model_validate_json(row["payload_json"]) for row in rows]

    def claim_review(self, review_id: str, context: WorkspaceContext, *, owner_id: str, parameters: dict, cancelling: bool = False) -> ProfessionalReview:
        with self._lock:
            self._db.execute("BEGIN IMMEDIATE")
            try:
                self._check_workspace(context, owner_id)
                review = self.get_review(review_id, owner_id=owner_id)
                if review is None or review.status != "pending":
                    raise ValueError("确认卡片已处理，请刷新查看当前状态")
                if not cancelling and (not context.professional_mode or context.execution_mode != "live"):
                    raise ValueError("请保持专业模式开启后确认")
                if review.phase not in {"lai", "crop"} and not cancelling:
                    if review.context.model_dump(exclude={"revision"}) != context.model_dump(exclude={"revision"}):
                        raise ValueError("区域、影像、参数或模式已变化，请重新生成确认卡片")
                elif review.phase in {"lai", "crop"}:
                    flow = self.get(review.workflow_id, owner_id=owner_id)
                    step = next((s for s in flow.steps if s.step_id == review.phase), None) if flow else None
                    if (flow is None or flow.status != "blocked" or not step or step.updated_at != review.step_version
                            or step.result.get("review_id") != review.review_id
                            or not cancelling and (context.workspace_id != flow.workspace_id or context.aoi != flow.aoi
                            or context.imagery_item_id != flow.imagery_item_id or context.farm_id != flow.farm_id)):
                        raise ValueError("任务输入或步骤已变化，请查看对应任务后重新确认")
                updated = review.model_copy(update={"status": "processing", "confirmed_parameters": parameters})
                self._db.execute("UPDATE product_professional_reviews SET payload_json=? WHERE review_id=?", (updated.model_dump_json(), review_id))
                self._db.commit()
                return updated
            except Exception:
                self._db.rollback()
                raise

    def finish_review(self, review_id: str, *, owner_id: str, **updates) -> ProfessionalReview:
        with self._lock:
            review = self.get_review(review_id, owner_id=owner_id)
            if review is None:
                raise KeyError(review_id)
            updated = ProfessionalReview.model_validate({**review.model_dump(), **updates})
            self._db.execute("UPDATE product_professional_reviews SET payload_json=? WHERE review_id=? AND owner_id=?",
                             (updated.model_dump_json(), review_id, owner_id))
            self._db.commit()
            return updated
