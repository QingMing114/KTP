"""API tests for the confidence service."""

from __future__ import annotations

import asyncio
from concurrent.futures import TimeoutError as FutureTimeoutError
import threading

import httpx
import pytest
from fastapi.testclient import TestClient

from services.confidence_service.main import create_app


@pytest.fixture
def anyio_backend() -> str:
    return "asyncio"


def _supports_testclient_runtime() -> bool:
    loop = asyncio.new_event_loop()
    ready = threading.Event()

    def run_loop() -> None:
        asyncio.set_event_loop(loop)
        ready.set()
        loop.run_forever()

    thread = threading.Thread(target=run_loop, daemon=True)
    thread.start()
    ready.wait(timeout=1)
    try:
        future = asyncio.run_coroutine_threadsafe(asyncio.sleep(0, result=True), loop)
        return bool(future.result(timeout=0.5))
    except FutureTimeoutError:
        return False
    finally:
        loop.call_soon_threadsafe(loop.stop)
        thread.join(timeout=1)


@pytest.mark.anyio
async def test_confidence_api_returns_structured_result() -> None:
    app = create_app()

    if _supports_testclient_runtime():
        with TestClient(app) as client:
            _assert_confidence_api_contract(client)
    else:
        transport = httpx.ASGITransport(app=app)
        async with httpx.AsyncClient(
            transport=transport,
            base_url="http://testserver",
        ) as client:
            await _assert_confidence_api_contract_async(client)


def _assert_confidence_api_contract(client: TestClient) -> None:
    health_response = client.get("/health")
    assert health_response.status_code == 200
    assert health_response.json()["service"] == "confidence-service"

    response = client.post(
        "/confidence/evaluate",
        json={
            "request_id": "req-confidence-api-001",
            "image_input": {
                "model_confidence": 0.91,
                "affected_area": 1280.5,
                "polygon_count": 2,
            },
            "text_input": {
                "retrieved_source_count": 3,
                "average_retrieval_score": 0.74,
                "has_rag_summary": True,
            },
            "workflow_input": {
                "model_exists": True,
                "training_triggered": False,
                "error_count": 0,
                "status": "completed",
            },
        },
    )
    assert response.status_code == 200
    payload = response.json()
    assert payload["success"] is True
    assert payload["result"]["final_label"] in {"high", "medium", "low"}


async def _assert_confidence_api_contract_async(client: httpx.AsyncClient) -> None:
    health_response = await client.get("/health")
    assert health_response.status_code == 200
    assert health_response.json()["service"] == "confidence-service"

    response = await client.post(
        "/confidence/evaluate",
        json={
            "request_id": "req-confidence-api-001",
            "image_input": {
                "model_confidence": 0.91,
                "affected_area": 1280.5,
                "polygon_count": 2,
            },
            "text_input": {
                "retrieved_source_count": 3,
                "average_retrieval_score": 0.74,
                "has_rag_summary": True,
            },
            "workflow_input": {
                "model_exists": True,
                "training_triggered": False,
                "error_count": 0,
                "status": "completed",
            },
        },
    )
    assert response.status_code == 200
    payload = response.json()
    assert payload["success"] is True
    assert payload["result"]["final_label"] in {"high", "medium", "low"}
