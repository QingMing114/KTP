"""Orchestrator client for inference execution."""

from __future__ import annotations

from services.inference_service.client import LocalInferenceServiceClient
from services.inference_service.config import InferenceServiceConfig


class InferenceServiceClient:
    """Thin orchestrator wrapper around the local inference client."""

    def __init__(
        self,
        *,
        config: InferenceServiceConfig,
        database_url: str,
        default_image_path: str | None,
    ) -> None:
        self._client = LocalInferenceServiceClient(
            config=config,
            database_url=database_url,
            default_image_path=default_image_path,
        )

    def run_inference(self, **kwargs):
        return self._client.run_inference(**kwargs)
