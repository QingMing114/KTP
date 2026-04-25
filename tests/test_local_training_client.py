"""Tests for the orchestrator-side Temporal training client wrapper."""

from __future__ import annotations

from dataclasses import dataclass

from services.training_service.config import TrainingServiceConfig
from services.training_service.local_client import LocalTrainingServiceClient


@dataclass
class _FakeWorkflowHandle:
    id: str
    first_execution_run_id: str


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
    ) -> _FakeWorkflowHandle:
        self.calls.append(
            {
                "workflow_run": workflow_run,
                "payload": payload,
                "id": id,
                "task_queue": task_queue,
            }
        )
        return _FakeWorkflowHandle(
            id=id,
            first_execution_run_id="run-local-training-001",
        )


def test_local_training_client_starts_temporal_workflow_with_derived_fields() -> None:
    fake_temporal_client = _FakeTemporalClient()
    client = LocalTrainingServiceClient(
        config=TrainingServiceConfig(
            TEMPORAL_SERVER_URL="127.0.0.1:7233",
            TEMPORAL_NAMESPACE="default",
            TEMPORAL_TASK_QUEUE="training-task-queue-test",
            MODEL_REGISTRY_URL="http://127.0.0.1:9000",
            TRAINING_SERVICE_NAME="training-service",
        ),
        temporal_client=fake_temporal_client,
        dataset_uri_root="/tmp/training-datasets",
        output_model_prefix="rs-platform",
    )

    result = client.trigger_training(
        request_id="req-train-12345678",
        task_type="crop_health_detection",
        region="yunnan",
        crop_type="maize",
        extra_params={
            "base_model_name": "foundation-seg-v1",
        },
    )

    assert result.training_triggered is True
    assert result.training_job_id == "training-req-train-12345678-yunnan-maize-auto-req-trai"
    assert result.workflow_id == result.training_job_id
    assert result.run_id == "run-local-training-001"
    assert result.task_queue == "training-task-queue-test"
    assert result.backend == "temporal"

    assert len(fake_temporal_client.calls) == 1
    payload = fake_temporal_client.calls[0]["payload"]
    assert payload["dataset_uri"] == (
        "/tmp/training-datasets/crop_health_detection/yunnan/maize/"
        "yunnan-maize-dataset"
    )
    assert payload["base_model_name"] == "foundation-seg-v1"
    assert payload["output_model_name"] == "rs-platform-crop-health-detection-yunnan-maize"
    assert payload["output_model_version"] == "auto-req-trai"
    assert payload["trigger_reason"] == (
        "No ready model was found for "
        "region=yunnan crop_type=maize task_type=crop_health_detection."
    )
