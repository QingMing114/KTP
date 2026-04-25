"""Unit tests for shared inference mask sanity inspection."""

from __future__ import annotations

from pathlib import Path

import numpy as np
from PIL import Image

from shared.inference_sanity import inspect_mask_artifact


def test_inspect_mask_artifact_flags_full_positive_mask(tmp_path: Path) -> None:
    mask_path = tmp_path / "full_positive_mask.png"
    Image.fromarray(np.full((8, 8), 255, dtype=np.uint8)).save(mask_path)

    result = inspect_mask_artifact(str(mask_path))

    assert result.available is True
    assert result.total_pixels == 64
    assert result.positive_pixels == 64
    assert result.positive_ratio == 1.0
    assert any("near-total" in warning for warning in result.warnings)
    assert any("single positive value" in warning for warning in result.warnings)


def test_inspect_mask_artifact_handles_missing_file() -> None:
    result = inspect_mask_artifact("/tmp/ktp_missing_mask_for_test.png")

    assert result.available is False
    assert result.total_pixels == 0
    assert result.positive_ratio == 0.0
    assert any("missing" in warning for warning in result.warnings)
