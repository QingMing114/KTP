"""Model loading boundaries for the inference service."""

from __future__ import annotations

from dataclasses import dataclass, field
import logging
from pathlib import Path
from typing import Any

from services.inference_service.config import (
    InferenceServiceConfig,
    get_inference_service_config,
)
from services.inference_service.schemas import ResolvedModelMetadata

logger = logging.getLogger(__name__)


@dataclass(slots=True)
class LoadedModel:
    """Runtime model handle returned by the model loader."""

    backend: str
    model_name: str
    model_version: str
    artifact_uri: str
    model_object: object | None = None
    metadata: dict[str, Any] = field(default_factory=dict)


class ModelLoader:
    """Boundary for future mock and real model loading strategies."""

    def __init__(self, config: InferenceServiceConfig | None = None) -> None:
        self._config = config or get_inference_service_config()

    def load_mock_model(self, model_metadata: ResolvedModelMetadata) -> LoadedModel:
        """Return a deterministic mock model handle."""
        logger.info(
            "mock_model_load_started | model_name=%s | version=%s",
            model_metadata.model_name,
            model_metadata.model_version,
        )
        loaded_model = LoadedModel(
            backend="mock",
            model_name=model_metadata.model_name,
            model_version=model_metadata.model_version,
            artifact_uri=model_metadata.artifact_uri,
            model_object={"kind": "mock-model"},
        )
        logger.info(
            "mock_model_load_succeeded | model_name=%s | version=%s",
            loaded_model.model_name,
            loaded_model.model_version,
        )
        return loaded_model

    def load_real_model(self, model_metadata: ResolvedModelMetadata) -> LoadedModel:
        """Resolve a local RF model artifact for real inference."""
        local_artifact_path = self._resolve_local_artifact_path(model_metadata.artifact_uri)
        logger.info(
            "real_model_load_started | model_name=%s | version=%s | backend=%s",
            model_metadata.model_name,
            model_metadata.model_version,
            self._config.real_predictor_backend,
        )
        if local_artifact_path is None:
            raise FileNotFoundError(
                "unable to resolve a local model artifact path from artifact_uri="
                f"{model_metadata.artifact_uri}"
            )
        loaded_model = LoadedModel(
            backend=self._config.real_predictor_backend,
            model_name=model_metadata.model_name,
            model_version=model_metadata.model_version,
            artifact_uri=local_artifact_path,
            model_object=None,
            metadata={
                "integration_status": "baldness_rf_ready",
                "external_source_root": self._config.baldness_rf_source_root,
                "local_artifact_path": local_artifact_path,
            },
        )
        logger.info(
            "real_model_load_succeeded | model_name=%s | version=%s | artifact=%s",
            loaded_model.model_name,
            loaded_model.model_version,
            local_artifact_path,
        )
        return loaded_model

    def _resolve_local_artifact_path(self, artifact_uri: str) -> str | None:
        candidate_paths: list[Path] = []
        if artifact_uri.startswith("file://"):
            candidate_paths.append(Path(artifact_uri.removeprefix("file://")))
        else:
            candidate_paths.append(Path(artifact_uri))

        default_model_path = self._config.baldness_rf_default_model_path
        if default_model_path:
            candidate_paths.append(Path(default_model_path))

        for candidate in candidate_paths:
            if candidate.exists() and candidate.is_file():
                return str(candidate)
        return None
