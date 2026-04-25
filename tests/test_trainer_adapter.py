"""Tests for the mock trainer adapter."""

from __future__ import annotations

import pytest

from services.training_service.adapters.trainer_adapter import TrainerAdapter
from services.training_service.schemas import TrainingRequest


@pytest.fixture
def anyio_backend() -> str:
    return "asyncio"


@pytest.mark.anyio
async def test_trainer_adapter_methods_return_expected_fields() -> None:
    adapter = TrainerAdapter()
    request = TrainingRequest(
        request_id="req-adapter-001",
        region="henan",
        crop_type="wheat",
        task_type="baldness_detection",
        dataset_uri="mock://datasets/raw",
        base_model_name="unet_base",
        output_model_name="unet_rs_baldness",
        output_model_version="v4",
        trigger_reason="model_missing",
    )

    dataset_result = await adapter.prepare_dataset(request)
    training_result = await adapter.launch_training(request, dataset_result)
    evaluation_result = await adapter.evaluate_model(request, training_result)

    assert dataset_result.status == "prepared"
    assert dataset_result.sample_count == 2048
    assert training_result.train_status == "completed"
    assert training_result.framework == "mock-pytorch"
    assert evaluation_result.eval_status == "completed"
    assert {"miou", "f1", "precision", "recall"} <= set(evaluation_result.metrics)
