"""HTTP adapter for looking up ready models from the model registry service."""

from __future__ import annotations

import logging

import httpx

from services.inference_service.config import (
    InferenceServiceConfig,
    get_inference_service_config,
)
from services.inference_service.schemas import ResolvedModelMetadata

logger = logging.getLogger(__name__)


class ModelRegistryClientError(Exception):
    """Raised when the model registry lookup cannot be completed."""


class ModelRegistryClient:
    """HTTP client wrapper around the model registry lookup endpoint."""

    def __init__(
        self,
        config: InferenceServiceConfig | None = None,
        timeout_seconds: float | None = None,
    ) -> None:
        self._config = config or get_inference_service_config()
        self._timeout_seconds = (
            timeout_seconds or self._config.inference_http_timeout_seconds
        )

    async def lookup_ready_model(
        self,
        *,
        region: str,
        crop_type: str,
        task_type: str,
    ) -> ResolvedModelMetadata | None:
        """Return the latest ready model metadata, or ``None`` when no model exists."""
        logger.info(
            "inference_model_lookup_started | region=%s | crop_type=%s | task_type=%s",
            region,
            crop_type,
            task_type,
        )
        url = f"{self._config.model_registry_url.rstrip('/')}/models/lookup"
        try:
            async with httpx.AsyncClient(
                timeout=self._timeout_seconds,
                trust_env=False,
            ) as client:
                response = await client.get(
                    url,
                    params={
                        "region": region,
                        "crop_type": crop_type,
                        "task_type": task_type,
                    },
                )
                response.raise_for_status()
        except httpx.HTTPError as exc:
            logger.exception(
                "inference_model_lookup_failed | region=%s | crop_type=%s | task_type=%s",
                region,
                crop_type,
                task_type,
            )
            raise ModelRegistryClientError(
                f"Failed to query model registry lookup endpoint: {exc}"
            ) from exc

        payload = response.json()
        if not payload.get("model_exists", False):
            logger.info(
                "inference_model_lookup_completed | model_exists=false | reason=%s",
                payload.get("reason"),
            )
            return None

        required_fields = ["model_id", "model_name", "model_version", "artifact_uri"]
        missing_fields = [field for field in required_fields if payload.get(field) is None]
        if missing_fields:
            raise ModelRegistryClientError(
                "Model registry lookup response is missing required fields: "
                + ", ".join(missing_fields)
            )

        resolved_model = ResolvedModelMetadata(
            model_id=int(payload["model_id"]),
            model_name=str(payload["model_name"]),
            model_version=str(payload["model_version"]),
            artifact_uri=str(payload["artifact_uri"]),
            status=payload.get("status"),
            metrics_json=payload.get("metrics_json"),
            description=payload.get("description"),
        )
        logger.info(
            "inference_model_lookup_completed | model_exists=true | model_id=%s | version=%s",
            resolved_model.model_id,
            resolved_model.model_version,
        )
        return resolved_model
