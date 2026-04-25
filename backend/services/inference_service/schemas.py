"""Pydantic schemas for the inference service."""

from __future__ import annotations

from typing import Any

from pydantic import Field

from shared.schemas.common import BaseSchema


class InferenceRequest(BaseSchema):
    """Request payload for running an inference job."""

    request_id: str = Field(..., description="Stable request identifier.")
    region: str = Field(..., description="Target region identifier.")
    crop_type: str = Field(..., description="Target crop type.")
    task_type: str | None = Field(
        default=None,
        description="Target task type. Defaults to the service config value.",
    )
    image_path: str | None = Field(
        default=None,
        description="Local image path for this phase. Optional for LAI inversion using reflectance data.",
    )
    use_mock: bool | None = Field(
        default=None,
        description="Whether to force the mock predictor. Defaults to the service config value.",
    )
    extra_params: dict[str, Any] = Field(
        default_factory=dict,
        description="Additional predictor or preprocessing parameters.",
    )


class PolygonResult(BaseSchema):
    """Structured polygon-like region output."""

    id: str = Field(..., description="Polygon identifier.")
    points: list[tuple[float, float]] = Field(
        default_factory=list,
        description="Polygon coordinates in image pixel space.",
    )


class PredictionClassSummary(BaseSchema):
    """Structured summary for one predicted class."""

    class_value: int = Field(..., description="Predicted class value.")
    label: str | None = Field(default=None, description="Resolved human-readable class label.")
    count: int = Field(..., description="Pixel count for this class.")
    ratio: float = Field(..., description="Pixel ratio for this class.")
    mean_confidence: float | None = Field(
        default=None,
        description="Mean max-probability for pixels in this class.",
    )


class InferenceResult(BaseSchema):
    """Structured inference payload consumed by later services."""

    mask_uri: str = Field(..., description="Filesystem path to the generated mask.")
    affected_area: float = Field(..., description="Affected area in placeholder pixel units.")
    confidence: float = Field(..., description="Overall inference confidence.")
    polygons: list[PolygonResult] = Field(
        default_factory=list,
        description="Structured polygon outputs.",
    )
    model_name: str = Field(..., description="Resolved model name.")
    model_version: str = Field(..., description="Resolved model version.")
    artifact_uri: str = Field(..., description="Resolved artifact URI.")
    raw_prediction_uri: str | None = Field(
        default=None,
        description="Raw class-map path when a derived target mask is produced.",
    )
    confidence_map_uri: str | None = Field(
        default=None,
        description="Confidence raster path when available.",
    )
    warnings: list[str] = Field(
        default_factory=list,
        description="Warnings about model semantics or prediction interpretation.",
    )
    class_distribution: list[PredictionClassSummary] = Field(
        default_factory=list,
        description="Per-class distribution for multi-class outputs.",
    )
    class_labels: dict[str, str] = Field(
        default_factory=dict,
        description="Resolved class labels keyed by class value.",
    )
    target_classes: list[int] = Field(
        default_factory=list,
        description="Classes selected as the target mask.",
    )


class InferenceResponse(BaseSchema):
    """API response for inference execution."""

    request_id: str = Field(..., description="Original request identifier.")
    success: bool = Field(..., description="Whether inference completed successfully.")
    result: InferenceResult | None = Field(
        default=None,
        description="Structured inference result when successful.",
    )
    message: str = Field(..., description="Human-readable execution outcome.")


class ResolvedModelMetadata(BaseSchema):
    """Resolved model metadata returned by the model registry adapter."""

    model_id: int = Field(..., description="Resolved model identifier.")
    model_name: str = Field(..., description="Resolved model name.")
    model_version: str = Field(..., description="Resolved model version.")
    artifact_uri: str = Field(..., description="Resolved artifact URI.")
    status: str | None = Field(default=None, description="Model lifecycle status.")
    metrics_json: dict[str, Any] | None = Field(
        default=None,
        description="Optional model metadata used for downstream interpretation.",
    )
    description: str | None = Field(default=None, description="Optional model description.")
