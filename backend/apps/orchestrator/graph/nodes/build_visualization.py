"""Visualization node that renders a workflow dashboard after outputs are ready."""

from __future__ import annotations

import logging

from apps.orchestrator.graph.states import WorkflowState
from apps.orchestrator.graph.timing import append_stage_timing, stage_started
from apps.orchestrator.service_registry import get_orchestrator_executor_agent
from shared.schemas.executor import ExecutorTaskInput

logger = logging.getLogger(__name__)


def build_visualization_node(state: WorkflowState) -> dict[str, object]:
    """Generate a workflow visualization without disturbing main business outputs."""
    request_id = state["request_id"]
    started_at = stage_started()
    if state.get("extra_params", {}).get("enable_visualization", True) is False:
        logger.info("build_visualization_skipped | request_id=%s", request_id)
        return {
            "visualization_result": None,
            "stage_timings": append_stage_timing(
                state,
                stage_name="build_visualization",
                started_at=started_at,
                status="skipped",
                detail="disabled by request",
            ),
        }

    logger.info("build_visualization_started | request_id=%s", request_id)
    payload = dict(state)
    payload["workflow_status"] = state.get("status", "completed")
    payload["final_state"] = dict(state)
    execution = get_orchestrator_executor_agent().execute(
        ExecutorTaskInput(
            request_id=request_id,
            tool_name="build_visualization",
            payload=payload,
        )
    )
    if not execution.success:
        logger.error(
            "build_visualization_failed | request_id=%s | detail=%s",
            request_id,
            execution.message,
        )
        updated_errors = [*state.get("errors", []), execution.message]
        return {
            "visualization_result": None,
            "errors": updated_errors,
            "executor_result": execution.model_dump(),
            "stage_timings": append_stage_timing(
                state,
                stage_name="build_visualization",
                started_at=started_at,
                status="failed",
                detail=execution.message,
            ),
        }

    logger.info("build_visualization_succeeded | request_id=%s", request_id)
    return {
        "visualization_result": execution.output,
        "executor_result": execution.model_dump(),
        "stage_timings": append_stage_timing(
            state,
            stage_name="build_visualization",
            started_at=started_at,
            status="done",
            detail=str(execution.output.get("visualization_id", "n/a")),
        ),
    }
