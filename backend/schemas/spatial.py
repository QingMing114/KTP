"""Typed contracts for the map-first spatial analysis product surface.

These are intentionally independent from the chat/runtime schemas.  A map
analysis is reproducible from its AOI, the user-selected imagery item and
explicit parameters; it is not a free-form LLM tool invocation.
"""

from __future__ import annotations

import math
from datetime import date, timedelta
from typing import Any, Literal

from pydantic import BaseModel, Field, field_validator, model_validator


EARTH_RADIUS_METERS = 6_371_008.8
MIN_AOI_HECTARES = 0.01
MAX_AOI_HECTARES = 100_000.0
PROSAIL_REFLECTANCE_BANDS = ("B02", "B03", "B04", "B07", "B08")


def _orientation(first: tuple[float, float], second: tuple[float, float], third: tuple[float, float]) -> float:
    return (second[0] - first[0]) * (third[1] - first[1]) - (second[1] - first[1]) * (third[0] - first[0])


def _on_segment(first: tuple[float, float], second: tuple[float, float], point: tuple[float, float]) -> bool:
    return (
        min(first[0], second[0]) <= point[0] <= max(first[0], second[0])
        and min(first[1], second[1]) <= point[1] <= max(first[1], second[1])
    )


def _segments_intersect(
    first_start: tuple[float, float],
    first_end: tuple[float, float],
    second_start: tuple[float, float],
    second_end: tuple[float, float],
) -> bool:
    values = (
        _orientation(first_start, first_end, second_start),
        _orientation(first_start, first_end, second_end),
        _orientation(second_start, second_end, first_start),
        _orientation(second_start, second_end, first_end),
    )
    if (values[0] > 0) != (values[1] > 0) and (values[2] > 0) != (values[3] > 0):
        return True
    return (
        (values[0] == 0 and _on_segment(first_start, first_end, second_start))
        or (values[1] == 0 and _on_segment(first_start, first_end, second_end))
        or (values[2] == 0 and _on_segment(second_start, second_end, first_start))
        or (values[3] == 0 and _on_segment(second_start, second_end, first_end))
    )


def _has_self_intersection(vertices: list[tuple[float, float]]) -> bool:
    segment_count = len(vertices)
    for first_index in range(segment_count):
        first_start = vertices[first_index]
        first_end = vertices[(first_index + 1) % segment_count]
        for second_index in range(first_index + 1, segment_count):
            if (first_index + 1) % segment_count == second_index or (second_index + 1) % segment_count == first_index:
                continue
            second_start = vertices[second_index]
            second_end = vertices[(second_index + 1) % segment_count]
            if _segments_intersect(first_start, first_end, second_start, second_end):
                return True
    return False


def _spherical_area_hectares(ring: list[tuple[float, float]]) -> float:
    accumulator = 0.0
    radians = math.pi / 180
    for first, second in zip(ring, ring[1:]):
        accumulator += (
            (second[0] - first[0]) * radians
            * (2 + math.sin(first[1] * radians) + math.sin(second[1] * radians))
        )
    return abs(accumulator * EARTH_RADIUS_METERS ** 2 / 2) / 10_000


