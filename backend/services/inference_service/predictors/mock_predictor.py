"""Deterministic mock predictor for inference service MVP flows."""

from __future__ import annotations

import logging
from typing import Any, Mapping

import numpy as np

from services.inference_service.predictors.base import BasePredictor, PredictionOutput
from services.inference_service.loaders.model_loader import LoadedModel
from services.inference_service.schemas import ResolvedModelMetadata

logger = logging.getLogger(__name__)


class MockPredictor(BasePredictor):
    """Stable predictor used to validate the service contract."""

    def predict(
        self,
        *,
        image_array: np.ndarray | None,
        model_metadata: ResolvedModelMetadata,
        loaded_model: LoadedModel,
        extra_params: Mapping[str, Any] | None = None,
    ) -> PredictionOutput:
        """Generate a deterministic mask and summary from the input image array."""
        logger.info(
            "mock_predictor_started | model_name=%s | version=%s | backend=%s",
            model_metadata.model_name,
            model_metadata.model_version,
            loaded_model.backend,
        )
        if image_array is None:
            raise ValueError("mock predictor requires a preprocessed image array")
        if image_array.ndim != 3:
            raise ValueError(
                f"Mock predictor expects a 3D image array, received shape={image_array.shape!r}"
            )

        grayscale = image_array.mean(axis=2)
        threshold_bias = float((extra_params or {}).get("threshold_bias", 0.0))
        threshold = float(
            np.clip(np.quantile(grayscale, 0.65) + threshold_bias, 0.05, 0.95)
        )
        mask = grayscale >= threshold

        if not np.any(mask):
            center_y, center_x = grayscale.shape[0] // 2, grayscale.shape[1] // 2
            mask[max(center_y - 1, 0) : center_y + 1, max(center_x - 1, 0) : center_x + 1] = True

        positive_pixels = int(mask.sum())
        confidence = float(np.clip(0.55 + mask.mean(), 0.55, 0.99))
        polygons = self._mask_to_polygons(mask)

        logger.info(
            "mock_predictor_succeeded | positive_pixels=%s | confidence=%.4f",
            positive_pixels,
            confidence,
        )
        return PredictionOutput(
            mask=mask.astype(np.uint8),
            affected_area=float(positive_pixels),
            confidence=confidence,
            polygons=polygons,
            metadata={
                "threshold": threshold,
                "predictor_backend": "mock",
                "prediction_kind": "binary_mask",
            },
        )

    def _mask_to_polygons(self, mask: np.ndarray) -> list[list[tuple[float, float]]]:
        ys, xs = np.where(mask)
        if ys.size == 0 or xs.size == 0:
            return []

        min_y, max_y = int(ys.min()), int(ys.max()) + 1
        min_x, max_x = int(xs.min()), int(xs.max()) + 1
        return [[
            (float(min_x), float(min_y)),
            (float(max_x), float(min_y)),
            (float(max_x), float(max_y)),
            (float(min_x), float(max_y)),
        ]]
