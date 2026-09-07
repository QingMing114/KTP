"""API tests for the report service."""

from __future__ import annotations

import asyncio
from concurrent.futures import TimeoutError as FutureTimeoutError
from pathlib import Path
import threading

import httpx
import pytest
from fastapi.testclient import TestClient

from services.report_service.config import ReportServiceConfig
from services.report_service.main import create_app
from services.report_service.service import ReportService

TEMPLATE_DIR = Path(__file__).resolve().parents[1] / "backend" / "services" / "report_service" / "templates"


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


def _create_test_app(tmp_path: Path):
    config = ReportServiceConfig(
        REPORT_SERVICE_NAME="report-service",
        REPORT_OUTPUT_DIR=str(tmp_path / "reports"),
        REPORT_TEMPLATE_DIR=str(TEMPLATE_DIR),
        EMBED_HTML_IN_RESPONSE=True,
        GENERATE_CHARTS=True,
    )
    return create_app(config=config, service=ReportService(config=config))


@pytest.mark.anyio
async def test_report_api_generates_structured_report(tmp_path: Path) -> None:
    app = _create_test_app(tmp_path)

    if _supports_testclient_runtime():
        with TestClient(app) as client:
            _assert_report_api_contract(client)
    else:
        transport = httpx.ASGITransport(app=app)
        async with httpx.AsyncClient(
            transport=transport,
            base_url="http://testserver",
        ) as client:
            await _assert_report_api_contract_async(client)


def _assert_report_api_contract(client: TestClient) -> None:
    health_response = client.get("/health")
    assert health_response.status_code == 200
    assert health_response.json()["service"] == "report-service"

    response = client.post(
        "/report/generate",
        json={
            "request_id": "req-report-api-001",
            "title": "Henan Wheat Report",
            "user_query": "Assess wheat health in Henan.",
            "region": "henan",
            "crop_type": "wheat",
            "task_type": "crop_health_detection",
            "summary": {
                "overview": "Structured report generated from workflow outputs.",
                "key_findings": ["Inference confidence is high."],
            },
            "inference": {
                "model_name": "wheat-health-segmentation",
                "model_version": "v1",
                "affected_area": 1280.5,
                "confidence": 0.91,
                "mask_uri": "/tmp/mask.png",
                "polygons": [],
            },
            "rag": {
                "summary": "Retrieved agronomic context for Henan wheat.",
                "sources": ["local://knowledge/henan-wheat"],
                "results": [],
            },
            "confidence": None,
            "extra_metadata": {},
        },
    )
    assert response.status_code == 200
    payload = response.json()
    assert payload["success"] is True
    assert Path(payload["result"]["report_path"]).exists()
    assert "<html" in payload["result"]["html"].lower()


async def _assert_report_api_contract_async(client: httpx.AsyncClient) -> None:
    health_response = await client.get("/health")
    assert health_response.status_code == 200
    assert health_response.json()["service"] == "report-service"

    response = await client.post(
        "/report/generate",
        json={
            "request_id": "req-report-api-001",
            "title": "Henan Wheat Report",
            "user_query": "Assess wheat health in Henan.",
            "region": "henan",
            "crop_type": "wheat",
            "task_type": "crop_health_detection",
            "summary": {
                "overview": "Structured report generated from workflow outputs.",
                "key_findings": ["Inference confidence is high."],
            },
            "inference": {
                "model_name": "wheat-health-segmentation",
                "model_version": "v1",
                "affected_area": 1280.5,
                "confidence": 0.91,
                "mask_uri": "/tmp/mask.png",
                "polygons": [],
            },
            "rag": {
                "summary": "Retrieved agronomic context for Henan wheat.",
                "sources": ["local://knowledge/henan-wheat"],
                "results": [],
            },
            "confidence": None,
            "extra_metadata": {},
        },
    )
    assert response.status_code == 200
    payload = response.json()
    assert payload["success"] is True
    assert Path(payload["result"]["report_path"]).exists()
