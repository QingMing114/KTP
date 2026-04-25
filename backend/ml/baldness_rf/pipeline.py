"""End-to-end RF pipeline for baldness detection inference."""

from __future__ import annotations

from dataclasses import dataclass
import logging
from pathlib import Path
import tempfile
import threading
from uuid import uuid4

import numpy as np
import rasterio

from ml.baldness_rf.classifier import run_rf_inference
from ml.baldness_rf.feature_extractor import extract_features

logger = logging.getLogger(__name__)


@dataclass(slots=True)
class BaldnessRfPipelineResult:
    """Structured result from the migrated baldness RF pipeline."""

    classification_map_path: str
    confidence_map_path: str
    affected_area: float
    confidence: float
    polygons: list[list[tuple[float, float]]]


def _ensure_not_cancelled(cancel_event: threading.Event | None) -> None:
    if cancel_event and cancel_event.is_set():
        raise RuntimeError("task cancelled")


def _build_polygons(mask: np.ndarray) -> list[list[tuple[float, float]]]:
    positive_y, positive_x = np.where(mask)
    if positive_y.size == 0 or positive_x.size == 0:
        return []

    min_y, max_y = int(positive_y.min()), int(positive_y.max()) + 1
    min_x, max_x = int(positive_x.min()), int(positive_x.max()) + 1
    return [[
        (float(min_x), float(min_y)),
        (float(max_x), float(min_y)),
        (float(max_x), float(max_y)),
        (float(min_x), float(max_y)),
    ]]


def summarize_outputs(
    *,
    classification_map_path: str | Path,
    confidence_map_path: str | Path,
) -> BaldnessRfPipelineResult:
    """Summarize classification and confidence GeoTIFF outputs into API-ready stats."""
    class_path = str(classification_map_path)
    conf_path = str(confidence_map_path)
    with rasterio.open(class_path) as src_class:
        class_map = src_class.read(1)
    with rasterio.open(conf_path) as src_conf:
        confidence_map = src_conf.read(1)

    positive_mask = class_map > 0
    affected_area = float(int(positive_mask.sum()))

    if positive_mask.any():
        confidence = float(np.nanmean(confidence_map[positive_mask]))
    else:
        finite_conf = confidence_map[np.isfinite(confidence_map)]
        confidence = float(np.nanmean(finite_conf)) if finite_conf.size else 0.0

    return BaldnessRfPipelineResult(
        classification_map_path=class_path,
        confidence_map_path=conf_path,
        affected_area=affected_area,
        confidence=float(np.clip(confidence, 0.0, 1.0)),
        polygons=_build_polygons(positive_mask),
    )


def run_baldness_rf_pipeline(
    *,
    input_image_path: str | Path,
    model_path: str | Path,
    output_dir: str | Path,
    cancel_event: threading.Event | None = None,
) -> BaldnessRfPipelineResult:
    """Run the migrated baldness RF pipeline from raw image to classified outputs."""
    input_path = str(input_image_path)
    model_file = str(model_path)
    output_root = Path(output_dir)
    output_root.mkdir(parents=True, exist_ok=True)
    logger.info(
        "baldness_rf_pipeline_started | image=%s | model=%s | output_dir=%s",
        input_path,
        model_file,
        output_root,
    )

    temp_feature_path = (
        Path(tempfile.gettempdir()) / f"ktp_baldness_features_{uuid4().hex}.tif"
    )
    temp_sidecar_path = temp_feature_path.with_name(f"{temp_feature_path.stem}_bands.json")
    class_map_path = output_root / "class.tif"
    confidence_map_path = output_root / "confidence.tif"

    try:
        _ensure_not_cancelled(cancel_event)
        extract_features(
            input_path,
            temp_feature_path,
            win_size=5,
            cancel_event=cancel_event,
        )
        _ensure_not_cancelled(cancel_event)
        run_rf_inference(
            input_feature_path=temp_feature_path,
            model_path=model_file,
            output_class_path=class_map_path,
            output_conf_path=confidence_map_path,
            cancel_event=cancel_event,
        )
        _ensure_not_cancelled(cancel_event)
        result = summarize_outputs(
            classification_map_path=class_map_path,
            confidence_map_path=confidence_map_path,
        )
        logger.info(
            "baldness_rf_pipeline_succeeded | class_path=%s | confidence_path=%s",
            result.classification_map_path,
            result.confidence_map_path,
        )
        return result
    finally:
        if temp_feature_path.exists():
            temp_feature_path.unlink()
        if temp_sidecar_path.exists():
            temp_sidecar_path.unlink()
