"""Model registration activity."""

from __future__ import annotations

from typing import Any

from temporalio import activity

from services.training_service.adapters.model_registry_client import ModelRegistryClient
from services.training_service.schemas import RegisterModelActivityInput

model_registry_client = ModelRegistryClient()


@activity.defn(name="register_model_activity")
async def register_model_activity(payload: dict[str, Any]) -> dict[str, Any]:
    """Register a trained model in the model registry if evaluation passed."""
    activity_input = RegisterModelActivityInput.model_validate(payload)
    request = activity_input.request
    evaluation_result = activity_input.evaluation_result
    activity.logger.info("register_model_activity_started | request_id=%s", request.request_id)
    if not evaluation_result.passed:
        result = {
            "registered": False,
            "model_id": None,
            "model_version": request.output_model_version,
            "status": "skipped",
        }
        activity.logger.info(
            "register_model_activity_skipped | request_id=%s | reason=evaluation_failed",
            request.request_id,
        )
        return result

    result = await model_registry_client.register_model(
        request=request,
        training_result=activity_input.training_result,
        evaluation_result=evaluation_result,
    )
    activity.logger.info(
        "register_model_activity_succeeded | request_id=%s | model_id=%s",
        request.request_id,
        result.model_id,
    )
    return result.model_dump()
