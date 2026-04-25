"""Orchestrator client for model registry lookups."""

from __future__ import annotations

from services.model_registry.local_client import LocalModelRegistryLookupClient


class ModelRegistryClient:
    """Thin orchestrator wrapper around the local model registry client."""

    def __init__(self, *, database_url: str) -> None:
        self._client = LocalModelRegistryLookupClient(database_url=database_url)

    def lookup_model(
        self,
        *,
        region: str,
        crop_type: str,
        task_type: str,
    ):
        return self._client.lookup_model(
            region=region,
            crop_type=crop_type,
            task_type=task_type,
        )
