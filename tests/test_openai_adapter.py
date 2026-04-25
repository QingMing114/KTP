from __future__ import annotations

import asyncio
import json

import pytest
from fastapi import HTTPException

from apps.api_gateway.routers.openai_adapter import (
    OpenAIChatRequest,
    chat_completions,
    list_models,
)

try:
    from apps.api_gateway.routers.openai_adapter import _stream_openai_chunks
except ImportError:
    _stream_openai_chunks = None

try:
    from apps.api_gateway.routers.openai_adapter import require_openai_api_key
except ImportError:
    require_openai_api_key = None
from v2.shared.schemas import AttachmentV2, RunDetail, RunEventV2


class _StubOpenAIChatService:
    def handle_openai_chat(
        self,
        *,
        model: str,
        messages,
        attachments,
        user_id: str | None,
        conversation_id: str | None,
        client_capabilities,
        public_base_url: str,
    ):
        assert model == "ktp-multi-agent"
        assert user_id == "demo-user"
        assert conversation_id == "conv-001"
        assert messages[0].role == "system"
        assert messages[0].content == "Be helpful."
        assert messages[-1].role == "user"
        assert messages[-1].content == "请分析这张影像"
        assert attachments == [
            AttachmentV2(
                path="/home/D/liumeng/data/demo-field.tif",
                name="demo-field.tif",
            )
        ]
        assert client_capabilities["client"] == "librechat"
        assert public_base_url == "http://testserver"

        class _Response:
            answer = "知道。Claude 是 Anthropic 的通用对话与 agent 系列模型。"
            artifacts = [
                type(
                    "Artifact",
                    (),
                    {
                        "title": "Open report",
                        "uri": "/home/D/liumeng/ktp_product/var/reports/report-001.html",
                    },
                )()
            ]

        return _Response()


class _StubStreamingOpenAIChatService(_StubOpenAIChatService):
    def stream_openai_chat(
        self,
        *,
        model: str,
        messages,
        attachments,
        user_id: str | None,
        conversation_id: str | None,
        client_capabilities,
    ):
        self.handle_openai_chat(
            model=model,
            messages=messages,
            attachments=attachments,
            user_id=user_id,
            conversation_id=conversation_id,
            client_capabilities=client_capabilities,
            public_base_url="http://testserver",
        )
        run = RunDetail(
            run_id="run-openai-stream-001",
            session_id="conv-001",
            status="completed",
            input_message=messages[-1].content,
            output_message="Claude 是 Anthropic 的模型。",
        )
        yield RunEventV2(
            sequence=1,
            event="assistant.delta",
            run_id=run.run_id,
            session_id=run.session_id,
            detail="partial",
            output_message="Claude 是 Anthropic 的模型。",
        )
        yield RunEventV2(
            sequence=2,
            event="artifact.available",
            run_id=run.run_id,
            session_id=run.session_id,
            detail="artifact",
            artifact={
                "pack_name": "ktp",
                "artifact_type": "report_card",
                "title": "Open report",
                "content": None,
                "uri": "/home/D/liumeng/ktp_product/var/reports/report-001.html",
            },
        )
        yield RunEventV2(
            sequence=3,
            event="run.completed",
            run_id=run.run_id,
            session_id=run.session_id,
            detail="done",
            run_status="completed",
            run=run,
        )


class _StubDatasetOpenAIChatService:
    def handle_openai_chat(
        self,
        *,
        model: str,
        messages,
        attachments,
        user_id: str | None,
        conversation_id: str | None,
        client_capabilities,
        public_base_url: str,
    ):
        assert model == "ktp-multi-agent"
        assert user_id == "demo-user"
        assert conversation_id == "conv-dataset"
        assert messages[-1].role == "user"
        assert "已注册数据集" in messages[-1].content
        assert attachments == []
        assert client_capabilities["client"] == "librechat"
        assert client_capabilities["dataset_id"] == "ds_demo_001"
        assert client_capabilities["conversation_mode"] == "task"
        assert client_capabilities["region"] == "scalp"
        assert client_capabilities["crop_type"] == "hair"
        assert client_capabilities["task_type"] == "baldness_detection"
        assert client_capabilities["extra_params"] == {"prefer_visualization": True}
        assert public_base_url == "http://testserver"

        class _Response:
            answer = "已接收 dataset-backed 斑秃识别请求。"
            artifacts = []

        return _Response()


