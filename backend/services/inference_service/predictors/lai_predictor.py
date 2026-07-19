"""LAI inversion predictor backed by PROSAIL model."""

from __future__ import annotations

import logging
import sys
from pathlib import Path
from typing import Any, Mapping

import numpy as np

from services.inference_service.predictors.base import BasePredictor, PredictionOutput
from services.inference_service.schemas import ResolvedModelMetadata
from services.inference_service.loaders.model_loader import LoadedModel

logger = logging.getLogger(__name__)

# Resolve the PROSAIL package/LUT dir relative to the backend root so it works
# on any host (was previously a hardcoded developer Linux path).
PROSAIL_LUT_DIR = Path(__file__).resolve().parents[3] / "prosail_python"


class LAIPredictor(BasePredictor):
    """Predictor that executes PROSAIL-based LAI inversion using a LUT."""

    def predict(
        self,
        *,
        image_array: object | None,
        model_metadata: ResolvedModelMetadata,
        loaded_model: LoadedModel,
        extra_params: Mapping[str, Any] | None = None,
    ) -> PredictionOutput:
        """Invert LAI from reflectance data using PROSAIL LUT."""
        params = dict(extra_params or {})
        reflectance: dict[str, float] | list[list[float]] | None = params.get("reflectance")
        lut_path = params.get("lut_path", str(PROSAIL_LUT_DIR / "demo_lut.pkl"))
        method = params.get("method", "min_distance")

        if reflectance is None:
            raise ValueError("LAI inversion requires 'reflectance' in extra_params")

        try:
            from prosail_python.prosail_api import PROSAILEngine
        except ImportError:
            sys.path.insert(0, str(PROSAIL_LUT_DIR.parent))
            from prosail_python.prosail_api import PROSAILEngine

        engine = PROSAILEngine()
        engine.load_lut(lut_path)

        if isinstance(reflectance, dict):
            result = engine.invert_lai(reflectance, method=method)
            lai_results = [result["LAI"]]
            confidences = [result.get("confidence", 1.0)]
            distances = [result.get("distance", 0.0)]
        else:
            arr = reflectance
            results = engine.batch_invert_lai(arr, method=method)
            lai_results = [r["LAI"] for r in results]
            confidences = [r.get("confidence", 1.0) for r in results]
            distances = [r.get("distance", 0.0) for r in results]

        primary_lai = lai_results[0] if lai_results else 0.0
        primary_confidence = confidences[0] if confidences else 0.0

        output: dict[str, Any] = {
            "lai_results": lai_results,
            "num_pixels": len(lai_results),
            "mean_lai": float(np.mean(lai_results)) if lai_results else 0.0,
            "std_lai": float(np.std(lai_results)) if len(lai_results) > 1 else 0.0,
            "primary_lai": primary_lai,
            "primary_confidence": primary_confidence,
            "primary_distance": distances[0] if distances else 0.0,
            "lut_path": lut_path,
            "method": method,
        }

        return PredictionOutput(
            mask=None,
            affected_area=float(np.sum(lai_results)) if lai_results else 0.0,
            confidence=primary_confidence,
            polygons=[],
            mask_uri=None,
            metadata=output,
        )
