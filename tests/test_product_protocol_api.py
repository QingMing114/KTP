from __future__ import annotations

import asyncio
import json
from pathlib import Path

import httpx
import pytest
from fastapi import FastAPI

pytest.importorskip("ktp_backend.product_protocol", reason="ktp_backend.product_protocol not yet implemented")

from ktp_backend.api import install_backend_api
from ktp_backend.product_protocol.conversations import ConversationMetadataRegistry
from ktp_backend.product_protocol.idempotency import IdempotencyStore
from ktp_backend.runtime_host import build_backend_runtime_host
from shared.config.settings import get_settings
from v2.adapters.python_services.ktp_rag import KtpKnowledgeAdapter
from v2.apps.api.config import V2ApiSettings
from v2.shared.schemas import AsyncRunStatusV2
from v2.tests.test_api_smoke import (
    _FakeKtpServiceBundle,
    _FakeRagClient,
    _SequenceStructuredLLMProvider,
)
from v2.tools.registry import build_default_tool_registry


def _run_request(
    app,
    method: str,
    path: str,
    payload: dict | None = None,
    headers: dict[str, str] | None = None,
) -> httpx.Response:
    async def _call() -> httpx.Response:
        transport = httpx.ASGITransport(app=app)
        async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
            return await client.request(method, path, json=payload, headers=headers)

    return asyncio.run(_call())


def _build_product_app(
    *,
    tmp_path: Path,
    llm_provider=None,
):
    settings = V2ApiSettings(
        store_backend="memory",
        dataset_registry_path=str(tmp_path / "datasets.json"),
    )
    tool_registry = build_default_tool_registry(
        ktp_knowledge_adapter=KtpKnowledgeAdapter(client=_FakeRagClient()),
        ktp_service_bundle=_FakeKtpServiceBundle(),
    )
    host = build_backend_runtime_host(
        settings_override=settings,
        tool_registry_override=tool_registry,
        llm_provider_override=llm_provider,
    )
    app = FastAPI()
    install_backend_api(app, settings_override=settings, runtime_host_override=host, include_root_health=False)
    app.state.product_conversation_registry = ConversationMetadataRegistry(
        registry_path=str(tmp_path / "product-conversations.json")
    )
    app.state.product_idempotency_store = IdempotencyStore()
    return app


def _auth_headers() -> dict[str, str]:
    return {"Authorization": "Bearer sk-ktp-local"}


def _poll_submission(app, submission_id: str) -> dict:
    for _ in range(80):
        response = _run_request(app, "GET", f"/api/product/v1/submissions/{submission_id}", headers=_auth_headers())
        payload = response.json()
        if payload["status"] in {"completed", "failed", "cancelled"}:
            return payload
        import time

        time.sleep(0.05)
    raise AssertionError(f"Submission {submission_id} did not reach a terminal state in time.")


def _parse_sse_events(body: str) -> list[dict]:
    parsed: list[dict] = []
    for block in body.split("\n\n"):
        block = block.strip()
        if not block:
            continue
        event_id = None
        event_name = None
        data = None
        for line in block.splitlines():
            if line.startswith("id:"):
                event_id = line[3:].strip()
            elif line.startswith("event:"):
                event_name = line[6:].strip()
            elif line.startswith("data:"):
                data = json.loads(line[5:].strip())
        parsed.append({"id": event_id, "event": event_name, "data": data})
    return parsed


def test_product_protocol_manifest_requires_bearer_when_configured(tmp_path: Path) -> None:
    app = _build_product_app(tmp_path=tmp_path)
    settings = get_settings()
    original = settings.ktp_product_api_key
    settings.ktp_product_api_key = "sk-ktp-local"
    try:
        unauthorized = _run_request(app, "GET", "/api/product/v1/manifest")
        assert unauthorized.status_code == 401
        payload = unauthorized.json()
        assert payload["error"]["code"] == "UNAUTHORIZED"

        authorized = _run_request(app, "GET", "/api/product/v1/manifest", headers=_auth_headers())
        assert authorized.status_code == 200
        manifest = authorized.json()
        assert manifest["protocol_version"] == "1.1"
        assert manifest["delivery_modes"] == ["async"]
        assert "include_visualization" in manifest["supported_preferences"]
        assert "openai_chat_v1" in manifest["compat_adapters"]
    finally:
        settings.ktp_product_api_key = original


