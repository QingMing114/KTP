"""Bounded, durable parameter proposals shared by assistant and workflow tools."""
from datetime import datetime, timezone
from uuid import uuid4

from schemas.workspace import ProfessionalReview, WorkspaceIntent
from runtime.workspace_assistant import automatic_imagery_request


def create_review(workflows, *, owner_id, context, intent, run_id, conversation_id,
                  phase=None, candidates=None, search=None, workflow=None, scene=None):
    if phase is None:
        phase = "search" if not context.imagery_snapshot or intent.imagery_search else "workflow"
    if phase == "search":
        search = search or automatic_imagery_request(context, intent)
    candidates = candidates if candidates is not None else ([workflow.imagery_snapshot] if workflow else [context.imagery_snapshot] if context.imagery_snapshot else [])
    selected = next((item for item in candidates if item.is_recommended), None) or (candidates[0] if candidates else None)
    review = ProfessionalReview(
        review_id=str(uuid4()), workspace_id=context.workspace_id, source_run_id=run_id,
        conversation_id=conversation_id, context=context, intent=intent,
        phase=phase, title={"search": "确认影像搜索参数", "workflow": "确认影像与分析任务", "lai": "确认 LAI 反演参数"}[phase],
        rationale=(scene or {}).get("reasoning") or intent.rationale,
        search=search, candidates=candidates, selected_imagery_id=selected.item_id if selected else None,
        proposed_scene=scene, workflow_id=workflow.workflow_id if workflow else None,
        created_at=datetime.now(timezone.utc).isoformat(),
    )
    workflows.save_review(review, owner_id=owner_id)
    return review


def review_part(review):
    return {"type": "professional_review", "part_id": f"review-{review.review_id}", "data": {"review": review.model_dump(mode="json")}}


def validate_lai_lut_ranges(ranges):
    """Confirmed ranges must be applicable; professional mode never relaxes them."""
    import os
    from pathlib import Path
    import numpy as np
    from v2.tools.lai_report_handler import _build_lut_mask, _DEFAULT_LUT_TXT
    from schemas.runtime import SceneParameters

    constraints = SceneParameters.model_validate(ranges).to_constraints()
    if not constraints:
        return
    path = Path(os.environ.get("LAI_LUT_PATH") or _DEFAULT_LUT_TXT)
    if not path.is_file():
        raise ValueError("当前 LUT 不可用，无法核验参数，请稍后重试")
    lut = np.atleast_2d(np.loadtxt(path))
    mask = _build_lut_mask(lut[:, 0], lut[:, 9:13], constraints)
    if mask is not None and int(mask.sum()) < 10:
        raise ValueError("所选参数范围在当前 LUT 中不足 10 条组合，请调整范围或选择不限制；本次未执行")
