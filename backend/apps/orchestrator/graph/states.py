"""Workflow state definitions for the LangGraph orchestrator.

TypedDict is used here because LangGraph works naturally with dict-like state and
partial node updates. External API and service boundaries remain Pydantic-based.
"""

from __future__ import annotations

from typing import TypedDict


class WorkflowState(TypedDict, total=False):
    """Shared mutable state passed across LangGraph nodes."""

    request_id: str
    user_query: str
    image_path: str | None
    use_mock: bool | None
    extra_params: dict
    task_type: str | None
    region: str | None
    crop_type: str | None
    need_training: bool
    need_rag: bool
    need_report: bool
    need_confidence: bool
    model_exists: bool | None
    model_id: int | None
    model_name: str | None
    model_version: str | None
    model_status: str | None
    artifact_uri: str | None
    model_metrics: dict | None
    model_description: str | None
    training_triggered: bool
    training_job_id: str | None
    training_workflow_id: str | None
    training_run_id: str | None
    training_task_queue: str | None
    training_backend: str | None
    inference_result: dict | None
    rag_result: dict | None
    report_result: dict | None
    confidence_result: dict | None
    visualization_result: dict | None
    stage_timings: list[dict]
    planner_result: dict | None
    executor_result: dict | None
    errors: list[str]
    status: str


def create_initial_state(
    request_id: str,
    user_query: str,
    region: str | None = None,
    crop_type: str | None = None,
    task_type: str | None = None,
    image_path: str | None = None,
    use_mock: bool | None = None,
    extra_params: dict | None = None,
) -> WorkflowState:
    """Create the initial workflow state for a new request."""
    return WorkflowState(
        request_id=request_id,
        user_query=user_query,
        image_path=image_path,
        use_mock=use_mock,
        extra_params=extra_params or {},
        task_type=task_type,
        region=region,
        crop_type=crop_type,
        need_training=False,
        need_rag=False,
        need_report=False,
        need_confidence=False,
        model_exists=None,
        model_id=None,
        model_name=None,
        model_version=None,
        model_status=None,
        artifact_uri=None,
        model_metrics=None,
        model_description=None,
        training_triggered=False,
        training_job_id=None,
        training_workflow_id=None,
        training_run_id=None,
        training_task_queue=None,
        training_backend=None,
        inference_result=None,
        rag_result=None,
        report_result=None,
        confidence_result=None,
        visualization_result=None,
        stage_timings=[],
        planner_result=None,
        executor_result=None,
        errors=[],
        status="received",
    )
