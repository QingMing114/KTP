"""Model registry lookup node with conditional routing."""

from __future__ import annotations

import logging

from apps.orchestrator.service_registry import get_model_registry_lookup_client
from apps.orchestrator.graph.states import WorkflowState
from apps.orchestrator.graph.timing import append_stage_timing, stage_started

logger = logging.getLogger(__name__)


def check_model_registry_node(state: WorkflowState) -> dict[str, object]:
    """Look up the latest ready model using the local model registry adapter."""
    request_id = state["request_id"]
    started_at = stage_started()
    logger.info("check_model_registry_started | request_id=%s", request_id)
    task_type = state.get("task_type")
    region = state.get("region")
    crop_type = state.get("crop_type")
    if task_type is None or region is None or crop_type is None:
        raise ValueError(
            "task_type, region, and crop_type must be resolved before model lookup"
        )

    result = get_model_registry_lookup_client().lookup_model(
        task_type=task_type,
        region=region,
        crop_type=crop_type,
    )
    explicit_need_training = state.get("need_training", False)
    need_training = explicit_need_training or not result.model_exists
    detail = "ready model found" if result.model_exists else "training required"
    if explicit_need_training and result.model_exists:
        detail = "training explicitly requested"
    logger.info(
        "check_model_registry_succeeded | request_id=%s | model_exists=%s | model_id=%s | need_training=%s",
        request_id,
        result.model_exists,
        result.model_id,
        need_training,
    )
    return {
        "model_exists": result.model_exists,
        "model_id": result.model_id,
        "model_name": result.model_name,
        "model_version": result.model_version,
        "model_status": result.status.value if result.status is not None else None,
        "artifact_uri": result.artifact_uri,
        "model_metrics": result.metrics_json,
        "model_description": result.description,
        "need_training": need_training,
        "stage_timings": append_stage_timing(
            state,
            stage_name="check_model_registry",
            started_at=started_at,
            status="done",
            detail=detail,
        ),
        "status": "model_registry_checked",
    }


def route_after_model_check(state: WorkflowState) -> str:
    """Route to inference when a model exists, otherwise trigger training."""
    if state.get("need_training"):
        return "trigger_training"
    if state.get("model_exists"):
        return "run_inference"
    return "trigger_training"
