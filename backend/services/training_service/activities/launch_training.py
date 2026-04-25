"""Training launch activity."""

from __future__ import annotations

from typing import Any

from temporalio import activity

from services.training_service.adapters.trainer_adapter import TrainerAdapter
from services.training_service.schemas import DatasetPreparationResult, TrainingRequest

trainer_adapter = TrainerAdapter()


@activity.defn(name="launch_training_activity")
async def launch_training_activity(payload: dict[str, Any]) -> dict[str, Any]:
    """Launch a training run from prepared data."""
    request = TrainingRequest.model_validate(payload["request"])
    dataset_result = DatasetPreparationResult.model_validate(payload["dataset_result"])
    activity.logger.info("launch_training_activity_started | request_id=%s", request.request_id)
    result = await trainer_adapter.launch_training(request, dataset_result)
    activity.logger.info("launch_training_activity_succeeded | request_id=%s", request.request_id)
    return result.model_dump()
