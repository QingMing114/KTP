"""Local model registry adapter used by the inference service in integration mode."""

from __future__ import annotations

from services.inference_service.adapters.model_registry_client import (
    ModelRegistryClientError,
)
from services.inference_service.schemas import ResolvedModelMetadata
from services.model_registry.local_client import LocalModelRegistryLookupClient


class LocalModelRegistryClient:
    """Resolve ready models without requiring an external model registry server."""

    def __init__(self, *, database_url: str) -> None:
        self._lookup_client = LocalModelRegistryLookupClient(database_url=database_url)

    async def lookup_ready_model(
        self,
        *,
        region: str,
        crop_type: str,
        task_type: str,
    ) -> ResolvedModelMetadata | None:
        """Return ready model metadata or ``None`` when no model is available."""
        lookup = self._lookup_client.lookup_model(
            region=region,
            crop_type=crop_type,
            task_type=task_type,
        )
        if not lookup.model_exists:
            return None

        required_fields = ["model_id", "model_name", "model_version", "artifact_uri"]
        missing_fields = [
            field
            for field in required_fields
            if getattr(lookup, field, None) is None
        ]
        if missing_fields:
            raise ModelRegistryClientError(
                "Local model registry lookup response is missing required fields: "
                + ", ".join(missing_fields)
            )

        return ResolvedModelMetadata(
            model_id=int(lookup.model_id),
            model_name=str(lookup.model_name),
            model_version=str(lookup.model_version),
            artifact_uri=str(lookup.artifact_uri),
            status=lookup.status.value if lookup.status else None,
            metrics_json=lookup.metrics_json,
            description=lookup.description,
        )
