"""Training-trigger node using the executor agent placeholder."""

from __future__ import annotations

import logging

from apps.orchestrator.graph.states import WorkflowState
from apps.orchestrator.graph.timing import append_stage_timing, stage_started
from apps.orchestrator.service_registry import get_orchestrator_executor_agent
from shared.schemas.executor import ExecutorTaskInput

logger = logging.getLogger(__name__)


def trigger_training_node(state: WorkflowState) -> dict[str, object]:
    """Trigger a mock training workflow through the executor."""
    request_id = state["request_id"]
    started_at = stage_started()
    logger.info("trigger_training_started | request_id=%s", request_id)
    execution = get_orchestrator_executor_agent().execute(
        ExecutorTaskInput(
            request_id=request_id,
            tool_name="trigger_training",
            payload={
                "task_type": state.get("task_type"),
                "region": state.get("region"),
                "crop_type": state.get("crop_type"),
                "extra_params": state.get("extra_params", {}),
            },
        )
    )
    if not execution.success:
        logger.error(
            "trigger_training_failed | request_id=%s | detail=%s",
            request_id,
            execution.message,
        )
        raise RuntimeError(execution.message)
    logger.info("trigger_training_succeeded | request_id=%s", request_id)
    return {
        "training_triggered": True,
        "training_job_id": execution.output.get("training_job_id"),
        "training_workflow_id": execution.output.get("workflow_id"),
        "training_run_id": execution.output.get("run_id"),
        "training_task_queue": execution.output.get("task_queue"),
        "training_backend": execution.output.get("backend"),
        "executor_result": execution.model_dump(),
        "stage_timings": append_stage_timing(
            state,
            stage_name="trigger_training",
            started_at=started_at,
            status="triggered",
            detail=str(execution.output.get("backend", "unknown")),
        ),
        "status": "training_triggered",
    }
