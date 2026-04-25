"""HTTP client adapter for the model registry service."""

from __future__ import annotations

import logging

import httpx

from services.training_service.config import TrainingServiceConfig, get_training_service_config
from services.training_service.schemas import (
    EvaluationResult,
    ModelRegistrationResult,
    TrainingRequest,
    TrainingRunResult,
)

logger = logging.getLogger(__name__)


class ModelRegistryClientError(Exception):
    """Raised when the model registry adapter cannot register a model."""


class ModelRegistryClient:
    """HTTP adapter around the model registry service."""

    def __init__(
        self,
        config: TrainingServiceConfig | None = None,
        timeout_seconds: float = 10.0,
    ) -> None:
        self._config = config or get_training_service_config()
        self._timeout_seconds = timeout_seconds

    async def register_model(
        self,
        request: TrainingRequest,
        training_result: TrainingRunResult,
        evaluation_result: EvaluationResult,
    ) -> ModelRegistrationResult:
        """Register a trained model in the model registry service."""
        logger.info(
            "model_registry_registration_started | request_id=%s | model_version=%s",
            request.request_id,
            request.output_model_version,
        )
        payload = {
            "region": request.region,
            "crop_type": request.crop_type,
            "task_type": request.task_type,
            "model_name": request.output_model_name,
            "model_version": request.output_model_version,
            "artifact_uri": training_result.artifact_uri,
            "metrics_json": evaluation_result.metrics,
            "status": "ready",
            "description": (
                f"Registered by training workflow for request {request.request_id}"
            ),
        }
        url = f"{self._config.model_registry_url.rstrip('/')}/models"
        try:
            async with httpx.AsyncClient(timeout=self._timeout_seconds) as client:
                response = await client.post(url, json=payload)
                response.raise_for_status()
        except httpx.HTTPError as exc:
            logger.exception(
                "model_registry_registration_failed | request_id=%s",
                request.request_id,
            )
            raise ModelRegistryClientError(
                f"Failed to register model via model_registry API: {exc}"
            ) from exc

        body = response.json()
        result = ModelRegistrationResult(
            registered=True,
            model_id=body["id"],
            model_version=body["model_version"],
            status=body["status"],
        )
        logger.info(
            "model_registry_registration_succeeded | request_id=%s | model_id=%s",
            request.request_id,
            result.model_id,
        )
        return result
