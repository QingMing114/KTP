"""Schemas for confidence evaluation inputs and outputs."""

from __future__ import annotations

from pydantic import Field

from shared.schemas.common import BaseSchema


class ImageConfidenceInput(BaseSchema):
    """Image-related input for confidence scoring."""

    model_confidence: float = Field(..., description="Model confidence score.")
    affected_area: float = Field(..., description="Affected area estimate.")
    polygon_count: int = Field(..., description="Detected polygon count.")
    mask_uri: str | None = Field(
        default=None,
        description="Optional local mask artifact path used for sanity inspection.",
    )
    task_type: str | None = Field(
        default=None,
        description="Optional task type used for task-aware confidence heuristics.",
    )


class TextConfidenceInput(BaseSchema):
    """Text/RAG-related input for confidence scoring."""

    retrieved_source_count: int = Field(..., description="Retrieved source count.")
    average_retrieval_score: float = Field(
        ...,
        description="Average retrieval score across retrieved chunks.",
    )
    has_rag_summary: bool = Field(..., description="Whether a summary is available.")


class WorkflowConfidenceInput(BaseSchema):
    """Workflow execution input for confidence scoring."""

    model_exists: bool = Field(..., description="Whether a ready model existed.")
    training_triggered: bool = Field(..., description="Whether training was triggered.")
    error_count: int = Field(..., description="Workflow error count.")
    status: str = Field(..., description="Workflow status label.")


class ConfidenceRequest(BaseSchema):
    """Request payload for evaluating workflow confidence."""

    request_id: str = Field(..., description="Workflow request identifier.")
    image_input: ImageConfidenceInput = Field(..., description="Image input block.")
    text_input: TextConfidenceInput = Field(..., description="Text input block.")
    workflow_input: WorkflowConfidenceInput = Field(..., description="Workflow input block.")


class SubConfidenceResult(BaseSchema):
    """Sub-score result for one confidence dimension."""

    score: float = Field(..., description="Confidence score.")
    label: str = Field(..., description="Confidence label.")
    reason: str = Field(..., description="Human-readable reason.")
    warnings: list[str] = Field(
        default_factory=list,
        description="Warnings that temper confidence despite successful execution.",
    )


class ConfidenceResult(BaseSchema):
    """Final fused confidence output."""

    image_confidence: SubConfidenceResult = Field(..., description="Image confidence result.")
    text_confidence: SubConfidenceResult = Field(..., description="Text confidence result.")
    workflow_confidence: SubConfidenceResult = Field(..., description="Workflow confidence result.")
    final_confidence: float = Field(..., description="Final fused confidence.")
    final_label: str = Field(..., description="Final confidence label.")
    explanation: str = Field(..., description="Overall confidence explanation.")


class ConfidenceResponse(BaseSchema):
    """API response for confidence evaluation."""

    request_id: str = Field(..., description="Workflow request identifier.")
    success: bool = Field(..., description="Whether evaluation succeeded.")
    result: ConfidenceResult | None = Field(
        default=None,
        description="Confidence result when evaluation succeeds.",
    )
    message: str = Field(..., description="Human-readable evaluation outcome.")
