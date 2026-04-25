"""Shared fixtures for integration-style gateway/orchestrator tests."""

from __future__ import annotations

from pathlib import Path

import pytest

from apps.api_gateway.config import get_api_gateway_config
from apps.api_gateway.main import create_app
from apps.orchestrator.config import get_orchestrator_runtime_config
from apps.orchestrator.service_registry import (
    get_model_registry_lookup_client,
    get_orchestrator_executor_agent,
    get_orchestrator_planner_agent,
    get_orchestrator_tool_executor,
)
from infra.llm.config import get_agent_llm_config
from infra.llm.provider import get_agent_llm_provider
from services.confidence_service.config import get_confidence_service_config
from services.inference_service.config import get_inference_service_config
from services.model_registry.db import create_engine_for_url, create_session_factory, init_db
from services.model_registry.repository import ModelRegistryRepository
from services.model_registry.schemas import ModelRegisterRequest, ModelStatus
from services.model_registry.service import ModelRegistryService
from services.rag_service.config import get_rag_service_config
from services.rag_service.schemas import DocumentIngestRequest
from services.rag_service.service import RAGService
from services.report_service.config import get_report_service_config
from services.training_service.config import get_training_service_config
from services.visualization_service.config import get_visualization_service_config
from test_support.chat_first_llm import IntegrationChatFirstLLMProvider

try:
    from apps.orchestrator.graph.workflow import get_workflow
except ModuleNotFoundError as exc:  # pragma: no cover - test environment dependent
    pytest.skip(f"integration tests require optional dependency: {exc.name}", allow_module_level=True)


@pytest.fixture
def integration_runtime(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> dict[str, object]:
    database_url = f"sqlite:///{tmp_path / 'integration_registry.db'}"
    monkeypatch.setenv("AGENT_LLM_BACKEND", "heuristic")
    monkeypatch.setenv("ORCHESTRATOR_DATABASE_URL", database_url)
    monkeypatch.setenv("ORCHESTRATOR_DEFAULT_USE_MOCK", "true")
    monkeypatch.setenv(
        "ORCHESTRATOR_INFERENCE_MASK_OUTPUT_DIR",
        str(tmp_path / "integration_masks"),
    )
    monkeypatch.setenv("VECTORSTORE_DIR", str(tmp_path / "integration_rag"))
    monkeypatch.setenv("USE_MOCK_EMBEDDING", "true")
    monkeypatch.setenv("DEFAULT_TOP_K", "3")
    monkeypatch.setenv("RAG_EMBEDDING_DIMENSION", "64")
    monkeypatch.setenv("REPORT_OUTPUT_DIR", str(tmp_path / "integration_reports"))
    monkeypatch.setenv("BALDNESS_RF_WORK_DIR", str(tmp_path / "integration_rf"))
    monkeypatch.setenv("VISUALIZATION_OUTPUT_DIR", str(tmp_path / "integration_visualizations"))
    monkeypatch.setenv(
        "API_GATEWAY_CONVERSATION_DB_PATH",
        str(tmp_path / "integration_gateway_conversations.sqlite3"),
    )
    monkeypatch.setenv("API_GATEWAY_CONVERSATION_HISTORY_LIMIT", "6")

    _clear_caches()

    engine = create_engine_for_url(database_url)
    init_db(engine)
    session_factory = create_session_factory(engine)
    _seed_ready_model(session_factory)
    _seed_knowledge()
    app = create_app(llm_provider_override=IntegrationChatFirstLLMProvider())

    try:
        yield {
            "tmp_path": tmp_path,
            "database_url": database_url,
            "gateway_app": app,
        }
    finally:
        engine.dispose()
        _clear_caches()


def _seed_ready_model(session_factory) -> None:
    with session_factory() as session:
        service = ModelRegistryService(ModelRegistryRepository(session))
        service.register_model(
            ModelRegisterRequest(
                region="henan",
                crop_type="wheat",
                task_type="crop_health_detection",
                model_name="wheat-health-segmentation",
                model_version="demo-v1",
                artifact_uri="mock://models/wheat-health-segmentation/demo-v1",
                metrics_json={"miou": 0.88},
                status=ModelStatus.READY,
            )
        )


def _seed_knowledge() -> None:
    rag_service = RAGService(config=get_rag_service_config())
    if not rag_service.query.__self__.get_health_snapshot:
        return
    documents = [
        DocumentIngestRequest(
            document_id="doc-henan-wheat-int",
            title="Henan Wheat Stress Guide",
            source="local://knowledge/henan-wheat",
            text=(
                "Henan wheat health monitoring often considers drought stress, "
                "disease pressure, and agronomic response plans."
            ),
            metadata={
                "region": "henan",
                "crop_type": "wheat",
                "task_type": "crop_health_detection",
            },
        ),
        DocumentIngestRequest(
            document_id="doc-yunnan-maize-int",
            title="Yunnan Maize Guide",
            source="local://knowledge/yunnan-maize",
            text=(
                "Yunnan maize monitoring often highlights disease spread, drought risk, "
                "and local field management suggestions."
            ),
            metadata={
                "region": "yunnan",
                "crop_type": "maize",
                "task_type": "crop_health_detection",
            },
        ),
    ]
    for document in documents:
        try:
            rag_service.ingest_document(document)
        except Exception:
            continue


def _clear_caches() -> None:
    get_api_gateway_config.cache_clear()
    get_orchestrator_runtime_config.cache_clear()
    get_agent_llm_config.cache_clear()
    get_agent_llm_provider.cache_clear()
    get_model_registry_lookup_client.cache_clear()
    get_orchestrator_planner_agent.cache_clear()
    get_orchestrator_tool_executor.cache_clear()
    get_orchestrator_executor_agent.cache_clear()
    get_confidence_service_config.cache_clear()
    get_inference_service_config.cache_clear()
    get_rag_service_config.cache_clear()
    get_report_service_config.cache_clear()
    get_training_service_config.cache_clear()
    get_visualization_service_config.cache_clear()
    get_workflow.cache_clear()