def test_product_protocol_dataset_crud_and_cursor_pagination(tmp_path: Path) -> None:
    app = _build_product_app(tmp_path=tmp_path)
    file_a = tmp_path / "a.tif"
    file_b = tmp_path / "b.tif"
    file_a.write_bytes(b"a")
    file_b.write_bytes(b"b")

    first = _run_request(
        app,
        "POST",
        "/api/product/v1/datasets",
        {
            "source": {"kind": "local_path", "uri": str(file_a)},
            "display_name": "a.tif",
            "defaults": {"region": "scalp", "crop_type": "hair", "task_type": "baldness_detection"},
        },
        headers=_auth_headers(),
    )
    second = _run_request(
        app,
        "POST",
        "/api/product/v1/datasets",
        {
            "source": {"kind": "local_path", "uri": str(file_b)},
            "display_name": "b.tif",
            "defaults": {"region": "henan", "crop_type": "wheat", "task_type": "crop_health_detection"},
        },
        headers=_auth_headers(),
    )

    first_dataset = first.json()
    second_dataset = second.json()
    assert first_dataset["defaults"]["crop_type"] == "hair"

    patched = _run_request(
        app,
        "PATCH",
        f"/api/product/v1/datasets/{first_dataset['dataset_id']}",
        {"display_name": "a-renamed.tif", "defaults": {"region": "scalp", "crop_type": "hair", "task_type": "baldness_detection"}, "tags": ["demo"]},
        headers=_auth_headers(),
    )
    assert patched.status_code == 200
    assert patched.json()["display_name"] == "a-renamed.tif"
    assert patched.json()["tags"] == ["demo"]

    page_one = _run_request(
        app,
        "GET",
        "/api/product/v1/datasets?limit=1",
        headers=_auth_headers(),
    )
    assert page_one.status_code == 200
    page_one_payload = page_one.json()
    assert page_one_payload["has_more"] is True
    assert page_one_payload["next_cursor"] is not None

    page_two = _run_request(
        app,
        "GET",
        f"/api/product/v1/datasets?cursor={page_one_payload['next_cursor']}&limit=1",
        headers=_auth_headers(),
    )
    assert page_two.status_code == 200
    assert len(page_two.json()["items"]) == 1

    deleted = _run_request(
        app,
        "DELETE",
        f"/api/product/v1/datasets/{second_dataset['dataset_id']}",
        headers=_auth_headers(),
    )
    assert deleted.status_code == 204
    assert file_b.exists()


def test_product_protocol_conversation_create_is_idempotent_and_delete_is_soft_archive(tmp_path: Path) -> None:
    app = _build_product_app(tmp_path=tmp_path)
    headers = {**_auth_headers(), "Idempotency-Key": "conv-001"}

    first = _run_request(
        app,
        "POST",
        "/api/product/v1/conversations",
        {"title": "Demo"},
        headers=headers,
    )
    second = _run_request(
        app,
        "POST",
        "/api/product/v1/conversations",
        {"title": "Demo"},
        headers=headers,
    )
    assert first.status_code == 200
    assert second.status_code == 200
    first_id = first.json()["conversation_id"]
    assert second.json()["conversation_id"] == first_id

    conflict = _run_request(
        app,
        "POST",
        "/api/product/v1/conversations",
        {"title": "Different"},
        headers=headers,
    )
    assert conflict.status_code == 409
    assert conflict.json()["error"]["code"] == "IDEMPOTENCY_CONFLICT"

    archived = _run_request(
        app,
        "DELETE",
        f"/api/product/v1/conversations/{first_id}",
        headers=_auth_headers(),
    )
    assert archived.status_code == 204

    fetched = _run_request(
        app,
        "GET",
        f"/api/product/v1/conversations/{first_id}",
        headers=_auth_headers(),
    )
    assert fetched.status_code == 200
    assert fetched.json()["archived"] is True