class GeoJsonGeometry(BaseModel):
    """Minimal WGS84 GeoJSON geometry accepted by the spatial API."""

    type: Literal["Polygon"]
    coordinates: list[Any]

    @field_validator("coordinates")
    @classmethod
    def coordinates_must_be_valid_polygon(cls, value: list[Any]) -> list[Any]:
        if len(value) != 1 or not isinstance(value[0], list):
            raise ValueError("AOI must contain exactly one Polygon exterior ring")
        source_ring = value[0]
        if len(source_ring) < 4:
            raise ValueError("AOI exterior ring must contain at least four coordinates")
        ring: list[tuple[float, float]] = []
        for coordinate in source_ring:
            if not isinstance(coordinate, (list, tuple)) or len(coordinate) != 2:
                raise ValueError("AOI coordinates must be [longitude, latitude] pairs")
            longitude, latitude = coordinate
            if (
                isinstance(longitude, bool)
                or isinstance(latitude, bool)
                or not isinstance(longitude, (int, float))
                or not isinstance(latitude, (int, float))
                or not math.isfinite(float(longitude))
                or not math.isfinite(float(latitude))
                or not -180 <= float(longitude) <= 180
                or not -90 <= float(latitude) <= 90
            ):
                raise ValueError("AOI coordinates must be finite WGS84 longitude/latitude values")
            ring.append((float(longitude), float(latitude)))
        if ring[0] != ring[-1]:
            raise ValueError("AOI exterior ring must be closed")
        vertices = ring[:-1]
        if len(set(vertices)) < 3:
            raise ValueError("AOI exterior ring must contain at least three unique vertices")
        if _has_self_intersection(vertices):
            raise ValueError("AOI exterior ring must not self-intersect")
        area = _spherical_area_hectares(ring)
        if area < MIN_AOI_HECTARES:
            raise ValueError(f"AOI area must be at least {MIN_AOI_HECTARES} hectares")
        if area > MAX_AOI_HECTARES:
            raise ValueError(f"AOI area must not exceed {MAX_AOI_HECTARES:g} hectares")
        return value

    def area_hectares(self) -> float:
        ring = [(float(point[0]), float(point[1])) for point in self.coordinates[0]]
        return _spherical_area_hectares(ring)


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

    @model_validator(mode="after")
    def validate_reported_area(self) -> "AoiGeometry":
        calculated = self.geometry.area_hectares()
        if self.area_hectares is not None:
            tolerance = max(0.05, calculated * 0.02)
            if abs(self.area_hectares - calculated) > tolerance:
                raise ValueError("AOI area_hectares does not match the submitted geometry")
        self.area_hectares = calculated
        return self


class ImagerySearchRequest(BaseModel):
    """Future Sentinel/STAC search request for one explicit AOI."""

    aoi: AoiGeometry
    start_date: str | None = None
    end_date: str
    max_cloud_cover: float = Field(default=20, ge=0, le=100)
    collection: str = "sentinel-2-l2a"

    @model_validator(mode="after")
    def validate_date_range(self) -> "ImagerySearchRequest":
        if self.start_date is None:
            try:
                self.start_date = (date.fromisoformat(self.end_date) - timedelta(days=90)).isoformat()
            except ValueError as exc:
                raise ValueError("end_date must use YYYY-MM-DD format") from exc
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
    item_version: str | None = None
    asset_fingerprint: str | None = None
    selection_token: str | None = None
    is_recommended: bool = False
    recommendation_reason: str | None = None


class ImagerySearchResponse(BaseModel):
    items: list[ImageryCandidate] = Field(default_factory=list)
    search_id: str


class LaiAnalysisParameters(BaseModel):
    """Explicit numerical inputs for a reproducible LAI analysis."""

    target_resolution_m: Literal[20] = 20
    bands: list[str] = Field(default_factory=lambda: list(PROSAIL_REFLECTANCE_BANDS))
    top_fraction: float = Field(default=0.01, gt=0, le=0.2)

    @field_validator("bands")
    @classmethod
    def bands_match_prosail_contract(cls, value: list[str]) -> list[str]:
        legacy_default = ["B02", "B03", "B04", "B05", "B06", "B07", "B08", "B8A", "SCL"]
        if value == legacy_default:
            return list(PROSAIL_REFLECTANCE_BANDS)
        if value != list(PROSAIL_REFLECTANCE_BANDS):
            raise ValueError(f"bands must exactly match the PROSAIL contract: {PROSAIL_REFLECTANCE_BANDS}")
        return value

    @field_validator("top_fraction")
    @classmethod
    def top_fraction_is_currently_fixed(cls, value: float) -> float:
        if not math.isclose(value, 0.01, rel_tol=0.0, abs_tol=1e-12):
            raise ValueError("top_fraction is fixed at 0.01 by the current PROSAIL inversion protocol")
        return value


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
    imagery_snapshot: ImageryCandidate | None = None
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
