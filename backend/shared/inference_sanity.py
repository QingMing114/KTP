"""Shared helpers for basic sanity inspection of inference mask artifacts."""

from __future__ import annotations

import logging
from pathlib import Path

import numpy as np
import rasterio
from PIL import Image, UnidentifiedImageError
from pydantic import Field
from rasterio.errors import RasterioIOError

from shared.schemas.common import BaseSchema

logger = logging.getLogger(__name__)


class MaskSanityResult(BaseSchema):
    """Structured summary of a local mask artifact inspection."""

    mask_uri: str | None = Field(default=None, description="Resolved mask path or URI.")
    available: bool = Field(..., description="Whether the artifact could be loaded.")
    total_pixels: int = Field(..., description="Number of valid inspected pixels.")
    positive_pixels: int = Field(..., description="Number of positive pixels.")
    positive_ratio: float = Field(..., description="Positive pixel ratio in [0, 1].")
    unique_value_count: int = Field(..., description="Unique value count in the mask.")
    warnings: list[str] = Field(
        default_factory=list,
        description="Human-readable warnings about suspicious mask structure.",
    )
    summary: str = Field(..., description="Short inspection summary.")


def inspect_mask_artifact(mask_uri: str | None) -> MaskSanityResult:
    """Inspect a local mask artifact and surface simple degeneracy warnings."""
    resolved_uri = str(mask_uri).strip() if mask_uri else ""
    if not resolved_uri:
        return MaskSanityResult(
            mask_uri=mask_uri,
            available=False,
            total_pixels=0,
            positive_pixels=0,
            positive_ratio=0.0,
            unique_value_count=0,
            warnings=[],
            summary="mask artifact was not provided",
        )

    path = _resolve_local_path(resolved_uri)
    if not path.exists():
        return MaskSanityResult(
            mask_uri=resolved_uri,
            available=False,
            total_pixels=0,
            positive_pixels=0,
            positive_ratio=0.0,
            unique_value_count=0,
            warnings=["mask artifact is missing on disk"],
            summary="mask artifact could not be inspected because the file is missing",
        )

    try:
        mask_array = _load_mask_array(path)
    except (RasterioIOError, UnidentifiedImageError, OSError, ValueError) as exc:
        logger.warning(
            "mask_sanity_inspection_failed | mask_uri=%s | detail=%s",
            resolved_uri,
            exc,
        )
        return MaskSanityResult(
            mask_uri=resolved_uri,
            available=False,
            total_pixels=0,
            positive_pixels=0,
            positive_ratio=0.0,
            unique_value_count=0,
            warnings=["mask artifact could not be decoded"],
            summary="mask artifact exists but could not be decoded for inspection",
        )

    data = np.asarray(mask_array)
    if data.ndim == 3:
        data = data[..., 0]
    if data.ndim != 2:
        raise ValueError(f"unsupported mask dimensions: {data.shape}")

    finite_mask = np.isfinite(data)
    valid_pixels = data[finite_mask]
    total_pixels = int(valid_pixels.size)
    if total_pixels == 0:
        return MaskSanityResult(
            mask_uri=resolved_uri,
            available=True,
            total_pixels=0,
            positive_pixels=0,
            positive_ratio=0.0,
            unique_value_count=0,
            warnings=["mask artifact contains no valid pixels"],
            summary="mask artifact was loaded but contains no valid pixels",
        )

    positive_pixels = int(np.count_nonzero(valid_pixels > 0))
    positive_ratio = positive_pixels / total_pixels
    unique_value_count = int(np.unique(valid_pixels).size)
    warnings = _build_warnings(
        positive_pixels=positive_pixels,
        positive_ratio=positive_ratio,
        unique_value_count=unique_value_count,
    )
    summary = _build_summary(
        positive_pixels=positive_pixels,
        total_pixels=total_pixels,
        positive_ratio=positive_ratio,
        warnings=warnings,
    )
    return MaskSanityResult(
        mask_uri=resolved_uri,
        available=True,
        total_pixels=total_pixels,
        positive_pixels=positive_pixels,
        positive_ratio=round(float(np.clip(positive_ratio, 0.0, 1.0)), 6),
        unique_value_count=unique_value_count,
        warnings=warnings,
        summary=summary,
    )


def _resolve_local_path(mask_uri: str) -> Path:
    if mask_uri.startswith("file://"):
        return Path(mask_uri.removeprefix("file://")).expanduser()
    return Path(mask_uri).expanduser()


def _load_mask_array(path: Path) -> np.ndarray:
    try:
        with rasterio.open(path) as dataset:
            return dataset.read(1)
    except RasterioIOError:
        with Image.open(path) as image:
            return np.asarray(image)


def _build_warnings(
    *,
    positive_pixels: int,
    positive_ratio: float,
    unique_value_count: int,
) -> list[str]:
    warnings: list[str] = []
    if positive_pixels > 0 and positive_ratio == 1.0:
        warnings.append("mask marks every valid pixel as positive")
    if positive_pixels > 0 and positive_ratio >= 0.98:
        warnings.append("mask coverage is near-total and should be reviewed manually")
    if positive_pixels > 0 and positive_ratio == 1.0 and unique_value_count == 1:
        warnings.append("mask contains a single positive value across the full image")
    return warnings


def _build_summary(
    *,
    positive_pixels: int,
    total_pixels: int,
    positive_ratio: float,
    warnings: list[str],
) -> str:
    coverage_text = (
        f"mask covers {positive_pixels} of {total_pixels} valid pixels "
        f"({positive_ratio:.2%} positive coverage)"
    )
    if not warnings:
        return coverage_text
    return f"{coverage_text}; {'; '.join(warnings)}"
