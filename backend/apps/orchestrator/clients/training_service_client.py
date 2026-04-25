"""Orchestrator client for training workflow triggers."""

from __future__ import annotations

from temporalio.client import Client as TemporalClient

from services.training_service.config import TrainingServiceConfig
from services.training_service.local_client import LocalTrainingServiceClient


class TrainingServiceClient:
    """Thin orchestrator wrapper around the local training client."""

    def __init__(
        self,
        *,
        config: TrainingServiceConfig,
        temporal_client: TemporalClient | None = None,
        dataset_uri_root: str,
        output_model_prefix: str,
    ) -> None:
        self._client = LocalTrainingServiceClient(
            config=config,
            temporal_client=temporal_client,
            dataset_uri_root=dataset_uri_root,
            output_model_prefix=output_model_prefix,
        )

    def trigger_training(self, **kwargs):
        return self._client.trigger_training(**kwargs)
