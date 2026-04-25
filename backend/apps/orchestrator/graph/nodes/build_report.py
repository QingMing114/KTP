"""Report-building node using the executor agent placeholder."""

from __future__ import annotations

import logging

from apps.orchestrator.graph.states import WorkflowState
from apps.orchestrator.graph.timing import append_stage_timing, stage_started
from apps.orchestrator.service_registry import get_orchestrator_executor_agent
from shared.schemas.executor import ExecutorTaskInput

logger = logging.getLogger(__name__)


def build_report_node(state: WorkflowState) -> dict[str, object]:
    """Build a mock report if the request requires one."""
    request_id = state["request_id"]
    started_at = stage_started()
    logger.info("build_report_started | request_id=%s", request_id)
    if not state.get("need_report", False):
        logger.info("build_report_skipped | request_id=%s", request_id)
        return {
            "report_result": None,
            "stage_timings": append_stage_timing(
                state,
                stage_name="build_report",
                started_at=started_at,
                status="skipped",
                detail="not requested",
            ),
            "status": "report_skipped",
        }

    execution = get_orchestrator_executor_agent().execute(
        ExecutorTaskInput(
            request_id=request_id,
            tool_name="build_report",
            payload={
                "task_type": state.get("task_type"),
                "region": state.get("region"),
                "crop_type": state.get("crop_type"),
                "user_query": state.get("user_query"),
                "inference_result": state.get("inference_result"),
                "rag_result": state.get("rag_result"),
                "training_triggered": state.get("training_triggered", False),
                "confidence_result": state.get("confidence_result"),
            },
        )
    )
    if not execution.success:
        logger.error(
            "build_report_failed | request_id=%s | detail=%s",
            request_id,
            execution.message,
        )
        raise RuntimeError(execution.message)
    logger.info("build_report_succeeded | request_id=%s", request_id)
    return {
        "report_result": execution.output,
        "executor_result": execution.model_dump(),
        "stage_timings": append_stage_timing(
            state,
            stage_name="build_report",
            started_at=started_at,
            status="done",
            detail=str(execution.output.get("report_id", "n/a")),
        ),
        "status": "report_built",
    }
