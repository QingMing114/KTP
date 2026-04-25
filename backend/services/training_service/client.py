"""Temporal client wrapper for starting training workflows."""

from __future__ import annotations

import logging

from temporalio.client import Client as TemporalClient

from services.training_service.config import TrainingServiceConfig, get_training_service_config
from services.training_service.schemas import (
    TrainingRequest,
    TrainingWorkflowStartResponse,
)
from services.training_service.workflows.training_workflow import TrainingWorkflow

logger = logging.getLogger(__name__)


class TrainingServiceClientError(Exception):
    """Raised when the training workflow cannot be started."""


class TrainingServiceClient:
    """Client wrapper around Temporal workflow start operations."""

    def __init__(
        self,
        config: TrainingServiceConfig | None = None,
        temporal_client: TemporalClient | None = None,
    ) -> None:
        self._config = config or get_training_service_config()
        self._temporal_client = temporal_client

    async def _get_client(self) -> TemporalClient:
        if self._temporal_client is not None:
            return self._temporal_client
        return await TemporalClient.connect(
            self._config.temporal_server_url,
            namespace=self._config.temporal_namespace,
        )

    async def start_training_workflow(
        self,
        request: TrainingRequest,
    ) -> TrainingWorkflowStartResponse:
        """Start a Temporal training workflow for the given request."""
        client = await self._get_client()
        workflow_id = (
            f"training-{request.request_id}-{request.region}-"
            f"{request.crop_type}-{request.output_model_version}"
        )
        logger.info(
            "training_workflow_start_started | request_id=%s | workflow_id=%s",
            request.request_id,
            workflow_id,
        )
        try:
            handle = await client.start_workflow(
                TrainingWorkflow.run,
                request.model_dump(),
                id=workflow_id,
                task_queue=self._config.temporal_task_queue,
            )
        except Exception as exc:
            logger.exception(
                "training_workflow_start_failed | request_id=%s | workflow_id=%s",
                request.request_id,
                workflow_id,
            )
            raise TrainingServiceClientError(
                f"Unable to start training workflow: {exc}"
            ) from exc

        result = TrainingWorkflowStartResponse(
            workflow_id=handle.id,
            run_id=getattr(handle, "first_execution_run_id", None),
            request_id=request.request_id,
            task_queue=self._config.temporal_task_queue,
            status="started",
        )
        logger.info(
            "training_workflow_start_succeeded | request_id=%s | workflow_id=%s",
            request.request_id,
            result.workflow_id,
        )
        return result


async def start_training_workflow(
    request: TrainingRequest,
) -> TrainingWorkflowStartResponse:
    """Convenience wrapper used by scripts and HTTP handlers."""
    return await TrainingServiceClient().start_training_workflow(request)
