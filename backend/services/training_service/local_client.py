"""Synchronous wrapper for starting Temporal training workflows from the orchestrator."""

from __future__ import annotations

import logging
from typing import Any

from temporalio.client import Client as TemporalClient

from services.training_service.client import (
    TrainingServiceClient,
    TrainingServiceClientError,
)
from services.training_service.config import (
    TrainingServiceConfig,
    get_training_service_config,
)
from services.training_service.schemas import TrainingRequest
from shared.async_utils import run_coro_sync
from shared.schemas.service_results import TrainingTriggerResult

logger = logging.getLogger(__name__)


class LocalTrainingServiceClient:
    """Run the Temporal training client from synchronous orchestrator code."""

    def __init__(
        self,
        *,
        config: TrainingServiceConfig | None = None,
        temporal_client: TemporalClient | None = None,
        dataset_uri_root: str = "/tmp/ktp_training_datasets",
        output_model_prefix: str = "remote-sensing",
    ) -> None:
        self._config = config or get_training_service_config()
        self._client = TrainingServiceClient(
            config=self._config,
            temporal_client=temporal_client,
        )
        self._dataset_uri_root = dataset_uri_root.rstrip("/")
        self._output_model_prefix = output_model_prefix

    def trigger_training(
        self,
        *,
        request_id: str,
        task_type: str | None,
        region: str | None,
        crop_type: str | None,
        extra_params: dict[str, Any] | None = None,
    ) -> TrainingTriggerResult:
        """Start a Temporal training workflow and return the normalized result."""
        if task_type is None or region is None or crop_type is None:
            raise TrainingServiceClientError(
                "task_type, region, and crop_type are required for Temporal training"
            )

        payload = extra_params or {}
        training_request = TrainingRequest(
            request_id=request_id,
            region=region,
            crop_type=crop_type,
            task_type=task_type,
            dataset_uri=self._build_dataset_uri(
                task_type=task_type,
                region=region,
                crop_type=crop_type,
                dataset_uri=payload.get("dataset_uri"),
            ),
            base_model_name=self._coerce_optional_str(payload.get("base_model_name")),
            output_model_name=self._build_output_model_name(
                task_type=task_type,
                region=region,
                crop_type=crop_type,
                explicit_name=payload.get("output_model_name"),
            ),
            output_model_version=self._build_output_model_version(
                request_id=request_id,
                explicit_version=payload.get("output_model_version"),
            ),
            trigger_reason=self._build_trigger_reason(
                task_type=task_type,
                region=region,
                crop_type=crop_type,
                explicit_reason=payload.get("trigger_reason"),
            ),
        )

        logger.info(
            "local_training_execution_started | request_id=%s | task_type=%s | region=%s | crop_type=%s",
            request_id,
            task_type,
            region,
            crop_type,
        )
        response = run_coro_sync(
            self._client.start_training_workflow(training_request)
        )
        logger.info(
            "local_training_execution_succeeded | request_id=%s | workflow_id=%s",
            request_id,
            response.workflow_id,
        )
        return TrainingTriggerResult(
            training_triggered=True,
            training_job_id=response.workflow_id,
            workflow_id=response.workflow_id,
            run_id=response.run_id,
            task_queue=response.task_queue,
            backend="temporal",
        )

    def _build_dataset_uri(
        self,
        *,
        task_type: str,
        region: str,
        crop_type: str,
        dataset_uri: Any,
    ) -> str:
        explicit_dataset_uri = self._coerce_optional_str(dataset_uri)
        if explicit_dataset_uri:
            return explicit_dataset_uri
        return (
            f"{self._dataset_uri_root}/{task_type}/{region}/{crop_type}/"
            f"{region}-{crop_type}-dataset"
        )

    def _build_output_model_name(
        self,
        *,
        task_type: str,
        region: str,
        crop_type: str,
        explicit_name: Any,
    ) -> str:
        resolved = self._coerce_optional_str(explicit_name)
        if resolved:
            return resolved
        return "-".join(
            [
                self._output_model_prefix,
                task_type.replace("_", "-"),
                region,
                crop_type,
            ]
        )

    def _build_output_model_version(
        self,
        *,
        request_id: str,
        explicit_version: Any,
    ) -> str:
        resolved = self._coerce_optional_str(explicit_version)
        if resolved:
            return resolved
        return f"auto-{request_id[:8]}"

    def _build_trigger_reason(
        self,
        *,
        task_type: str,
        region: str,
        crop_type: str,
        explicit_reason: Any,
    ) -> str:
        resolved = self._coerce_optional_str(explicit_reason)
        if resolved:
            return resolved
        return (
            "No ready model was found for "
            f"region={region} crop_type={crop_type} task_type={task_type}."
        )

    @staticmethod
    def _coerce_optional_str(value: Any) -> str | None:
        if value is None:
            return None
        text = str(value).strip()
        return text or None
