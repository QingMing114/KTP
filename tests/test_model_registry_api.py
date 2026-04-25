"""API tests for the model registry service."""

from __future__ import annotations

import asyncio
from concurrent.futures import TimeoutError as FutureTimeoutError
from pathlib import Path
import threading

import httpx
import pytest
from fastapi.testclient import TestClient

from services.model_registry.db import init_db
from services.model_registry.main import create_app


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


@pytest.fixture
def registry_app(tmp_path: Path):
    database_url = f"sqlite:///{tmp_path / 'model_registry_api.db'}"
    app = create_app(database_url=database_url)
    init_db()
    return app


@pytest.mark.anyio
async def test_model_registry_api_endpoints(registry_app) -> None:
    if _supports_testclient_runtime():
        with TestClient(registry_app) as client:
            _assert_model_registry_api_contract(client)
    else:
        transport = httpx.ASGITransport(app=registry_app)
        async with httpx.AsyncClient(
            transport=transport,
            base_url="http://testserver",
        ) as client:
            await _assert_model_registry_api_contract_async(client)


def _assert_model_registry_api_contract(client: TestClient) -> None:
    health_response = client.get("/health")
    assert health_response.status_code == 200
    assert health_response.json()["service"] == "model-registry"

    create_response = client.post(
        "/models",
        json={
            "region": "henan",
            "crop_type": "wheat",
            "task_type": "baldness_detection",
            "model_name": "unet_rs_baldness",
            "model_version": "v3",
            "artifact_uri": "s3://models/henan/wheat/v3/model.pt",
            "metrics_json": {"miou": 0.88, "f1": 0.9},
            "status": "ready",
        },
    )
    assert create_response.status_code == 201
    created_model = create_response.json()
    model_id = created_model["id"]

    lookup_ready = client.get(
        "/models/lookup",
        params={
            "region": "henan",
            "crop_type": "wheat",
            "task_type": "baldness_detection",
        },
    )
    assert lookup_ready.status_code == 200
    assert lookup_ready.json()["model_exists"] is True
    assert lookup_ready.json()["model_version"] == "v3"

    patch_response = client.patch(
        f"/models/{model_id}/status",
        json={"status": "deprecated"},
    )
    assert patch_response.status_code == 200
    assert patch_response.json()["status"] == "deprecated"

    lookup_missing = client.get(
        "/models/lookup",
        params={
            "region": "henan",
            "crop_type": "wheat",
            "task_type": "baldness_detection",
        },
    )
    assert lookup_missing.status_code == 200
    assert lookup_missing.json()["model_exists"] is False
    assert "no ready model found" in lookup_missing.json()["reason"]


async def _assert_model_registry_api_contract_async(client: httpx.AsyncClient) -> None:
    health_response = await client.get("/health")
    assert health_response.status_code == 200
    assert health_response.json()["service"] == "model-registry"

    create_response = await client.post(
        "/models",
        json={
            "region": "henan",
            "crop_type": "wheat",
            "task_type": "baldness_detection",
            "model_name": "unet_rs_baldness",
            "model_version": "v3",
            "artifact_uri": "s3://models/henan/wheat/v3/model.pt",
            "metrics_json": {"miou": 0.88, "f1": 0.9},
            "status": "ready",
        },
    )
    assert create_response.status_code == 201
    created_model = create_response.json()
    model_id = created_model["id"]

    lookup_ready = await client.get(
        "/models/lookup",
        params={
            "region": "henan",
            "crop_type": "wheat",
            "task_type": "baldness_detection",
        },
    )
    assert lookup_ready.status_code == 200
    assert lookup_ready.json()["model_exists"] is True
    assert lookup_ready.json()["model_version"] == "v3"

    patch_response = await client.patch(
        f"/models/{model_id}/status",
        json={"status": "deprecated"},
    )
    assert patch_response.status_code == 200
    assert patch_response.json()["status"] == "deprecated"

    lookup_missing = await client.get(
        "/models/lookup",
        params={
            "region": "henan",
            "crop_type": "wheat",
            "task_type": "baldness_detection",
        },
    )
    assert lookup_missing.status_code == 200
    assert lookup_missing.json()["model_exists"] is False
    assert "no ready model found" in lookup_missing.json()["reason"]
