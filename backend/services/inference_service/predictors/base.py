"""Predictor interfaces for the inference service."""

from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import Any, Mapping, TYPE_CHECKING

import numpy as np

if TYPE_CHECKING:
    from services.inference_service.loaders.model_loader import LoadedModel
    from services.inference_service.schemas import ResolvedModelMetadata


@dataclass(slots=True)
class PredictionOutput:
    """Structured internal predictor output."""

    mask: np.ndarray | None = None
    affected_area: float = 0.0
    confidence: float = 0.0
    polygons: list[list[tuple[float, float]]] = field(default_factory=list)
    mask_uri: str | None = None
    metadata: dict[str, Any] = field(default_factory=dict)


class BasePredictor(ABC):
    """Abstract predictor interface."""

    @abstractmethod
    def predict(
        self,
        *,
        image_array: np.ndarray | None,
        model_metadata: ResolvedModelMetadata,
        loaded_model: LoadedModel,
        extra_params: Mapping[str, Any] | None = None,
    ) -> PredictionOutput:
        """Run inference and return a structured prediction output."""
