"""Configuration for the confidence evaluation service."""

from __future__ import annotations

from functools import lru_cache

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class ConfidenceServiceConfig(BaseSettings):
    """Settings used by the confidence evaluation service."""

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    confidence_service_name: str = Field(
        default="confidence-service",
        validation_alias="CONFIDENCE_SERVICE_NAME",
    )
    image_confidence_weight: float = Field(
        default=0.45,
        validation_alias="IMAGE_CONFIDENCE_WEIGHT",
    )
    text_confidence_weight: float = Field(
        default=0.2,
        validation_alias="TEXT_CONFIDENCE_WEIGHT",
    )
    workflow_confidence_weight: float = Field(
        default=0.35,
        validation_alias="WORKFLOW_CONFIDENCE_WEIGHT",
    )


@lru_cache(maxsize=1)
def get_confidence_service_config() -> ConfidenceServiceConfig:
    """Return the cached confidence service configuration."""
    return ConfidenceServiceConfig()
