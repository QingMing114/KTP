"""Helpers for resolving configurable prediction class semantics."""

from __future__ import annotations

from collections.abc import Mapping
import json
from typing import Any

from pydantic import Field

from shared.schemas.common import BaseSchema


class PredictionClassSemantics(BaseSchema):
    """Configurable mapping from model classes to target semantics."""

    class_labels: dict[int, str] = Field(default_factory=dict)
    target_classes: list[int] = Field(default_factory=list)
    background_classes: list[int] = Field(default_factory=lambda: [0])
    source: str | None = Field(default=None)

    @classmethod
    def from_raw(
        cls,
        raw: Mapping[str, Any] | None,
        *,
        source: str | None = None,
    ) -> PredictionClassSemantics | None:
        """Parse a flexible mapping payload into a normalized schema."""
        if raw is None:
            return None
        class_labels_raw = raw.get("class_labels") or raw.get("labels") or {}
        target_classes_raw = raw.get("target_classes") or raw.get("positive_classes") or []
        background_classes_raw = raw.get("background_classes") or [0]
        return cls(
            class_labels={int(key): str(value) for key, value in class_labels_raw.items()},
            target_classes=[int(value) for value in target_classes_raw],
            background_classes=[int(value) for value in background_classes_raw],
            source=source or raw.get("source"),
        )


def resolve_prediction_class_semantics(
    *,
    model_metrics: Mapping[str, Any] | None,
    extra_params: Mapping[str, Any] | None,
    config_default_json: str | None = None,
) -> PredictionClassSemantics | None:
    """Resolve semantics from request parameters, model metadata, or config."""
    if extra_params and isinstance(extra_params.get("prediction_class_semantics"), Mapping):
        return PredictionClassSemantics.from_raw(
            extra_params.get("prediction_class_semantics"),
            source="request.extra_params.prediction_class_semantics",
        )
    if model_metrics and isinstance(model_metrics.get("prediction_class_semantics"), Mapping):
        return PredictionClassSemantics.from_raw(
            model_metrics.get("prediction_class_semantics"),
            source="model.metrics_json.prediction_class_semantics",
        )
    if config_default_json:
        payload = json.loads(config_default_json)
        if isinstance(payload, Mapping):
            return PredictionClassSemantics.from_raw(
                payload,
                source="inference.default_prediction_class_semantics_json",
            )
    return None
