"""Postprocessing helpers for inference outputs."""

from __future__ import annotations

from pathlib import Path
from typing import Any, Mapping

import numpy as np
import rasterio
from PIL import Image

from services.inference_service.class_semantics import (
    PredictionClassSemantics,
    resolve_prediction_class_semantics,
)
from services.inference_service.predictors.base import PredictionOutput
from services.inference_service.schemas import (
    InferenceResult,
    PolygonResult,
    PredictionClassSummary,
    ResolvedModelMetadata,
)


def _save_mask(mask: np.ndarray, *, request_id: str, mask_output_dir: str) -> str:
    output_dir = Path(mask_output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)
    output_path = output_dir / f"{request_id}_mask.png"
    mask_image = np.where(mask > 0, 255, 0).astype(np.uint8)
    Image.fromarray(mask_image).save(output_path)
    return str(output_path)


def _save_mask_geotiff(
    *,
    source_raster_path: str,
    mask: np.ndarray,
    request_id: str,
    mask_output_dir: str,
) -> str:
    output_dir = Path(mask_output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)
    output_path = output_dir / f"{request_id}_target_mask.tif"
    with rasterio.open(source_raster_path) as src:
        profile = src.profile.copy()
        dataset_mask = src.dataset_mask()
        profile.update(count=1, dtype=rasterio.uint8, nodata=0)
        with rasterio.open(output_path, "w", **profile) as dst:
            dst.write(mask.astype(np.uint8), 1)
            dst.write_mask(dataset_mask)
    return str(output_path)


def _build_polygons_from_mask(mask: np.ndarray) -> list[PolygonResult]:
    positive_y, positive_x = np.where(mask > 0)
    if positive_y.size == 0 or positive_x.size == 0:
        return []

    min_y, max_y = int(positive_y.min()), int(positive_y.max()) + 1
    min_x, max_x = int(positive_x.min()), int(positive_x.max()) + 1
    return [
        PolygonResult(
            id="poly-1",
            points=[
                (float(min_x), float(min_y)),
                (float(max_x), float(min_y)),
                (float(max_x), float(max_y)),
                (float(min_x), float(max_y)),
            ],
        )
    ]


def _build_class_distribution(
    *,
    class_map: np.ndarray,
    confidence_map: np.ndarray | None,
    semantics: PredictionClassSemantics | None,
) -> list[PredictionClassSummary]:
    values, counts = np.unique(class_map, return_counts=True)
    total_pixels = int(class_map.size) or 1
    summaries: list[PredictionClassSummary] = []
    for class_value, count in zip(values.tolist(), counts.tolist(), strict=False):
        class_mask = class_map == class_value
        mean_confidence = None
        if confidence_map is not None and class_mask.any():
            masked_conf = confidence_map[class_mask]
            finite_conf = masked_conf[np.isfinite(masked_conf)]
            if finite_conf.size:
                mean_confidence = round(float(np.mean(finite_conf)), 6)
        summaries.append(
            PredictionClassSummary(
                class_value=int(class_value),
                label=semantics.class_labels.get(int(class_value)) if semantics else None,
                count=int(count),
                ratio=round(float(count / total_pixels), 6),
                mean_confidence=mean_confidence,
            )
        )
    return summaries


def _derive_target_classes(
    *,
    class_map: np.ndarray,
    semantics: PredictionClassSemantics | None,
) -> list[int]:
    unique_non_background = sorted(int(value) for value in np.unique(class_map) if int(value) != 0)
    if semantics and semantics.target_classes:
        return list(semantics.target_classes)
    if len(unique_non_background) <= 1:
        return unique_non_background
    raise ValueError(
        "multi-class prediction requires prediction_class_semantics with target_classes"
    )


