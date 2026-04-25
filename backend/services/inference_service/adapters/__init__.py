"""Adapters for the inference service."""

from services.inference_service.adapters.model_registry_client import (
    ModelRegistryClient,
    ModelRegistryClientError,
)

__all__ = ["ModelRegistryClient", "ModelRegistryClientError"]
