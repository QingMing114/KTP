"""Integration-style tests for the LangGraph orchestrator scaffold."""

from __future__ import annotations

from pathlib import Path

import numpy as np
import pytest
import rasterio
from rasterio.transform import from_origin

from apps.orchestrator.config import get_orchestrator_runtime_config
from apps.orchestrator.graph.workflow import get_workflow
from apps.orchestrator.main import run_workflow_request
from apps.orchestrator.service_registry import (
    get_model_registry_lookup_client,
    get_orchestrator_executor_agent,
    get_orchestrator_planner_agent,
    get_orchestrator_tool_executor,
)
from infra.llm.config import get_agent_llm_config
from infra.llm.provider import get_agent_llm_provider
from services.inference_service.config import get_inference_service_config
from services.confidence_service.config import get_confidence_service_config
from services.rag_service.config import get_rag_service_config
from services.rag_service.schemas import DocumentIngestRequest
from services.rag_service.service import RAGService
from services.report_service.config import get_report_service_config
from services.model_registry.db import create_engine_for_url, create_session_factory, init_db
from services.model_registry.repository import ModelRegistryRepository
from services.model_registry.schemas import ModelRegisterRequest, ModelStatus
from services.model_registry.service import ModelRegistryService
from services.training_service.config import get_training_service_config
from services.visualization_service.config import get_visualization_service_config
from shared.schemas.orchestrator import WorkflowRequest

EXTERNAL_RF_MODEL_PATH = Path(
    "/home/D/liumeng/bantushibie/test/api_storage/models/rf_model.pkl"
)


class _FakeTemporalWorkflowHandle:
    def __init__(self, workflow_id: str, run_id: str) -> None:
        self.id = workflow_id
        self.first_execution_run_id = run_id


class _FakeTemporalClient:
    def __init__(self) -> None:
        self.calls: list[dict[str, object]] = []

    async def start_workflow(
        self,
        workflow_run,
        payload: dict[str, object],
        *,
        id: str,
        task_queue: str,
    ) -> _FakeTemporalWorkflowHandle:
        self.calls.append(
            {
                "workflow_run": workflow_run,
                "payload": payload,
                "id": id,
                "task_queue": task_queue,
            }
        )
        return _FakeTemporalWorkflowHandle(
            workflow_id=id,
            run_id="run-orchestrator-temporal-001",
        )


