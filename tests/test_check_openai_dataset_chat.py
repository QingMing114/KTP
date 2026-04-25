from __future__ import annotations

import argparse

import pytest
pytest.importorskip("scripts.check_openai_dataset_chat", reason="scripts.check_openai_dataset_chat not yet implemented")

from scripts.check_openai_dataset_chat import (
    _build_chat_payload,
    _build_dataset_register_payload,
    _derive_v2_base_url,
)


def test_derive_v2_base_url_from_openai_root() -> None:
    assert _derive_v2_base_url("http://127.0.0.1:18080/v1") == "http://127.0.0.1:18080/v2"
    assert _derive_v2_base_url("http://127.0.0.1:18080/v1/") == "http://127.0.0.1:18080/v2"


def test_build_dataset_register_payload_includes_default_context() -> None:
    args = argparse.Namespace(
        source_uri="/tmp/demo.tif",
        display_name="demo.tif",
        region="scalp",
        crop_type="hair",
        task_type="baldness_detection",
    )

    assert _build_dataset_register_payload(args) == {
        "source_type": "local_path",
        "source_uri": "/tmp/demo.tif",
        "display_name": "demo.tif",
        "region": "scalp",
        "crop_type": "hair",
        "task_type": "baldness_detection",
    }


def test_build_chat_payload_supports_file_id_dataset_reference() -> None:
    args = argparse.Namespace(
        client_name="open-webui",
        conversation_mode="task",
        forward_context=False,
        region="scalp",
        crop_type="hair",
        task_type="baldness_detection",
        ref_mode="file_id",
        model="ktp-multi-agent",
        user="dataset-smoke",
        message="请分析这个已注册数据集。",
    )

    payload = _build_chat_payload(args, dataset_id="ds_demo_001")

    assert payload["metadata"] == {
        "client": "open-webui",
        "conversation_mode": "task",
    }
    assert payload["messages"] == [
        {
            "role": "user",
            "content": [
                {"type": "text", "text": "请分析这个已注册数据集。"},
                {"type": "input_file", "file_id": "ds_demo_001"},
            ],
        }
    ]


def test_build_chat_payload_supports_metadata_dataset_reference_with_context_forwarding() -> None:
    args = argparse.Namespace(
        client_name="librechat",
        conversation_mode="task",
        forward_context=True,
        region="henan",
        crop_type="wheat",
        task_type="crop_health_detection",
        ref_mode="metadata",
        model="ktp-multi-agent",
        user="dataset-smoke",
        message="请分析这个已注册数据集。",
    )

    payload = _build_chat_payload(args, dataset_id="ds_demo_001")

    assert payload["metadata"] == {
        "client": "librechat",
        "conversation_mode": "task",
        "dataset_id": "ds_demo_001",
        "region": "henan",
        "crop_type": "wheat",
        "task_type": "crop_health_detection",
    }
    assert payload["messages"] == [{"role": "user", "content": "请分析这个已注册数据集。"}]
