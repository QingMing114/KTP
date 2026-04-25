"""Unit tests for dynamic GPU selection helpers."""

from __future__ import annotations

import pytest

from infra.llm.gpu_selection import GPUSelectionError, parse_nvidia_smi_csv, resolve_cuda_visible_devices


def test_parse_nvidia_smi_csv_returns_statuses() -> None:
    statuses = parse_nvidia_smi_csv(
        "0, 1000, 81920, 10\n1, 2000, 81920, 40\n"
    )

    assert [item.index for item in statuses] == [0, 1]
    assert statuses[0].memory_free_mb == 80920
    assert statuses[1].utilization_gpu_percent == 40


def test_resolve_cuda_visible_devices_returns_explicit_value() -> None:
    assert resolve_cuda_visible_devices("2,5") == "2,5"


def test_resolve_cuda_visible_devices_rejects_bad_auto_value() -> None:
    with pytest.raises(GPUSelectionError):
        resolve_cuda_visible_devices("auto:abc")
