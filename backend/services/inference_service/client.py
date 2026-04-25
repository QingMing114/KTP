"""Synchronous client wrapper for orchestrator-side inference execution."""

from __future__ import annotations

import logging
from pathlib import Path

import numpy as np
from PIL import Image

from services.inference_service.adapters.local_model_registry_client import (
    LocalModelRegistryClient,
)
from services.inference_service.config import (
    InferenceServiceConfig,
    get_inference_service_config,
)
from services.inference_service.schemas import InferenceRequest
from services.inference_service.service import InferenceService
from shared.async_utils import run_coro_sync
from shared.schemas.service_results import InferenceServiceResult

logger = logging.getLogger(__name__)


class InferenceServiceClientError(Exception):
    """Raised when local inference execution cannot be completed."""


class LocalInferenceServiceClient:
    """Run the inference service locally from synchronous orchestrator code."""

    def __init__(
        self,
        *,
        config: InferenceServiceConfig | None = None,
        database_url: str,
        default_image_path: str | None = None,
        service: InferenceService | None = None,
    ) -> None:
        self._config = config or get_inference_service_config()
        self._default_image_path = default_image_path
        self._service = service or InferenceService(
            config=self._config,
            model_registry_client=LocalModelRegistryClient(database_url=database_url),
        )

    def run_inference(
        self,
        *,
        request_id: str,
        region: str | None,
        crop_type: str | None,
        task_type: str | None,
        image_path: str | None = None,
        use_mock: bool | None = None,
        extra_params: dict | None = None,
        model_name: str | None = None,
        model_version: str | None = None,
    ) -> InferenceServiceResult:
        """Execute inference and return the normalized orchestrator payload."""
        if region is None or crop_type is None:
            raise InferenceServiceClientError(
                "region and crop_type are required for orchestrator inference execution"
            )

        resolved_use_mock = (
            self._config.default_use_mock if use_mock is None else use_mock
        )
        resolved_image_path = self._resolve_image_path(
            image_path=image_path,
            use_mock=resolved_use_mock,
        )
        logger.info(
            "local_inference_execution_started | request_id=%s | use_mock=%s | image_path=%s",
            request_id,
            resolved_use_mock,
            resolved_image_path,
        )

        request = InferenceRequest(
            request_id=request_id,
            region=region,
            crop_type=crop_type,
            task_type=task_type,
            image_path=resolved_image_path,
            use_mock=resolved_use_mock,
            extra_params=extra_params or {},
        )
        response = run_coro_sync(self._service.run_inference(request))
        if not response.success or response.result is None:
            logger.warning(
                "local_inference_execution_failed | request_id=%s | detail=%s",
                request_id,
                response.message,
            )
            raise InferenceServiceClientError(response.message)

        logger.info(
            "local_inference_execution_succeeded | request_id=%s | model_name=%s | version=%s",
            request_id,
            response.result.model_name,
            response.result.model_version,
        )
        return InferenceServiceResult(
            mask_uri=response.result.mask_uri,
            affected_area=response.result.affected_area,
            confidence=response.result.confidence,
            model_version=response.result.model_version,
            model_name=response.result.model_name,
            artifact_uri=response.result.artifact_uri,
            polygons=[polygon.model_dump() for polygon in response.result.polygons],
            raw_prediction_uri=response.result.raw_prediction_uri,
            confidence_map_uri=response.result.confidence_map_uri,
            warnings=list(response.result.warnings),
            class_distribution=[
                item.model_dump() for item in response.result.class_distribution
            ],
            class_labels=dict(response.result.class_labels),
            target_classes=list(response.result.target_classes),
        )

    def _resolve_image_path(self, *, image_path: str | None, use_mock: bool) -> str:
        if image_path:
            return image_path
        if self._default_image_path:
            return self._default_image_path
        if not use_mock:
            raise InferenceServiceClientError(
                "image_path is required when use_mock=false"
            )
        return self._create_demo_image()

    def _create_demo_image(self) -> str:
        demo_dir = Path(self._config.mask_output_dir) / "demo_inputs"
        demo_dir.mkdir(parents=True, exist_ok=True)
        demo_image_path = demo_dir / "orchestrator_mock_input.png"
        if demo_image_path.exists():
            return str(demo_image_path)

        x_axis = np.linspace(0, 255, num=64, dtype=np.uint8)
        y_axis = np.linspace(255, 0, num=64, dtype=np.uint8)
        red = np.tile(x_axis, (64, 1))
        green = np.tile(y_axis[:, None], (1, 64))
        blue = np.full((64, 64), 96, dtype=np.uint8)
        image = np.stack([red, green, blue], axis=-1)
        Image.fromarray(image).save(demo_image_path)
        return str(demo_image_path)
