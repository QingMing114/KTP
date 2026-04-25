"""Tests for the inference service mock predictor."""

from __future__ import annotations

import numpy as np

from services.inference_service.loaders.model_loader import LoadedModel
from services.inference_service.predictors.mock_predictor import MockPredictor
from services.inference_service.schemas import ResolvedModelMetadata


def test_mock_predictor_returns_stable_structured_output() -> None:
    predictor = MockPredictor()
    image_array = np.zeros((12, 12, 3), dtype=np.float32)
    image_array[3:9, 4:10, :] = 1.0

    output = predictor.predict(
        image_array=image_array,
        model_metadata=ResolvedModelMetadata(
            model_id=1,
            model_name="baldness-rf",
            model_version="v1",
            artifact_uri="mock://models/baldness-rf/v1/model.pkl",
            status="ready",
        ),
        loaded_model=LoadedModel(
            backend="mock",
            model_name="baldness-rf",
            model_version="v1",
            artifact_uri="mock://models/baldness-rf/v1/model.pkl",
            model_object={"kind": "mock-model"},
        ),
    )

    assert output.mask.shape == (12, 12)
    assert float(output.affected_area) > 0.0
    assert 0.0 <= float(output.confidence) <= 1.0
    assert len(output.polygons) == 1
    assert len(output.polygons[0]) == 4
