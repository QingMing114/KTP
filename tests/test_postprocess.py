"""Tests for the inference service postprocessing helpers."""

from __future__ import annotations

from pathlib import Path

import numpy as np
import rasterio
from rasterio.transform import from_origin

from services.inference_service.postprocessing.postprocess import build_inference_result
from services.inference_service.predictors.base import PredictionOutput
from services.inference_service.schemas import ResolvedModelMetadata


def test_build_inference_result_saves_mask_and_shapes_payload(tmp_path: Path) -> None:
    predictor_output = PredictionOutput(
        mask=np.array(
            [
                [0, 0, 0, 0],
                [0, 1, 1, 0],
                [0, 1, 1, 0],
                [0, 0, 0, 0],
            ],
            dtype=np.uint8,
        ),
        affected_area=4.0,
        confidence=0.83,
        polygons=[[(1.0, 1.0), (3.0, 1.0), (3.0, 3.0), (1.0, 3.0)]],
    )
    model_metadata = ResolvedModelMetadata(
        model_id=11,
        model_name="baldness-rf",
        model_version="v2",
        artifact_uri="mock://models/baldness-rf/v2/model.pkl",
        status="ready",
    )

    result = build_inference_result(
        request_id="req-postprocess-001",
        predictor_output=predictor_output,
        model_metadata=model_metadata,
        mask_output_dir=str(tmp_path / "masks"),
    )

    assert Path(result.mask_uri).exists()
    assert result.affected_area == 4.0
    assert result.confidence == 0.83
    assert result.model_name == "baldness-rf"
    assert result.model_version == "v2"
    assert len(result.polygons) == 1


def test_build_inference_result_derives_target_mask_from_multiclass_map(
    tmp_path: Path,
) -> None:
    class_map_path = tmp_path / "class.tif"
    confidence_map_path = tmp_path / "confidence.tif"
    class_map = np.array(
        [
            [4, 4, 4, 4],
            [4, 1, 1, 4],
            [4, 1, 2, 4],
            [4, 4, 4, 4],
        ],
        dtype=np.uint16,
    )
    confidence_map = np.full((4, 4), 0.9, dtype=np.float32)
    confidence_map[1:3, 1:3] = 0.72

    with rasterio.open(
        class_map_path,
        "w",
        driver="GTiff",
        height=4,
        width=4,
        count=1,
        dtype="uint16",
        transform=from_origin(100, 100, 1, 1),
    ) as dst:
        dst.write(class_map, 1)

    with rasterio.open(
        confidence_map_path,
        "w",
        driver="GTiff",
        height=4,
        width=4,
        count=1,
        dtype="float32",
        transform=from_origin(100, 100, 1, 1),
    ) as dst:
        dst.write(confidence_map, 1)

    predictor_output = PredictionOutput(
        mask=None,
        mask_uri=str(class_map_path),
        confidence=0.88,
        metadata={
            "prediction_kind": "class_map",
            "confidence_map_uri": str(confidence_map_path),
        },
    )
    model_metadata = ResolvedModelMetadata(
        model_id=12,
        model_name="baldness-rf",
        model_version="v3",
        artifact_uri="mock://models/baldness-rf/v3/model.pkl",
        status="ready",
        metrics_json={
            "prediction_class_semantics": {
                "class_labels": {
                    "1": "baldness",
                    "2": "water",
                    "3": "other_vegetation",
                    "4": "crop",
                },
                "target_classes": [1],
            }
        },
    )

    result = build_inference_result(
        request_id="req-postprocess-002",
        predictor_output=predictor_output,
        model_metadata=model_metadata,
        mask_output_dir=str(tmp_path / "masks"),
    )

    assert Path(result.mask_uri).exists()
    assert result.raw_prediction_uri == str(class_map_path)
    assert result.target_classes == [1]
    assert result.affected_area == 3.0
    assert result.class_labels["1"] == "baldness"
    assert len(result.class_distribution) == 3
    assert result.warnings
