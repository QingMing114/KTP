"""Focused tests for the migrated baldness RF pipeline."""

from __future__ import annotations

import os
from pathlib import Path

import numpy as np
import pytest
import rasterio
from rasterio.transform import from_origin

from ml.baldness_rf.pipeline import run_baldness_rf_pipeline

EXTERNAL_RF_MODEL_PATH = Path(
    os.environ.get("KTP_TEST_RF_MODEL_PATH", "var/models/baldness/rf_model.pkl")
)


def _write_multiband_demo_tiff(tmp_path: Path) -> Path:
    image_path = tmp_path / "demo_multiband.tif"
    bands = np.zeros((6, 24, 24), dtype=np.float32)
    for band_index in range(6):
        bands[band_index] = 15.0 + band_index * 7.5

    bands[0, 6:18, 6:18] = 28.0
    bands[1, 6:18, 6:18] = 44.0
    bands[2, 6:18, 6:18] = 60.0
    bands[3, 6:18, 6:18] = 76.0
    bands[4, 6:18, 6:18] = 92.0
    bands[5, 6:18, 6:18] = 136.0

    with rasterio.open(
        image_path,
        "w",
        driver="GTiff",
        height=bands.shape[1],
        width=bands.shape[2],
        count=bands.shape[0],
        dtype="float32",
        transform=from_origin(100, 100, 1, 1),
    ) as dst:
        dst.write(bands)
    return image_path


def test_baldness_rf_pipeline_runs_on_small_multiband_tif(tmp_path: Path) -> None:
    if not EXTERNAL_RF_MODEL_PATH.exists():
        pytest.skip("external RF model is not available in this environment")

    image_path = _write_multiband_demo_tiff(tmp_path)
    result = run_baldness_rf_pipeline(
        input_image_path=image_path,
        model_path=EXTERNAL_RF_MODEL_PATH,
        output_dir=tmp_path / "outputs",
    )

    assert Path(result.classification_map_path).exists()
    assert Path(result.confidence_map_path).exists()
    assert result.confidence >= 0.0
    assert result.affected_area >= 0.0