def _build_result_from_class_map(
    *,
    request_id: str,
    predictor_output: PredictionOutput,
    model_metadata: ResolvedModelMetadata,
    mask_output_dir: str,
    extra_params: Mapping[str, Any] | None,
    default_class_semantics_json: str | None,
) -> tuple[str, float, float, list[PolygonResult], list[str], list[PredictionClassSummary], dict[str, str], list[int], str | None]:
    if not predictor_output.mask_uri:
        raise ValueError("class-map predictor output must provide mask_uri")

    class_map_uri = predictor_output.mask_uri
    confidence_map_uri = predictor_output.metadata.get("confidence_map_uri")
    with rasterio.open(class_map_uri) as src:
        class_map = src.read(1)

    confidence_map = None
    if isinstance(confidence_map_uri, str) and confidence_map_uri:
        with rasterio.open(confidence_map_uri) as src:
            confidence_map = src.read(1).astype(np.float32)

    semantics = resolve_prediction_class_semantics(
        model_metrics=model_metadata.metrics_json,
        extra_params=extra_params,
        config_default_json=default_class_semantics_json,
    )
    target_classes = _derive_target_classes(class_map=class_map, semantics=semantics)
    target_mask = np.isin(class_map, target_classes).astype(np.uint8)
    mask_uri = _save_mask_geotiff(
        source_raster_path=class_map_uri,
        mask=target_mask,
        request_id=request_id,
        mask_output_dir=mask_output_dir,
    )
    affected_area = float(int(np.count_nonzero(target_mask)))
    confidence = float(np.clip(predictor_output.confidence, 0.0, 1.0))
    if confidence_map is not None and affected_area > 0:
        target_conf = confidence_map[target_mask > 0]
        finite_conf = target_conf[np.isfinite(target_conf)]
        if finite_conf.size:
            confidence = float(np.clip(np.mean(finite_conf), 0.0, 1.0))

    warnings = list(predictor_output.metadata.get("warnings", []))
    if semantics and semantics.source:
        warnings.append(f"class semantics loaded from {semantics.source}")
    class_distribution = _build_class_distribution(
        class_map=class_map,
        confidence_map=confidence_map,
        semantics=semantics,
    )
    class_labels = {
        str(key): value for key, value in (semantics.class_labels.items() if semantics else [])
    }
    polygons = _build_polygons_from_mask(target_mask)
    return (
        mask_uri,
        affected_area,
        round(confidence, 6),
        polygons,
        warnings,
        class_distribution,
        class_labels,
        target_classes,
        str(confidence_map_uri) if confidence_map_uri else None,
    )


def build_inference_result(
    *,
    request_id: str,
    predictor_output: PredictionOutput,
    model_metadata: ResolvedModelMetadata,
    mask_output_dir: str,
    extra_params: Mapping[str, Any] | None = None,
    default_class_semantics_json: str | None = None,
) -> InferenceResult:
    """Convert raw predictor output into the structured API response payload."""
    raw_prediction_uri = None
    confidence_map_uri = None
    warnings: list[str] = []
    class_distribution: list[PredictionClassSummary] = []
    class_labels: dict[str, str] = {}
    target_classes: list[int] = []

    if predictor_output.mask_uri:
        prediction_kind = str(predictor_output.metadata.get("prediction_kind", "binary_mask"))
        if prediction_kind == "class_map":
            raw_prediction_uri = predictor_output.mask_uri
            (
                mask_uri,
                affected_area,
                confidence,
                polygons,
                warnings,
                class_distribution,
                class_labels,
                target_classes,
                confidence_map_uri,
            ) = _build_result_from_class_map(
                request_id=request_id,
                predictor_output=predictor_output,
                model_metadata=model_metadata,
                mask_output_dir=mask_output_dir,
                extra_params=extra_params,
                default_class_semantics_json=default_class_semantics_json,
            )
        else:
            mask_uri = predictor_output.mask_uri
            affected_area = float(predictor_output.affected_area)
            confidence = float(np.clip(predictor_output.confidence, 0.0, 1.0))
            polygons = [
                PolygonResult(
                    id=f"poly-{index}",
                    points=[(float(x), float(y)) for x, y in polygon],
                )
                for index, polygon in enumerate(predictor_output.polygons, start=1)
            ]
            if predictor_output.metadata.get("confidence_map_uri"):
                confidence_map_uri = str(predictor_output.metadata.get("confidence_map_uri"))
    elif predictor_output.mask is not None:
        mask_uri = _save_mask(
            predictor_output.mask,
            request_id=request_id,
            mask_output_dir=mask_output_dir,
        )
        affected_area = float(
            predictor_output.affected_area
            if predictor_output.affected_area >= 0
            else np.count_nonzero(predictor_output.mask)
        )
        confidence = float(np.clip(predictor_output.confidence, 0.0, 1.0))
        polygons = [
            PolygonResult(
                id=f"poly-{index}",
                points=[(float(x), float(y)) for x, y in polygon],
            )
            for index, polygon in enumerate(predictor_output.polygons, start=1)
        ]
    else:
        raise ValueError("predictor output must include either mask data or a mask_uri")

    return InferenceResult(
        mask_uri=mask_uri,
        affected_area=affected_area,
        confidence=confidence,
        polygons=polygons,
        model_name=model_metadata.model_name,
        model_version=model_metadata.model_version,
        artifact_uri=model_metadata.artifact_uri,
        raw_prediction_uri=raw_prediction_uri,
        confidence_map_uri=confidence_map_uri,
        warnings=warnings,
        class_distribution=class_distribution,
        class_labels=class_labels,
        target_classes=target_classes,
    )