def test_product_protocol_submission_inherits_dataset_defaults_and_emits_artifacts(tmp_path: Path) -> None:
    llm_provider = _SequenceStructuredLLMProvider(
        {
            "action": "delegate_agent",
            "reasoning": "Use the analysis specialist for the dataset-backed task.",
            "delegation_target": "ktp_analysis_specialist",
            "delegation_goal": "Run the KTP analysis flow.",
        },
        {
            "action": "call_tools",
            "reasoning": "Use the macro KTP analysis tool.",
            "tool_calls": [{"tool_name": "ktp.analysis_pipeline", "tool_input": {}}],
        },
        {
            "action": "finish",
            "reasoning": "Summarize the completed analysis.",
            "response_message": "斑秃识别分析已经完成。",
        },
    )
    app = _build_product_app(tmp_path=tmp_path, llm_provider=llm_provider)
    image_path = tmp_path / "demo_hair.tif"
    image_path.write_bytes(b"demo")

    dataset = _run_request(
        app,
        "POST",
        "/api/product/v1/datasets",
        {
            "source": {"kind": "local_path", "uri": str(image_path)},
            "display_name": "demo_hair.tif",
            "defaults": {"region": "scalp", "crop_type": "hair", "task_type": "baldness_detection"},
        },
        headers=_auth_headers(),
    ).json()
    conversation = _run_request(
        app,
        "POST",
        "/api/product/v1/conversations",
        {"title": "Analysis"},
        headers=_auth_headers(),
    ).json()

    accepted = _run_request(
        app,
        "POST",
        f"/api/product/v1/conversations/{conversation['conversation_id']}/submissions",
        {
            "input": {
                "message": f"请对 dataset:{dataset['dataset_id']} 做真实斑秃识别，并生成分析报告、置信度说明和可视化。",
                "refs": [{"type": "dataset", "id": dataset["dataset_id"]}],
            },
            "mode": {"interaction": "task", "delivery": "async"},
            "preferences": {"include_visualization": True, "include_knowledge": True},
        },
        headers=_auth_headers(),
    )
    assert accepted.status_code == 200
    terminal = _poll_submission(app, accepted.json()["submission_id"])
    assert terminal["status"] == "completed"
    assert terminal["stage"] == "completed"

    run = _run_request(
        app,
        "GET",
        f"/api/product/v1/runs/{terminal['run_id']}",
        headers=_auth_headers(),
    )
    assert run.status_code == 200
    payload = run.json()
    assert payload["request"]["context"]["dataset_id"] == dataset["dataset_id"]
    assert payload["request"]["context"]["crop_type"] == "hair"
    assert payload["assistant"]["summary"] == "斑秃识别分析已经完成。"
    assert any(item["type"] == "artifact_ref" for item in payload["assistant"]["parts"])
    assert any(item["kind"] == "report_card" for item in payload["artifacts"])
    assert all("/api/product/v1/artifacts/" in item["view_url"] for item in payload["artifacts"])


def test_product_protocol_submission_context_inheritance_latest_and_none(tmp_path: Path) -> None:
    llm_provider = _SequenceStructuredLLMProvider(
        {
            "action": "delegate_agent",
            "reasoning": "First run should analyze the dataset.",
            "delegation_target": "ktp_analysis_specialist",
            "delegation_goal": "Analyze the dataset first.",
        },
        {
            "action": "call_tools",
            "reasoning": "Run the KTP analysis pipeline.",
            "tool_calls": [{"tool_name": "ktp.analysis_pipeline", "tool_input": {}}],
        },
        {
            "action": "finish",
            "reasoning": "First task is complete.",
            "response_message": "第一次分析完成。",
        },
        {
            "action": "reply",
            "reasoning": "Use inherited context for the follow-up.",
            "response_message": "我沿用了上一轮的上下文。",
        },
        {
            "action": "reply",
            "reasoning": "No context should be inherited here.",
            "response_message": "这轮没有继承上一轮的上下文。",
        },
    )
    app = _build_product_app(tmp_path=tmp_path, llm_provider=llm_provider)
    image_path = tmp_path / "inherit_demo.tif"
    image_path.write_bytes(b"demo")

    dataset = _run_request(
        app,
        "POST",
        "/api/product/v1/datasets",
        {
            "source": {"kind": "local_path", "uri": str(image_path)},
            "display_name": "inherit_demo.tif",
            "defaults": {"region": "scalp", "crop_type": "hair", "task_type": "baldness_detection"},
        },
        headers=_auth_headers(),
    ).json()
    conversation = _run_request(
        app,
        "POST",
        "/api/product/v1/conversations",
        {"title": "Inheritance"},
        headers=_auth_headers(),
    ).json()

    first = _run_request(
        app,
        "POST",
        f"/api/product/v1/conversations/{conversation['conversation_id']}/submissions",
        {
            "input": {
                "message": f"请对 dataset:{dataset['dataset_id']} 做分析。",
                "refs": [{"type": "dataset", "id": dataset["dataset_id"]}],
            },
            "mode": {"interaction": "task", "delivery": "async"},
        },
        headers=_auth_headers(),
    ).json()
    first_terminal = _poll_submission(app, first["submission_id"])
    assert first_terminal["status"] == "completed"

    second = _run_request(
        app,
        "POST",
        f"/api/product/v1/conversations/{conversation['conversation_id']}/submissions",
        {
            "input": {"message": "请继续补一版结论摘要。", "refs": []},
            "mode": {"interaction": "chat", "delivery": "async"},
        },
        headers=_auth_headers(),
    ).json()
    second_terminal = _poll_submission(app, second["submission_id"])
    second_run = _run_request(
        app,
        "GET",
        f"/api/product/v1/runs/{second_terminal['run_id']}",
        headers=_auth_headers(),
    ).json()
    assert second_run["request"]["context"]["dataset_id"] == dataset["dataset_id"]

    third = _run_request(
        app,
        "POST",
        f"/api/product/v1/conversations/{conversation['conversation_id']}/submissions",
        {
            "input": {"message": "这轮不要继承。", "refs": []},
            "context": {"inherit": "none"},
            "mode": {"interaction": "chat", "delivery": "async"},
        },
        headers=_auth_headers(),
    ).json()
    third_terminal = _poll_submission(app, third["submission_id"])
    third_run = _run_request(
        app,
        "GET",
        f"/api/product/v1/runs/{third_terminal['run_id']}",
        headers=_auth_headers(),
    ).json()
    assert third_run["request"]["context"]["dataset_id"] is None


