"""Tests for the baldness RF diagnostics helpers."""

from __future__ import annotations

from pathlib import Path

import numpy as np
import rasterio
from rasterio.transform import from_origin

from ml.baldness_rf.diagnostics import analyze_input_image, analyze_prediction_outputs


def _write_multiband_demo_tiff(tmp_path: Path) -> Path:
    image_path = tmp_path / "diagnostic_multiband.tif"
    bands = np.zeros((6, 12, 12), dtype=np.float32)
    for band_index in range(6):
        bands[band_index] = (band_index + 1) * 10.0
    bands[:, 3:9, 3:9] += 15.0

    with rasterio.open(
        image_path,
        "w",
        driver="GTiff",
        height=12,
        width=12,
        count=6,
        dtype="float32",
        transform=from_origin(100, 100, 1, 1),
    ) as dst:
        dst.write(bands)
    return image_path


def _write_prediction_outputs(tmp_path: Path) -> tuple[Path, Path]:
    class_path = tmp_path / "class.tif"
    conf_path = tmp_path / "confidence.tif"
    class_map = np.zeros((12, 12), dtype=np.uint16)
    class_map[:, :] = 4
    class_map[:2, :2] = 1
    class_map[2:4, 2:4] = 2
    confidence_map = np.full((12, 12), 0.98, dtype=np.float32)
    confidence_map[:2, :2] = 0.72
    confidence_map[2:4, 2:4] = 0.81

    with rasterio.open(
        class_path,
        "w",
        driver="GTiff",
        height=12,
        width=12,
        count=1,
        dtype="uint16",
        transform=from_origin(100, 100, 1, 1),
    ) as dst:
        dst.write(class_map, 1)

    with rasterio.open(
        conf_path,
        "w",
        driver="GTiff",
        height=12,
        width=12,
        count=1,
        dtype="float32",
        transform=from_origin(100, 100, 1, 1),
    ) as dst:
        dst.write(confidence_map, 1)

    return class_path, conf_path


def test_analyze_input_image_creates_preview_and_band_stats(tmp_path: Path) -> None:
    image_path = _write_multiband_demo_tiff(tmp_path)

    result = analyze_input_image(
        image_path=image_path,
        output_dir=tmp_path,
    )

    assert result.width == 12
    assert result.height == 12
    assert result.band_count == 6
    assert len(result.bands) == 6
    assert Path(result.input_preview_path).exists()


def test_analyze_prediction_outputs_flags_multiclass_collapse(tmp_path: Path) -> None:
    class_path, conf_path = _write_prediction_outputs(tmp_path)

    result = analyze_prediction_outputs(
        class_map_path=class_path,
        confidence_map_path=conf_path,
        output_dir=tmp_path,
        model_classes=[1, 2, 3, 4],
    )

    assert Path(result.class_preview_path).exists()
    assert Path(result.confidence_preview_path).exists()
    assert result.dominant_class == 4
    assert result.non_zero_ratio == 1.0
    assert any("binary summarization rule" in warning for warning in result.warnings)
    assert any(item.class_value == 4 for item in result.class_distribution)
