"""Schemas for service adapter placeholder results."""

from __future__ import annotations

from typing import Any

from pydantic import Field

from shared.schemas.common import BaseSchema


class ModelRegistryResult(BaseSchema):
    """Mock model registry lookup result."""

    model_exists: bool = Field(..., description="Whether a model exists.")
    model_id: int | None = Field(default=None, description="Resolved model identifier.")
    model_name: str | None = Field(default=None, description="Resolved model name.")
    model_version: str | None = Field(
        default=None,
        description="Resolved model version.",
    )
    artifact_uri: str | None = Field(
        default=None,
        description="Resolved model artifact URI when a model exists.",
    )
    status: str | None = Field(default=None, description="Resolved model lifecycle status.")
    reason: str | None = Field(default=None, description="Reason when no model is available.")


class TrainingTriggerResult(BaseSchema):
    """Mock training trigger result."""

    training_triggered: bool = Field(..., description="Whether training was triggered.")
    training_job_id: str = Field(..., description="Mock training job identifier.")
    workflow_id: str | None = Field(
        default=None,
        description="Workflow identifier when using Temporal-backed training.",
    )
    run_id: str | None = Field(
        default=None,
        description="Temporal run identifier when available.",
    )
    task_queue: str | None = Field(
        default=None,
        description="Temporal task queue when applicable.",
    )
    backend: str | None = Field(
        default=None,
        description="Training backend used for this trigger.",
    )


class InferenceServiceResult(BaseSchema):
    """Mock inference output."""

    mask_uri: str = Field(..., description="URI to the predicted mask artifact.")
    affected_area: float = Field(..., description="Estimated affected area.")
    confidence: float = Field(..., description="Model confidence score.")
    model_version: str = Field(..., description="Version of the model used.")
    model_name: str | None = Field(default=None, description="Resolved model name.")
    artifact_uri: str | None = Field(default=None, description="Resolved model artifact URI.")
    polygons: list[dict[str, Any]] = Field(
        default_factory=list,
        description="Optional polygon outputs returned by the inference backend.",
    )
    raw_prediction_uri: str | None = Field(
        default=None,
        description="Raw class-map or predictor output path when available.",
    )
    confidence_map_uri: str | None = Field(
        default=None,
        description="Confidence raster path when available.",
    )
    warnings: list[str] = Field(
        default_factory=list,
        description="Warnings about prediction semantics or interpretation.",
    )
    class_distribution: list[dict[str, Any]] = Field(
        default_factory=list,
        description="Per-class summary for multi-class predictors.",
    )
    class_labels: dict[str, str] = Field(
        default_factory=dict,
        description="Resolved class labels keyed by class value.",
    )
    target_classes: list[int] = Field(
        default_factory=list,
        description="Classes selected as the target mask.",
    )


class RagServiceResult(BaseSchema):
    """Mock RAG output."""

    query: str | None = Field(default=None, description="Original retrieval query.")
    summary: str = Field(..., description="Short retrieved context summary.")
    sources: list[str] = Field(..., description="Mock knowledge source identifiers.")
    top_k: int = Field(..., description="Number of retrieved documents.")
    results: list[dict[str, Any]] = Field(
        default_factory=list,
        description="Structured retrieved chunks for downstream consumers.",
    )


class ReportServiceResult(BaseSchema):
    """Mock report generation output."""

    report_uri: str = Field(..., description="URI to the rendered report.")
    title: str = Field(..., description="Report title.")
    sections: list[str] = Field(..., description="Report section titles.")
    report_id: str | None = Field(default=None, description="Stable report identifier.")
    html: str | None = Field(default=None, description="Embedded HTML when available.")
    generated_at: str | None = Field(
        default=None,
        description="Report generation time in ISO string form.",
    )


class ConfidenceServiceResult(BaseSchema):
    """Mock workflow confidence output."""

    image_confidence: float = Field(..., description="Inference confidence component.")
    text_confidence: float = Field(..., description="RAG/text confidence component.")
    workflow_confidence: float = Field(
        ...,
        description="Workflow completeness confidence component.",
    )
    final_confidence: float = Field(..., description="Combined confidence score.")
    final_label: str | None = Field(default=None, description="Confidence label.")
    explanation: str = Field(..., description="Short explanation of the score.")
    image_detail: dict[str, Any] = Field(
        default_factory=dict,
        description="Detailed image confidence breakdown.",
    )
    text_detail: dict[str, Any] = Field(
        default_factory=dict,
        description="Detailed text confidence breakdown.",
    )
    workflow_detail: dict[str, Any] = Field(
        default_factory=dict,
        description="Detailed workflow confidence breakdown.",
    )
    report_available: bool | None = Field(
        default=None,
        description="Whether a report artifact was already available during evaluation.",
    )


class VisualizationServiceResult(BaseSchema):
    """Workflow visualization output."""

    visualization_uri: str = Field(..., description="URI to the rendered dashboard.")
    title: str = Field(..., description="Visualization title.")
    sections: list[str] = Field(..., description="Rendered section identifiers.")
    visualization_id: str | None = Field(
        default=None,
        description="Stable visualization identifier.",
    )
    artifact_dir: str | None = Field(
        default=None,
        description="Directory containing generated preview artifacts.",
    )
    snapshot_path: str | None = Field(
        default=None,
        description="Path to the persisted workflow snapshot JSON.",
    )
    html: str | None = Field(default=None, description="Embedded HTML when available.")
    generated_at: str | None = Field(
        default=None,
        description="Visualization generation time in ISO string form.",
    )
    artifacts: list[dict[str, Any]] = Field(
        default_factory=list,
        description="Derived preview artifacts included in the dashboard.",
    )