@pytest.fixture
def orchestrator_runtime(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> dict[str, object]:
    database_url = f"sqlite:///{tmp_path / 'orchestrator_registry.db'}"
    monkeypatch.setenv("AGENT_LLM_BACKEND", "heuristic")
    monkeypatch.setenv("ORCHESTRATOR_DATABASE_URL", database_url)
    monkeypatch.setenv("ORCHESTRATOR_DEFAULT_USE_MOCK", "true")
    monkeypatch.setenv(
        "ORCHESTRATOR_INFERENCE_MASK_OUTPUT_DIR",
        str(tmp_path / "orchestrator_masks"),
    )
    monkeypatch.setenv("VECTORSTORE_DIR", str(tmp_path / "rag_store"))
    monkeypatch.setenv("USE_MOCK_EMBEDDING", "true")
    monkeypatch.setenv("DEFAULT_TOP_K", "3")
    monkeypatch.setenv("RAG_EMBEDDING_DIMENSION", "64")
    monkeypatch.setenv("REPORT_OUTPUT_DIR", str(tmp_path / "reports"))
    monkeypatch.setenv("BALDNESS_RF_WORK_DIR", str(tmp_path / "rf_work"))
    monkeypatch.setenv("VISUALIZATION_OUTPUT_DIR", str(tmp_path / "visualizations"))

    get_orchestrator_runtime_config.cache_clear()
    get_agent_llm_config.cache_clear()
    get_agent_llm_provider.cache_clear()
    get_confidence_service_config.cache_clear()
    get_model_registry_lookup_client.cache_clear()
    get_orchestrator_planner_agent.cache_clear()
    get_orchestrator_tool_executor.cache_clear()
    get_orchestrator_executor_agent.cache_clear()
    get_inference_service_config.cache_clear()
    get_rag_service_config.cache_clear()
    get_report_service_config.cache_clear()
    get_training_service_config.cache_clear()
    get_visualization_service_config.cache_clear()
    get_workflow.cache_clear()

    engine = create_engine_for_url(database_url)
    init_db(engine)
    session_factory = create_session_factory(engine)
    rag_service = RAGService(config=get_rag_service_config())
    rag_service.ingest_document(
        DocumentIngestRequest(
            document_id="doc-henan-wheat",
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
        )
    )
    rag_service.ingest_document(
        DocumentIngestRequest(
            document_id="doc-yunnan-maize",
            title="Yunnan Maize Monitoring Guide",
            source="local://knowledge/yunnan-maize",
            text=(
                "Yunnan maize analysis often explains disease spread, drought stress, "
                "and local field response recommendations."
            ),
            metadata={
                "region": "yunnan",
                "crop_type": "maize",
                "task_type": "crop_health_detection",
            },
        )
    )

    try:
        yield {
            "database_url": database_url,
            "session_factory": session_factory,
            "tmp_path": tmp_path,
        }
    finally:
        engine.dispose()
        get_workflow.cache_clear()
        get_agent_llm_config.cache_clear()
        get_agent_llm_provider.cache_clear()
        get_confidence_service_config.cache_clear()
        get_inference_service_config.cache_clear()
        get_rag_service_config.cache_clear()
        get_report_service_config.cache_clear()
        get_training_service_config.cache_clear()
        get_visualization_service_config.cache_clear()
        get_orchestrator_planner_agent.cache_clear()
        get_orchestrator_executor_agent.cache_clear()
        get_orchestrator_tool_executor.cache_clear()
        get_model_registry_lookup_client.cache_clear()
        get_orchestrator_runtime_config.cache_clear()


def _register_ready_model(
    session_factory,
    *,
    artifact_uri: str,
    task_type: str = "crop_health_detection",
    region: str = "henan",
    crop_type: str = "wheat",
    model_name: str = "wheat-health-segmentation",
    model_version: str = "v1.0.0",
    metrics_json: dict | None = None,
) -> None:
    with session_factory() as session:
        service = ModelRegistryService(ModelRegistryRepository(session))
        service.register_model(
            ModelRegisterRequest(
                region=region,
                crop_type=crop_type,
                task_type=task_type,
                model_name=model_name,
                model_version=model_version,
                artifact_uri=artifact_uri,
                metrics_json=metrics_json or {"miou": 0.88},
                status=ModelStatus.READY,
            )
        )


def _create_test_multiband_tiff(image_path: Path) -> Path:
    height = 16
    width = 16
    data = np.stack(
        [
            np.full((height, width), fill_value=base_value, dtype=np.uint16)
            for base_value in (150, 180, 210, 240, 270, 300)
        ],
        axis=0,
    )
    with rasterio.open(
        image_path,
        "w",
        driver="GTiff",
        height=height,
        width=width,
        count=6,
        dtype=data.dtype,
        transform=from_origin(100, 100, 1, 1),
    ) as dataset:
        dataset.write(data)
    return image_path


def test_orchestrator_existing_model_path_runs_inference(
    orchestrator_runtime: dict[str, object],
) -> None:
    _register_ready_model(
        orchestrator_runtime["session_factory"],
        artifact_uri="mock://models/wheat-health-segmentation/v1.0.0",
    )
    response = run_workflow_request(
        WorkflowRequest(
            request_id="req-existing-001",
            user_query=(
                "Assess wheat health in Henan and provide a report with confidence."
            ),
        )
    )

    final_state = response.final_state
    assert response.status == "completed"
    assert final_state["model_exists"] is True
    assert final_state["training_triggered"] is False
    assert final_state["inference_result"] is not None
    assert Path(final_state["inference_result"]["mask_uri"]).exists()
    assert final_state["inference_result"]["model_version"] == "v1.0.0"
    assert final_state["rag_result"] is not None
    assert final_state["rag_result"]["top_k"] >= 1
    assert "local://knowledge/henan-wheat" in final_state["rag_result"]["sources"]
    assert final_state["report_result"] is not None
    assert final_state["confidence_result"] is not None
    assert final_state["visualization_result"] is not None
    assert Path(final_state["report_result"]["report_uri"]).exists()
    assert Path(final_state["visualization_result"]["visualization_uri"]).exists()
    assert any(item["stage"] == "run_inference" for item in final_state["stage_timings"])
    assert final_state["confidence_result"]["final_label"] in {"high", "medium", "low"}


def test_orchestrator_missing_model_path_triggers_training(
    orchestrator_runtime: dict[str, object],
) -> None:
    response = run_workflow_request(
        WorkflowRequest(
            request_id="req-training-001",
            user_query=(
                "Assess maize health in Yunnan and provide a report with explanation."
            ),
        )
    )

    final_state = response.final_state
    assert response.status == "completed"
    assert final_state["model_exists"] is False
    assert final_state["training_triggered"] is True
    assert final_state["training_job_id"] is not None
    assert final_state["inference_result"] is None
    assert final_state["rag_result"] is not None
    assert "local://knowledge/yunnan-maize" in final_state["rag_result"]["sources"]
    assert final_state["report_result"] is not None
    assert final_state["confidence_result"] is not None
    assert final_state["visualization_result"] is not None
    assert Path(final_state["report_result"]["report_uri"]).exists()
    assert Path(final_state["visualization_result"]["visualization_uri"]).exists()
    assert any(item["stage"] == "trigger_training" for item in final_state["stage_timings"])
    assert final_state["confidence_result"]["final_label"] in {"high", "medium", "low"}


def test_orchestrator_missing_model_path_can_start_temporal_training_workflow(
    orchestrator_runtime: dict[str, object],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    fake_temporal_client = _FakeTemporalClient()

    async def _fake_connect(*args, **kwargs):
        return fake_temporal_client

    monkeypatch.setenv("ORCHESTRATOR_TRAINING_BACKEND", "temporal")
    monkeypatch.setenv("TEMPORAL_TASK_QUEUE", "training-task-queue-test")
    monkeypatch.setattr(
        "services.training_service.client.TemporalClient.connect",
        _fake_connect,
    )
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

    response = run_workflow_request(
        WorkflowRequest(
            request_id="req-temporal-001",
            user_query=(
                "Assess maize health in Yunnan and provide a report with explanation."
            ),
            extra_params={
                "dataset_uri": "/tmp/custom-datasets/yunnan/maize/train",
                "output_model_name": "maize-health-yunnan",
                "output_model_version": "2026.03.15.1",
            },
        )
    )

    final_state = response.final_state
    assert response.status == "completed"
    assert final_state["model_exists"] is False
    assert final_state["training_triggered"] is True
    assert final_state["training_backend"] == "temporal"
    assert final_state["training_workflow_id"] == (
        "training-req-temporal-001-yunnan-maize-2026.03.15.1"
    )
    assert final_state["training_job_id"] == final_state["training_workflow_id"]
    assert final_state["training_run_id"] == "run-orchestrator-temporal-001"
    assert final_state["training_task_queue"] == "training-task-queue-test"
    assert final_state["inference_result"] is None
    assert "local://knowledge/yunnan-maize" in final_state["rag_result"]["sources"]
    assert final_state["report_result"] is not None
    assert final_state["confidence_result"] is not None
    assert final_state["visualization_result"] is not None
    assert Path(final_state["report_result"]["report_uri"]).exists()
    assert Path(final_state["visualization_result"]["visualization_uri"]).exists()
    assert final_state["confidence_result"]["final_label"] in {"high", "medium", "low"}

    assert len(fake_temporal_client.calls) == 1
    payload = fake_temporal_client.calls[0]["payload"]
    assert payload["dataset_uri"] == "/tmp/custom-datasets/yunnan/maize/train"
    assert payload["output_model_name"] == "maize-health-yunnan"
    assert payload["output_model_version"] == "2026.03.15.1"


@pytest.mark.skipif(
    not EXTERNAL_RF_MODEL_PATH.exists(),
    reason="external baldness RF model is not available",
)
def test_orchestrator_existing_model_path_supports_real_rf_inference(
    orchestrator_runtime: dict[str, object],
) -> None:
    _register_ready_model(
        orchestrator_runtime["session_factory"],
        artifact_uri=str(EXTERNAL_RF_MODEL_PATH),
        model_name="baldness-rf",
        model_version="rf-v1",
        metrics_json={
            "source": "test",
            "prediction_class_semantics": {
                "class_labels": {
                    "1": "baldness",
                    "2": "water",
                    "3": "non_crop_vegetation",
                    "4": "sorghum",
                },
                "target_classes": [1],
            },
        },
    )
    image_path = _create_test_multiband_tiff(
        Path(orchestrator_runtime["tmp_path"]) / "orchestrator_real_input.tif"
    )

    response = run_workflow_request(
        WorkflowRequest(
            request_id="req-real-rf-001",
            user_query=(
                "Assess wheat health in Henan and provide a report with confidence."
            ),
            image_path=str(image_path),
            use_mock=False,
        )
    )

    final_state = response.final_state
    assert response.status == "completed"
    assert final_state["model_exists"] is True
    assert final_state["training_triggered"] is False
    assert Path(final_state["inference_result"]["mask_uri"]).exists()
    assert Path(final_state["inference_result"]["raw_prediction_uri"]).exists()
    assert final_state["inference_result"]["model_version"] == "rf-v1"
    assert final_state["inference_result"]["target_classes"] == [1]
    assert "local://knowledge/henan-wheat" in final_state["rag_result"]["sources"]
    assert 0.0 <= final_state["inference_result"]["confidence"] <= 1.0
    assert Path(final_state["report_result"]["report_uri"]).exists()
    assert Path(final_state["visualization_result"]["visualization_uri"]).exists()
    assert final_state["confidence_result"]["final_label"] in {"high", "medium", "low"}
