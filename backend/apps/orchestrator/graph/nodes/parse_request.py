"""Parse-request node using the planner agent placeholder."""

from __future__ import annotations

import logging
from typing import Any

from apps.orchestrator.service_registry import get_orchestrator_planner_agent
from apps.orchestrator.graph.states import WorkflowState
from apps.orchestrator.graph.timing import append_stage_timing, stage_started

logger = logging.getLogger(__name__)


def parse_request_node(state: WorkflowState) -> dict[str, object]:
    """Parse the raw user request into structured workflow fields."""
    request_id = state["request_id"]
    started_at = stage_started()
    logger.info("parse_request_started | request_id=%s", request_id)
    explicit_plan = _extract_explicit_agent_plan(state.get("extra_params", {}))
    plan = get_orchestrator_planner_agent().create_plan(
        request_id=request_id,
        user_query=state["user_query"],
    )
    resolved_task_type = (
        state.get("task_type")
        or explicit_plan.get("task_type")
        or plan.task_type
    )
    resolved_region = state.get("region") or explicit_plan.get("region") or plan.region
    resolved_crop_type = (
        state.get("crop_type") or explicit_plan.get("crop_type") or plan.crop_type
    )
    logger.info(
        "parse_request_succeeded | request_id=%s | task_type=%s | region=%s | crop_type=%s | explicit_plan=%s",
        request_id,
        resolved_task_type,
        resolved_region,
        resolved_crop_type,
        bool(explicit_plan),
    )
    return {
        "task_type": resolved_task_type,
        "region": resolved_region,
        "crop_type": resolved_crop_type,
        "need_training": _resolve_boolean_override(
            explicit_plan.get("need_training"),
            plan.need_training,
        ),
        "need_rag": _resolve_boolean_override(
            explicit_plan.get("need_rag"),
            plan.need_rag,
        ),
        "need_report": _resolve_boolean_override(
            explicit_plan.get("need_report"),
            plan.need_report,
        ),
        "need_confidence": _resolve_boolean_override(
            explicit_plan.get("need_confidence"),
            plan.need_confidence,
        ),
        "planner_result": {
            **plan.model_dump(),
            "task_type": resolved_task_type,
            "region": resolved_region,
            "crop_type": resolved_crop_type,
            "need_training": _resolve_boolean_override(
                explicit_plan.get("need_training"),
                plan.need_training,
            ),
            "need_rag": _resolve_boolean_override(
                explicit_plan.get("need_rag"),
                plan.need_rag,
            ),
            "need_report": _resolve_boolean_override(
                explicit_plan.get("need_report"),
                plan.need_report,
            ),
            "need_confidence": _resolve_boolean_override(
                explicit_plan.get("need_confidence"),
                plan.need_confidence,
            ),
            "decision_source": "gateway_agent" if explicit_plan else "orchestrator_planner",
        },
        "stage_timings": append_stage_timing(
            state,
            stage_name="parse_request",
            started_at=started_at,
            status="done",
            detail=resolved_task_type,
        ),
        "status": "request_parsed",
    }


def _extract_explicit_agent_plan(extra_params: dict[str, Any]) -> dict[str, Any]:
    raw_plan = extra_params.get("agent_plan")
    if not isinstance(raw_plan, dict):
        return {}
    allowed_keys = {
        "task_type",
        "region",
        "crop_type",
        "need_training",
        "need_rag",
        "need_report",
        "need_confidence",
    }
    return {key: raw_plan.get(key) for key in allowed_keys if key in raw_plan}


def _resolve_boolean_override(explicit_value: object, fallback: bool) -> bool:
    if isinstance(explicit_value, bool):
        return explicit_value
    return fallback
