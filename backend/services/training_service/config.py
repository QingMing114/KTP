"""Configuration for the Temporal training service."""

from __future__ import annotations

from functools import lru_cache

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict

from shared.config.settings import get_settings

base_settings = get_settings()


class TrainingServiceConfig(BaseSettings):
    """Settings for the training service and Temporal integration."""

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    temporal_server_url: str = Field(
        default=base_settings.temporal_server_url or "localhost:7233",
        validation_alias="TEMPORAL_SERVER_URL",
    )
    temporal_namespace: str = Field(
        default="default",
        validation_alias="TEMPORAL_NAMESPACE",
    )
    temporal_task_queue: str = Field(
        default="training-task-queue",
        validation_alias="TEMPORAL_TASK_QUEUE",
    )
    model_registry_url: str = Field(
        default=base_settings.model_registry_url or "http://127.0.0.1:8000",
        validation_alias="MODEL_REGISTRY_URL",
    )
    training_service_name: str = Field(
        default="training-service",
        validation_alias="TRAINING_SERVICE_NAME",
    )


@lru_cache
def get_training_service_config() -> TrainingServiceConfig:
    """Return a cached training service configuration instance."""
    return TrainingServiceConfig()
