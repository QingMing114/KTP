"""Smoke tests for the scaffold API gateway."""

from __future__ import annotations

import asyncio
from concurrent.futures import TimeoutError as FutureTimeoutError
import threading

import httpx
import pytest
from fastapi.testclient import TestClient

from apps.api_gateway.main import app
from shared.config.settings import settings


@pytest.fixture
def anyio_backend() -> str:
    return "asyncio"


def _supports_testclient_runtime() -> bool:
    """Detect runtimes where cross-thread asyncio scheduling is unavailable."""
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
async def test_health_returns_expected_payload() -> None:
    if _supports_testclient_runtime():
        with TestClient(app) as client:
            response = client.get("/health")
    else:
        transport = httpx.ASGITransport(app=app)
        async with httpx.AsyncClient(
            transport=transport,
            base_url="http://testserver",
        ) as client:
            response = await client.get("/health")

    assert response.status_code == 200

    payload = response.json()
    assert payload["service"] == settings.app_name
    assert payload["status"] == "ok"
    assert payload["environment"] == settings.app_env
    assert payload["checks"] == {
        "database": "not_checked",
        "redis": "not_checked",
    }
