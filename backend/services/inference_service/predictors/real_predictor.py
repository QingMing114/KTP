"""Real predictor backed by the migrated baldness RF pipeline."""

from __future__ import annotations

import logging
from pathlib import Path
from typing import Any, Mapping

from ml.baldness_rf.pipeline import run_baldness_rf_pipeline
from services.inference_service.config import (
    InferenceServiceConfig,
    get_inference_service_config,
)
from services.inference_service.predictors.base import BasePredictor, PredictionOutput
from services.inference_service.loaders.model_loader import LoadedModel
from services.inference_service.schemas import ResolvedModelMetadata

logger = logging.getLogger(__name__)


class RealPredictorNotReadyError(RuntimeError):
    """Raised when the real predictor boundary is selected before integration is complete."""


class RealPredictor(BasePredictor):
    """Real predictor that executes the migrated baldness RF pipeline."""

    def __init__(self, config: InferenceServiceConfig | None = None) -> None:
        self._config = config or get_inference_service_config()

    def predict(
        self,
        *,
        image_array: object | None,
        model_metadata: ResolvedModelMetadata,
        loaded_model: LoadedModel,
        extra_params: Mapping[str, Any] | None = None,
    ) -> PredictionOutput:
        """Execute the migrated baldness RF pipeline on a local multispectral image."""
        predictor_params = dict(extra_params or {})
        image_path = str(predictor_params.get("image_path", "")).strip()
        request_id = str(predictor_params.get("request_id", "real-infer")).strip()
        output_dir = str(
            predictor_params.get(
                "output_dir",
                Path(self._config.baldness_rf_work_dir) / request_id,
            )
        )
        local_model_path = loaded_model.metadata.get("local_artifact_path")
        if not image_path:
            raise RealPredictorNotReadyError("real predictor requires extra_params.image_path")
        if not local_model_path:
            raise RealPredictorNotReadyError(
                "real predictor requires a resolved local model artifact path"
            )

        logger.info(
            "real_predictor_started | backend=%s | image=%s | model=%s",
            loaded_model.backend,
            image_path,
            local_model_path,
        )
        pipeline_result = run_baldness_rf_pipeline(
            input_image_path=image_path,
            model_path=local_model_path,
            output_dir=output_dir,
        )
        logger.info(
            "real_predictor_succeeded | class_map=%s | confidence_map=%s",
            pipeline_result.classification_map_path,
            pipeline_result.confidence_map_path,
        )
        return PredictionOutput(
            mask=None,
            mask_uri=pipeline_result.classification_map_path,
            affected_area=pipeline_result.affected_area,
            confidence=pipeline_result.confidence,
            polygons=pipeline_result.polygons,
            metadata={
                "prediction_kind": "class_map",
                "confidence_map_uri": pipeline_result.confidence_map_path,
                "predictor_backend": loaded_model.backend,
            },
        )
