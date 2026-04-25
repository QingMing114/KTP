"""Schemas for report generation inputs and outputs."""

from __future__ import annotations

from datetime import datetime
from typing import Any

from pydantic import Field

from shared.schemas.common import BaseSchema


class ReportInputSummary(BaseSchema):
    """Summary content included in the report."""

    overview: str = Field(..., description="Short overall summary.")
    key_findings: list[str] = Field(
        default_factory=list,
        description="Key findings shown near the top of the report.",
    )


class ReportInputInference(BaseSchema):
    """Inference section payload for the report."""

    model_name: str = Field(..., description="Model family or name.")
    model_version: str = Field(..., description="Model version.")
    affected_area: float = Field(..., description="Affected area in current units.")
    confidence: float = Field(..., description="Inference confidence.")
    mask_uri: str = Field(..., description="Mask or class map location.")
    polygons: list[dict[str, Any]] = Field(
        default_factory=list,
        description="Polygon results or derived regions.",
    )
    positive_ratio: float | None = Field(
        default=None,
        description="Positive mask coverage ratio when artifact inspection is available.",
    )
    warnings: list[str] = Field(
        default_factory=list,
        description="Inference sanity warnings that should be surfaced to operators.",
    )


class ReportInputRAG(BaseSchema):
    """RAG section payload for the report."""

    summary: str = Field(..., description="Knowledge summary for the report.")
    sources: list[str] = Field(default_factory=list, description="Knowledge sources.")
    results: list[dict[str, Any]] = Field(
        default_factory=list,
        description="Structured retrieved chunks.",
    )


class ReportInputConfidence(BaseSchema):
    """Confidence section payload for the report."""

    image_confidence: float = Field(..., description="Image confidence score.")
    text_confidence: float = Field(..., description="Text confidence score.")
    workflow_confidence: float = Field(..., description="Workflow confidence score.")
    final_confidence: float = Field(..., description="Final fused confidence.")
    final_label: str = Field(..., description="Final confidence label.")
    explanation: str = Field(..., description="Human-readable explanation.")
    warnings: list[str] = Field(
        default_factory=list,
        description="Warnings attached to the confidence evaluation.",
    )


class ReportRequest(BaseSchema):
    """Request payload for generating a report."""

    request_id: str = Field(..., description="Workflow request identifier.")
    title: str = Field(..., description="Report title.")
    user_query: str = Field(..., description="Original user query.")
    region: str | None = Field(default=None, description="Target region.")
    crop_type: str | None = Field(default=None, description="Target crop type.")
    task_type: str | None = Field(default=None, description="Target task type.")
    summary: ReportInputSummary = Field(..., description="Summary block content.")
    inference: ReportInputInference | None = Field(
        default=None,
        description="Inference details when available.",
    )
    rag: ReportInputRAG | None = Field(
        default=None,
        description="Retrieved knowledge details when available.",
    )
    confidence: ReportInputConfidence | None = Field(
        default=None,
        description="Confidence details when available.",
    )
    extra_metadata: dict[str, Any] = Field(
        default_factory=dict,
        description="Additional metadata for future templates and exports.",
    )


class ReportResult(BaseSchema):
    """Generated report output."""

    report_id: str = Field(..., description="Stable report identifier.")
    report_title: str = Field(..., description="Report title.")
    html: str | None = Field(default=None, description="Embedded HTML when enabled.")
    report_path: str = Field(..., description="Local HTML report path.")
    generated_at: datetime = Field(..., description="Report generation time.")
    sections: list[str] = Field(
        default_factory=list,
        description="Section identifiers rendered in the report.",
    )
    chart_context: dict[str, Any] = Field(
        default_factory=dict,
        description="Chart data reserved for future visual rendering.",
    )


class ReportResponse(BaseSchema):
    """API response for report generation."""

    request_id: str = Field(..., description="Original workflow request identifier.")
    success: bool = Field(..., description="Whether report generation succeeded.")
    result: ReportResult | None = Field(
        default=None,
        description="Generated report details when successful.",
    )
    message: str = Field(..., description="Human-readable generation outcome.")
