"""Inference node using the executor agent placeholder."""

from __future__ import annotations

import logging

from apps.orchestrator.graph.states import WorkflowState
from apps.orchestrator.graph.timing import append_stage_timing, stage_started
from apps.orchestrator.service_registry import get_orchestrator_executor_agent
from shared.schemas.executor import ExecutorTaskInput

logger = logging.getLogger(__name__)


def run_inference_node(state: WorkflowState) -> dict[str, object]:
    """Run inference through the executor agent and integrated inference service."""
    request_id = state["request_id"]
    started_at = stage_started()
    logger.info("run_inference_started | request_id=%s", request_id)
    execution = get_orchestrator_executor_agent().execute(
        ExecutorTaskInput(
            request_id=request_id,
            tool_name="run_inference",
            payload={
                "task_type": state.get("task_type"),
                "region": state.get("region"),
                "crop_type": state.get("crop_type"),
                "model_name": state.get("model_name"),
                "model_version": state.get("model_version"),
                "image_path": state.get("image_path"),
                "use_mock": state.get("use_mock"),
                "extra_params": state.get("extra_params", {}),
            },
        )
    )
    if not execution.success:
        logger.error(
            "run_inference_failed | request_id=%s | detail=%s",
            request_id,
            execution.message,
        )
        raise RuntimeError(execution.message)
    logger.info("run_inference_succeeded | request_id=%s", request_id)
    return {
        "inference_result": execution.output,
        "executor_result": execution.model_dump(),
        "stage_timings": append_stage_timing(
            state,
            stage_name="run_inference",
            started_at=started_at,
            status="done",
            detail=str(execution.output.get("model_version", "n/a")),
        ),
        "status": "inference_completed",
    }
