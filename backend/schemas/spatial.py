"""Typed contracts for the map-first spatial analysis product surface.

These are intentionally independent from the chat/runtime schemas.  A map
analysis is reproducible from its AOI, the user-selected imagery item and
explicit parameters; it is not a free-form LLM tool invocation.
"""

from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel, Field, field_validator, model_validator


class GeoJsonGeometry(BaseModel):
    """Minimal WGS84 GeoJSON geometry accepted by the spatial API."""

    type: Literal["Polygon", "MultiPolygon"]
    coordinates: list[Any]

    @field_validator("coordinates")
    @classmethod
    def coordinates_must_not_be_empty(cls, value: list[Any]) -> list[Any]:
        if not value:
            raise ValueError("GeoJSON coordinates must not be empty")
        return value


class FarmResponse(BaseModel):
    """A farm boundary shown as a navigation preset in the map workspace."""

    farm_id: str
    name: str
    location_label: str
    area_hectares: float = Field(gt=0)
    geometry: GeoJsonGeometry
    is_demo: bool = True
    metadata: dict[str, Any] = Field(default_factory=dict)


class FarmListResponse(BaseModel):
    items: list[FarmResponse] = Field(default_factory=list)


class AoiGeometry(BaseModel):
    """User-drawn AOI.  It is not constrained to a farm boundary."""

    geometry: GeoJsonGeometry
    source: Literal["drawn", "farm", "uploaded"] = "drawn"
    area_hectares: float | None = Field(default=None, gt=0)


class ImagerySearchRequest(BaseModel):
    """Future Sentinel/STAC search request for one explicit AOI."""

    aoi: AoiGeometry
    start_date: str
    end_date: str
    max_cloud_cover: float = Field(default=20, ge=0, le=100)
    collection: str = "sentinel-2-l2a"

    @model_validator(mode="after")
    def validate_date_range(self) -> "ImagerySearchRequest":
        if self.start_date > self.end_date:
            raise ValueError("start_date must be earlier than or equal to end_date")
        return self


class ImageryCandidate(BaseModel):
    """A user-selectable remote-sensing product returned by imagery search."""

    item_id: str
    collection: str = "sentinel-2-l2a"
    acquired_at: str
    cloud_cover: float | None = Field(default=None, ge=0, le=100)
    coverage_percent: float | None = Field(default=None, ge=0, le=100)
    thumbnail_url: str | None = None
    preview_url: str | None = None
    platform: str | None = None
    is_recommended: bool = False
    recommendation_reason: str | None = None


class ImagerySearchResponse(BaseModel):
    items: list[ImageryCandidate] = Field(default_factory=list)
    search_id: str


class LaiAnalysisParameters(BaseModel):
    """Explicit numerical inputs for a reproducible LAI analysis."""

    target_resolution_m: int = Field(default=20, ge=10, le=60)
    bands: list[str] = Field(default_factory=lambda: ["B02", "B03", "B04", "B05", "B06", "B07", "B08", "B8A", "SCL"])
    top_fraction: float = Field(default=0.01, gt=0, le=0.2)


class CreateLaiAnalysisRequest(BaseModel):
    """Future typed submission.  The selected imagery item is mandatory."""

    aoi: AoiGeometry
    imagery_item_id: str = Field(min_length=1)
    imagery_snapshot: ImageryCandidate | None = None
    farm_id: str | None = None
    parameters: LaiAnalysisParameters = Field(default_factory=LaiAnalysisParameters)


class LaiAnalysisSummary(BaseModel):
    analysis_id: str
    submission_id: str | None = None
    farm_id: str | None = None
    status: Literal["queued", "running", "completed", "failed", "cancelled"]
    stage: Literal["accepted", "imagery", "inversion", "report", "completed", "failed"]
    aoi: AoiGeometry
    imagery_item_id: str
    parameters: LaiAnalysisParameters = Field(default_factory=LaiAnalysisParameters)
    created_at: str
    updated_at: str | None = None
    completed_at: str | None = None
    progress_percent: int = Field(default=0, ge=0, le=100)
    detail: str = ""
    progress_data: dict[str, Any] = Field(default_factory=dict)
    artifact_ids: list[str] = Field(default_factory=list)
    result: dict[str, Any] = Field(default_factory=dict)


class AnalysisEvent(BaseModel):
    """SSE payload that maps directly to one updateable Agent UI card."""

    event_id: str
    analysis_id: str
    kind: Literal["user_action", "agent_advice", "imagery_candidates", "progress", "result", "error"]
    stage: str
    detail: str
    progress_percent: int | None = Field(default=None, ge=0, le=100)
    data: dict[str, Any] = Field(default_factory=dict)
    timestamp: str
