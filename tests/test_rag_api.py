"""API tests for the RAG service."""

from __future__ import annotations

import asyncio
from concurrent.futures import TimeoutError as FutureTimeoutError
from pathlib import Path
import threading

import httpx
import pytest
from fastapi.testclient import TestClient

from services.rag_service.config import RAGServiceConfig
from services.rag_service.main import create_app
from services.rag_service.service import RAGService


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
    config = RAGServiceConfig(
        RAG_SERVICE_NAME="rag-service",
        VECTORSTORE_DIR=str(tmp_path / "rag_store"),
        DEFAULT_TOP_K=2,
        USE_MOCK_EMBEDDING=True,
        EMBEDDING_MODEL_NAME="sentence-transformers/all-MiniLM-L6-v2",
        RAG_EMBEDDING_DIMENSION=64,
        RAG_CHUNK_SIZE=32,
        RAG_CHUNK_OVERLAP=8,
        RAG_SEARCH_CANDIDATE_MULTIPLIER=4,
    )
    service = RAGService(config=config)
    return create_app(config=config, service=service)


@pytest.mark.anyio
async def test_rag_api_ingest_query_and_health(tmp_path: Path) -> None:
    app = _create_test_app(tmp_path)

    if _supports_testclient_runtime():
        with TestClient(app) as client:
            _assert_rag_api_contract(client)
    else:
        transport = httpx.ASGITransport(app=app)
        async with httpx.AsyncClient(
            transport=transport,
            base_url="http://testserver",
        ) as client:
            await _assert_rag_api_contract_async(client)


def _assert_rag_api_contract(client: TestClient) -> None:
    health_response = client.get("/health")
    assert health_response.status_code == 200
    assert health_response.json()["service"] == "rag-service"

    ingest_response = client.post(
        "/documents/ingest",
        json={
            "document_id": "doc-henan-wheat",
            "title": "Henan Wheat Stress Guide",
            "source": "local://knowledge/henan-wheat",
            "text": (
                "Henan wheat health monitoring often considers drought stress, "
                "disease pressure, and agronomic response plans."
            ),
            "metadata": {
                "region": "henan",
                "crop_type": "wheat",
                "task_type": "crop_health_detection",
            },
        },
    )
    assert ingest_response.status_code == 200
    assert ingest_response.json()["success"] is True

    query_response = client.post(
        "/query",
        json={
            "request_id": "req-rag-001",
            "query": "What factors affect wheat health in Henan?",
            "top_k": 2,
            "task_type": "crop_health_detection",
            "region": "henan",
            "crop_type": "wheat",
            "context": {"goal": "build_report"},
        },
    )
    assert query_response.status_code == 200
    payload = query_response.json()
    assert payload["success"] is True
    assert payload["query"] == "What factors affect wheat health in Henan?"
    assert len(payload["results"]) >= 1
    assert payload["results"][0]["source"] == "local://knowledge/henan-wheat"


async def _assert_rag_api_contract_async(client: httpx.AsyncClient) -> None:
    health_response = await client.get("/health")
    assert health_response.status_code == 200
    assert health_response.json()["service"] == "rag-service"

    ingest_response = await client.post(
        "/documents/ingest",
        json={
            "document_id": "doc-henan-wheat",
            "title": "Henan Wheat Stress Guide",
            "source": "local://knowledge/henan-wheat",
            "text": (
                "Henan wheat health monitoring often considers drought stress, "
                "disease pressure, and agronomic response plans."
            ),
            "metadata": {
                "region": "henan",
                "crop_type": "wheat",
                "task_type": "crop_health_detection",
            },
        },
    )
    assert ingest_response.status_code == 200
    assert ingest_response.json()["success"] is True

    query_response = await client.post(
        "/query",
        json={
            "request_id": "req-rag-001",
            "query": "What factors affect wheat health in Henan?",
            "top_k": 2,
            "task_type": "crop_health_detection",
            "region": "henan",
            "crop_type": "wheat",
            "context": {"goal": "build_report"},
        },
    )
    assert query_response.status_code == 200
    payload = query_response.json()
    assert payload["success"] is True
    assert len(payload["results"]) >= 1
    assert payload["results"][0]["source"] == "local://knowledge/henan-wheat"
