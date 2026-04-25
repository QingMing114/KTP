"""Minimal demo entrypoint for the LangGraph orchestrator scaffold."""

from __future__ import annotations

import json
import logging
from uuid import uuid4

from apps.orchestrator.graph.states import create_initial_state
from apps.orchestrator.graph.workflow import get_workflow
from shared.config.settings import get_settings
from shared.logging import configure_logging
from shared.schemas.orchestrator import WorkflowRequest, WorkflowResponse

settings = get_settings()
configure_logging(settings.log_level)
logger = logging.getLogger(__name__)


def run_workflow_request(request: WorkflowRequest) -> WorkflowResponse:
    """Run the orchestrator workflow for a structured request."""
    logger.info("workflow_request_started | request_id=%s", request.request_id)
    workflow = get_workflow()
    final_state = workflow.invoke(
        create_initial_state(
            request_id=request.request_id,
            user_query=request.user_query,
            region=request.region,
            crop_type=request.crop_type,
            task_type=request.task_type,
            image_path=request.image_path,
            use_mock=request.use_mock,
            extra_params=request.extra_params,
        )
    )
    logger.info(
        "workflow_request_succeeded | request_id=%s | status=%s",
        request.request_id,
        final_state["status"],
    )
    return WorkflowResponse(
        request_id=request.request_id,
        status=final_state["status"],
        final_state=final_state,
    )


def run_demo(user_query: str | None = None) -> WorkflowResponse:
    """Run a simple workflow demo for local development."""
    request = WorkflowRequest(
        request_id=str(uuid4()),
        user_query=(
            user_query
            or "Assess wheat health in Henan and provide a short report with confidence."
        ),
    )
    response = run_workflow_request(request)
    logger.info(
        "workflow_demo_completed | request_id=%s | final_state=%s",
        response.request_id,
        json.dumps(response.final_state, ensure_ascii=True, sort_keys=True),
    )
    return response


if __name__ == "__main__":
    run_demo()
