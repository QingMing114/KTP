"""Tests for the real baldness demo script helpers."""

from __future__ import annotations

from pathlib import Path

import numpy as np
import rasterio
from rasterio.transform import from_origin

from scripts.demo_baldness_real_flow import (
    build_runtime_paths,
    configure_baldness_demo_environment,
    crop_multiband_image,
)


def test_build_runtime_paths_for_baldness_demo(tmp_path: Path) -> None:
    paths = build_runtime_paths(str(tmp_path))

    assert paths["root"] == str(tmp_path.resolve())
    assert paths["database_path"].endswith("registry.db")
    assert paths["rf_work_dir"].endswith("rf_outputs")
    assert paths["input_dir"].endswith("inputs")
    assert paths["visualization_output_dir"].endswith("visualizations")
    assert paths["response_path"].endswith("response.json")


def test_configure_baldness_demo_environment_sets_expected_env(tmp_path: Path) -> None:
    paths = configure_baldness_demo_environment(
        base_dir=str(tmp_path),
        agent_backend="heuristic",
        model_dir="/models/qwen",
        runtime_python="python",
        cuda_visible_devices="0,6",
    )

    assert Path(paths["root"]).exists()
    assert paths["database_path"].endswith("registry.db")
    assert Path(paths["input_dir"]).exists()


def test_crop_multiband_image_writes_center_crop(tmp_path: Path) -> None:
    source_path = tmp_path / "source.tif"
    output_path = tmp_path / "crop.tif"
    data = np.stack(
        [
            np.arange(64 * 64, dtype=np.float32).reshape(64, 64)
            for _ in range(6)
        ],
        axis=0,
    )
    with rasterio.open(
        source_path,
        "w",
        driver="GTiff",
        height=64,
        width=64,
        count=6,
        dtype="float32",
        transform=from_origin(100, 100, 1, 1),
    ) as dst:
        dst.write(data)

    crop_multiband_image(
        source_image_path=str(source_path),
        output_image_path=str(output_path),
        crop_size=16,
    )

    with rasterio.open(output_path) as cropped:
        assert cropped.width == 16
        assert cropped.height == 16
        assert cropped.count == 6