def test_product_protocol_submission_events_support_sse_and_last_event_id_snapshot(tmp_path: Path) -> None:
    llm_provider = _SequenceStructuredLLMProvider(
        {
            "action": "reply",
            "reasoning": "Simple async chat reply.",
            "response_message": "这是一个简单的异步回答。",
        }
    )
    app = _build_product_app(tmp_path=tmp_path, llm_provider=llm_provider)
    conversation = _run_request(
        app,
        "POST",
        "/api/product/v1/conversations",
        {"title": "Events"},
        headers=_auth_headers(),
    ).json()
    accepted = _run_request(
        app,
        "POST",
        f"/api/product/v1/conversations/{conversation['conversation_id']}/submissions",
        {
            "input": {"message": "你好", "refs": []},
            "mode": {"interaction": "chat", "delivery": "async"},
        },
        headers=_auth_headers(),
    ).json()
    terminal = _poll_submission(app, accepted["submission_id"])
    assert terminal["status"] == "completed"

    events_response = _run_request(
        app,
        "GET",
        f"/api/product/v1/submissions/{accepted['submission_id']}/events",
        headers=_auth_headers(),
    )
    assert events_response.status_code == 200
    assert events_response.headers["content-type"].startswith("text/event-stream")
    events = _parse_sse_events(events_response.text)
    assert events
    assert all(item["id"] for item in events)
    assert any(item["event"] == "run.completed" for item in events)

    reconnect = _run_request(
        app,
        "GET",
        f"/api/product/v1/submissions/{accepted['submission_id']}/events",
        headers={**_auth_headers(), "Last-Event-ID": "evt_missing"},
    )
    reconnect_events = _parse_sse_events(reconnect.text)
    assert reconnect_events
    assert reconnect_events[0]["event"] == "submission.updated"


class _StubAsyncRunManager:
    def __init__(self) -> None:
        self.cancel_calls = 0
        self._status = AsyncRunStatusV2(
            submission_id="job_stub_001",
            session_id="sess_stub_001",
            status="queued",
            stage="accepted",
            message="demo",
            submitted_at="2026-04-04T00:00:00+00:00",
        )

    def get_submission(self, submission_id: str):
        if submission_id != self._status.submission_id:
            return None
        return self._status.model_copy(deep=True)

    def cancel_submission(self, submission_id: str):
        if submission_id != self._status.submission_id:
            return None
        self.cancel_calls += 1
        self._status = self._status.model_copy(
            update={
                "status": "cancelled",
                "cancel_requested": True,
                "stage": "failed",
                "completed_at": "2026-04-04T00:00:01+00:00",
                "latest_event": "submission.cancelled",
                "latest_detail": "Cancelled from test stub.",
            }
        )
        return self._status.model_copy(deep=True)

    def get_events(self, submission_id: str, *, after_event_id: str | None = None):
        del submission_id, after_event_id
        return [], True


def test_product_protocol_cancel_supports_idempotency_and_terminal_error(tmp_path: Path) -> None:
    app = _build_product_app(tmp_path=tmp_path)
    stub = _StubAsyncRunManager()
    app.state.async_run_manager = stub

    first = _run_request(
        app,
        "POST",
        "/api/product/v1/submissions/job_stub_001/cancel",
        headers={**_auth_headers(), "Idempotency-Key": "cancel-001"},
    )
    second = _run_request(
        app,
        "POST",
        "/api/product/v1/submissions/job_stub_001/cancel",
        headers={**_auth_headers(), "Idempotency-Key": "cancel-001"},
    )
    assert first.status_code == 200
    assert second.status_code == 200
    assert stub.cancel_calls == 1
    assert first.json()["status"] == "cancelled"

    terminal = _run_request(
        app,
        "POST",
        "/api/product/v1/submissions/job_stub_001/cancel",
        headers=_auth_headers(),
    )
    assert terminal.status_code == 409
    assert terminal.json()["error"]["code"] == "ALREADY_TERMINAL"
