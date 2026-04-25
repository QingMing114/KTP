"""Schemas for workflow visualization inputs and outputs."""

from __future__ import annotations

from datetime import datetime
from typing import Any

from pydantic import Field

from shared.schemas.common import BaseSchema


class VisualizationArtifact(BaseSchema):
    """One workflow artifact and its derived preview."""

    artifact_key: str = Field(..., description="Stable artifact identifier.")
    title: str = Field(..., description="Human-readable artifact title.")
    artifact_kind: str = Field(..., description="Artifact type or preview mode.")
    source_uri: str | None = Field(default=None, description="Original artifact path or URI.")
    preview_uri: str | None = Field(default=None, description="Derived preview PNG path.")
    available: bool = Field(..., description="Whether the source artifact was available.")
    note: str | None = Field(default=None, description="Optional note when preview is partial.")


class VisualizationRequest(BaseSchema):
    """Structured workflow payload used to render a dashboard."""

    request_id: str = Field(..., description="Workflow request identifier.")
    workflow_status: str = Field(..., description="Final workflow status.")
    user_query: str = Field(..., description="Original user query.")
    task_type: str | None = Field(default=None, description="Resolved task type.")
    region: str | None = Field(default=None, description="Resolved region.")
    crop_type: str | None = Field(default=None, description="Resolved crop type.")
    image_path: str | None = Field(default=None, description="Input image path when available.")
    use_mock: bool | None = Field(default=None, description="Whether mock inference was used.")
    extra_params: dict[str, Any] = Field(
        default_factory=dict,
        description="Forwarded structured request parameters.",
    )
    planner_result: dict[str, Any] | None = Field(
        default=None,
        description="Planner output snapshot.",
    )
    executor_result: dict[str, Any] | None = Field(
        default=None,
        description="Latest executor output snapshot.",
    )
    model_exists: bool | None = Field(default=None, description="Whether a ready model existed.")
    model_id: int | None = Field(default=None, description="Resolved model identifier.")
    model_name: str | None = Field(default=None, description="Resolved model name.")
    model_version: str | None = Field(default=None, description="Resolved model version.")
    model_status: str | None = Field(default=None, description="Resolved model status.")
    artifact_uri: str | None = Field(default=None, description="Resolved model artifact URI.")
    model_metrics: dict[str, Any] | None = Field(
        default=None,
        description="Resolved model metadata metrics payload.",
    )
    model_description: str | None = Field(
        default=None,
        description="Resolved model description.",
    )
    training_triggered: bool = Field(default=False, description="Whether training was triggered.")
    training_job_id: str | None = Field(default=None, description="Training job identifier.")
    training_workflow_id: str | None = Field(
        default=None,
        description="Temporal workflow identifier when available.",
    )
    training_run_id: str | None = Field(
        default=None,
        description="Temporal run identifier when available.",
    )
    training_task_queue: str | None = Field(
        default=None,
        description="Temporal task queue when available.",
    )
    training_backend: str | None = Field(default=None, description="Training backend label.")
    inference_result: dict[str, Any] | None = Field(
        default=None,
        description="Structured inference result.",
    )
    rag_result: dict[str, Any] | None = Field(default=None, description="Structured RAG result.")
    report_result: dict[str, Any] | None = Field(
        default=None,
        description="Structured report result.",
    )
    confidence_result: dict[str, Any] | None = Field(
        default=None,
        description="Structured confidence result.",
    )
    stage_timings: list[dict[str, Any]] = Field(
        default_factory=list,
        description="Per-stage timing summaries captured during workflow execution.",
    )
    errors: list[str] = Field(default_factory=list, description="Accumulated workflow errors.")
    final_state: dict[str, Any] = Field(
        default_factory=dict,
        description="Complete final workflow state snapshot.",
    )


class VisualizationResult(BaseSchema):
    """Generated workflow dashboard output."""

    visualization_id: str = Field(..., description="Stable visualization identifier.")
    title: str = Field(..., description="Dashboard title.")
    dashboard_path: str = Field(..., description="Local HTML dashboard path.")
    artifact_dir: str = Field(..., description="Directory containing derived previews.")
    snapshot_path: str = Field(..., description="Path to the persisted workflow snapshot JSON.")
    generated_at: datetime = Field(..., description="Dashboard generation time.")
    sections: list[str] = Field(
        default_factory=list,
        description="Rendered dashboard section identifiers.",
    )
    artifacts: list[VisualizationArtifact] = Field(
        default_factory=list,
        description="Resolved artifacts included in the dashboard.",
    )
    html: str | None = Field(default=None, description="Embedded HTML when enabled.")


class VisualizationResponse(BaseSchema):
    """API-style response for workflow visualization rendering."""

    request_id: str = Field(..., description="Original workflow request identifier.")
    success: bool = Field(..., description="Whether dashboard generation succeeded.")
    result: VisualizationResult | None = Field(
        default=None,
        description="Generated visualization output when successful.",
    )
    message: str = Field(..., description="Human-readable generation outcome.")
