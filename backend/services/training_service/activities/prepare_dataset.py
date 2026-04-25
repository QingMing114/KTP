"""Dataset preparation activity."""

from __future__ import annotations

from typing import Any

from temporalio import activity

from services.training_service.adapters.trainer_adapter import TrainerAdapter
from services.training_service.schemas import TrainingRequest

trainer_adapter = TrainerAdapter()


@activity.defn(name="prepare_dataset_activity")
async def prepare_dataset_activity(request_payload: dict[str, Any]) -> dict[str, Any]:
    """Prepare a dataset for a training request."""
    request = TrainingRequest.model_validate(request_payload)
    activity.logger.info("prepare_dataset_activity_started | request_id=%s", request.request_id)
    result = await trainer_adapter.prepare_dataset(request)
    activity.logger.info("prepare_dataset_activity_succeeded | request_id=%s", request.request_id)
    return result.model_dump()
