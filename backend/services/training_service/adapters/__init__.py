"""Adapters for the training service."""

from services.training_service.adapters.model_registry_client import (
    ModelRegistryClient,
    ModelRegistryClientError,
)
from services.training_service.adapters.trainer_adapter import TrainerAdapter

__all__ = ["ModelRegistryClient", "ModelRegistryClientError", "TrainerAdapter"]
