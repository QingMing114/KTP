"""Model evaluation activity."""

from __future__ import annotations

from typing import Any

from temporalio import activity

from services.training_service.adapters.trainer_adapter import TrainerAdapter
from services.training_service.schemas import TrainingRequest, TrainingRunResult

trainer_adapter = TrainerAdapter()


@activity.defn(name="evaluate_model_activity")
async def evaluate_model_activity(payload: dict[str, Any]) -> dict[str, Any]:
    """Evaluate a trained model artifact."""
    request = TrainingRequest.model_validate(payload["request"])
    training_result = TrainingRunResult.model_validate(payload["training_result"])
    activity.logger.info("evaluate_model_activity_started | request_id=%s", request.request_id)
    result = await trainer_adapter.evaluate_model(request, training_result)
    activity.logger.info("evaluate_model_activity_succeeded | request_id=%s", request.request_id)
    return result.model_dump()
