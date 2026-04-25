"""Confidence-evaluation node using the executor agent placeholder."""

from __future__ import annotations

import logging

from apps.orchestrator.graph.states import WorkflowState
from apps.orchestrator.graph.timing import append_stage_timing, stage_started
from apps.orchestrator.service_registry import get_orchestrator_executor_agent
from shared.schemas.executor import ExecutorTaskInput

logger = logging.getLogger(__name__)


def evaluate_confidence_node(state: WorkflowState) -> dict[str, object]:
    """Evaluate mock workflow confidence at the end of the graph."""
    request_id = state["request_id"]
    started_at = stage_started()
    logger.info("evaluate_confidence_started | request_id=%s", request_id)
    if not state.get("need_confidence", False):
        logger.info("evaluate_confidence_skipped | request_id=%s", request_id)
        return {
            "confidence_result": None,
            "stage_timings": append_stage_timing(
                state,
                stage_name="evaluate_confidence",
                started_at=started_at,
                status="skipped",
                detail="not requested",
            ),
            "status": "completed",
        }

    execution = get_orchestrator_executor_agent().execute(
        ExecutorTaskInput(
            request_id=request_id,
            tool_name="evaluate_confidence",
            payload={
                "inference_result": state.get("inference_result"),
                "rag_result": state.get("rag_result"),
                "report_result": state.get("report_result"),
                "training_triggered": state.get("training_triggered", False),
                "model_exists": state.get("model_exists", False),
                "status": state.get("status", "completed"),
                "error_count": len(state.get("errors", [])),
                "task_type": state.get("task_type"),
            },
        )
    )
    if not execution.success:
        logger.error(
            "evaluate_confidence_failed | request_id=%s | detail=%s",
            request_id,
            execution.message,
        )
        raise RuntimeError(execution.message)
    logger.info("evaluate_confidence_succeeded | request_id=%s", request_id)
    return {
        "confidence_result": execution.output,
        "executor_result": execution.model_dump(),
        "stage_timings": append_stage_timing(
            state,
            stage_name="evaluate_confidence",
            started_at=started_at,
            status="done",
            detail=str(execution.output.get("final_label", "n/a")),
        ),
        "status": "completed",
    }
