from __future__ import annotations

import argparse

import pytest
pytest.importorskip("scripts.check_dataset_async_flow", reason="scripts.check_dataset_async_flow not yet implemented")

from scripts.check_dataset_async_flow import (
    _artifact_open_url,
    _build_context_payload,
    _build_dataset_register_payload,
)


def test_build_context_payload_includes_dataset_and_task_context() -> None:
    args = argparse.Namespace(
        entrypoint="api",
        conversation_mode="task",
        region="scalp",
        crop_type="hair",
        task_type="baldness_detection",
    )

    payload = _build_context_payload(args, dataset_id="ds_demo_001")

    assert payload == {
        "entrypoint": "api",
        "conversation_mode": "task",
        "dataset_id": "ds_demo_001",
        "region": "scalp",
        "crop_type": "hair",
        "task_type": "baldness_detection",
    }


def test_build_context_payload_can_rely_on_dataset_defaults() -> None:
    args = argparse.Namespace(
        entrypoint="api",
        conversation_mode="task",
        region="scalp",
        crop_type="hair",
        task_type="baldness_detection",
    )

    payload = _build_context_payload(
        args,
        dataset_id="ds_demo_001",
        include_task_defaults=False,
    )

    assert payload == {
        "entrypoint": "api",
        "conversation_mode": "task",
        "dataset_id": "ds_demo_001",
    }


def test_build_dataset_register_payload_includes_default_context() -> None:
    args = argparse.Namespace(
        source_uri="/tmp/demo.tif",
        display_name="demo.tif",
        region="scalp",
        crop_type="hair",
        task_type="baldness_detection",
    )

    payload = _build_dataset_register_payload(args)

    assert payload == {
        "source_type": "local_path",
        "source_uri": "/tmp/demo.tif",
        "display_name": "demo.tif",
        "region": "scalp",
        "crop_type": "hair",
        "task_type": "baldness_detection",
    }


def test_artifact_open_url_rewrites_local_paths() -> None:
    assert (
        _artifact_open_url("http://127.0.0.1:18080/v2", "/tmp/report.html")
        == "http://127.0.0.1:18080/v2/artifacts/open?path=%2Ftmp%2Freport.html"
    )
    assert _artifact_open_url("http://127.0.0.1:18080/v2", "http://example.test/demo") == "http://example.test/demo"