class _StubRequest:
    base_url = "http://testserver/"


def test_openai_chat_completion_routes_into_gateway_bridge() -> None:
    async def _run() -> None:
        response = await chat_completions(
            OpenAIChatRequest.model_validate(
                {
                    "model": "ktp-multi-agent",
                    "user": "demo-user",
                    "conversation_id": "conv-001",
                    "metadata": {"client": "librechat"},
                    "messages": [
                        {"role": "system", "content": "Be helpful."},
                        {
                            "role": "user",
                            "content": [
                                {"type": "text", "text": "请分析这张影像"},
                                {
                                    "type": "input_file",
                                    "file_url": "file:///home/D/liumeng/data/demo-field.tif",
                                },
                            ],
                        },
                    ],
                }
            ),
            _StubRequest(),
            None,
            _StubOpenAIChatService(),
        )
        payload = response.model_dump(mode="json")
        content = payload["choices"][0]["message"]["content"]
        assert content.startswith("知道。Claude")
        assert "/v2/artifacts/open?path=%2Fhome%2FD%2Fliumeng%2Fktp_product%2Fvar%2Freports%2Freport-001.html" in content

    asyncio.run(_run())


def test_openai_models_requires_valid_api_key() -> None:
    if require_openai_api_key is None:
        pytest.skip("require_openai_api_key not available in current version")
    try:
        require_openai_api_key(authorization=None, x_api_key=None)
    except HTTPException as exc:
        assert exc.status_code == 401
        assert exc.detail == "invalid_api_key"
    else:  # pragma: no cover
        raise AssertionError("expected invalid_api_key")


def test_openai_models_returns_single_public_model() -> None:
    require_openai_api_key(authorization="Bearer sk-ktp-local", x_api_key=None)

    async def _run() -> None:
        response = await list_models(None)
        payload = response.model_dump(mode="json")
        assert payload["data"][0]["id"] == "ktp-multi-agent"

    asyncio.run(_run())


def test_openai_chat_completion_streams_sse_chunks() -> None:
    body = "".join(
        _stream_openai_chunks(
            events=_StubStreamingOpenAIChatService().stream_openai_chat(
                model="ktp-multi-agent",
                messages=[
                    type("Msg", (), {"role": "system", "content": "Be helpful."})(),
                    type("Msg", (), {"role": "user", "content": "请分析这张影像"})(),
                ],
                attachments=[AttachmentV2(path="/home/D/liumeng/data/demo-field.tif", name="demo-field.tif")],
                user_id="demo-user",
                conversation_id="conv-001",
                client_capabilities={"client": "librechat"},
            ),
            model="ktp-multi-agent",
            public_base_url="http://testserver",
        )
    )
    assert "data: [DONE]" in body
    json_payloads = []
    for line in body.splitlines():
        if not line.startswith("data: ") or line == "data: [DONE]":
            continue
        json_payloads.append(json.loads(line.removeprefix("data: ")))
    assert any(item["choices"][0]["delta"].get("role") == "assistant" for item in json_payloads)
    assert any(item["choices"][0]["delta"].get("content") == "Claude 是 Anthropic 的模型。" for item in json_payloads)
    assert any("Open report" in item["choices"][0]["delta"].get("content", "") for item in json_payloads)
    assert json_payloads[-1]["choices"][0]["finish_reason"] == "stop"


def test_openai_chat_completion_supports_dataset_metadata_and_file_id_reference() -> None:
    async def _run() -> None:
        response = await chat_completions(
            OpenAIChatRequest.model_validate(
                {
                    "model": "ktp-multi-agent",
                    "user": "demo-user",
                    "conversation_id": "conv-dataset",
                    "metadata": {
                        "client": "librechat",
                        "conversation_mode": "task",
                        "region": "scalp",
                        "crop_type": "hair",
                        "task_type": "baldness_detection",
                        "extra_params": {"prefer_visualization": True},
                    },
                    "messages": [
                        {
                            "role": "user",
                            "content": [
                                {
                                    "type": "input_file",
                                    "file_id": "ds_demo_001",
                                }
                            ],
                        },
                    ],
                }
            ),
            _StubRequest(),
            None,
            _StubDatasetOpenAIChatService(),
        )
        payload = response.model_dump(mode="json")
        assert payload["choices"][0]["message"]["content"] == "已接收 dataset-backed 斑秃识别请求。"

    asyncio.run(_run())
