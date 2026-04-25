"""RAG node using the executor agent placeholder."""

from __future__ import annotations

import logging

from apps.orchestrator.graph.states import WorkflowState
from apps.orchestrator.graph.timing import append_stage_timing, stage_started
from apps.orchestrator.service_registry import get_orchestrator_executor_agent
from shared.schemas.executor import ExecutorTaskInput

logger = logging.getLogger(__name__)


def run_rag_node(state: WorkflowState) -> dict[str, object]:
    """Run mock retrieval-augmented context generation when requested."""
    request_id = state["request_id"]
    started_at = stage_started()
    logger.info("run_rag_started | request_id=%s", request_id)
    if not state.get("need_rag", False):
        logger.info("run_rag_skipped | request_id=%s", request_id)
        return {
            "rag_result": None,
            "stage_timings": append_stage_timing(
                state,
                stage_name="run_rag",
                started_at=started_at,
                status="skipped",
                detail="not requested",
            ),
            "status": "rag_skipped",
        }

    execution = get_orchestrator_executor_agent().execute(
        ExecutorTaskInput(
            request_id=request_id,
            tool_name="run_rag",
            payload={
                "user_query": state.get("user_query"),
                "task_type": state.get("task_type"),
                "region": state.get("region"),
                "crop_type": state.get("crop_type"),
                "inference_result": state.get("inference_result"),
                "context": state.get("extra_params", {}),
            },
        )
    )
    if not execution.success:
        logger.error(
            "run_rag_failed | request_id=%s | detail=%s",
            request_id,
            execution.message,
        )
        raise RuntimeError(execution.message)
    logger.info("run_rag_succeeded | request_id=%s", request_id)
    return {
        "rag_result": execution.output,
        "executor_result": execution.model_dump(),
        "stage_timings": append_stage_timing(
            state,
            stage_name="run_rag",
            started_at=started_at,
            status="done",
            detail=f"{len(execution.output.get('sources', []))} sources",
        ),
        "status": "rag_completed",
    }
