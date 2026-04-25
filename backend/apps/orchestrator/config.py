"""Runtime settings for local orchestrator integrations."""

from __future__ import annotations

from functools import lru_cache

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict

from shared.config.settings import get_settings


def _default_database_url() -> str:
    return get_settings().database_url


class OrchestratorRuntimeConfig(BaseSettings):
    """Settings used when the orchestrator wires local service adapters together."""

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    database_url: str = Field(
        default_factory=_default_database_url,
        validation_alias="ORCHESTRATOR_DATABASE_URL",
    )
    default_image_path: str | None = Field(
        default=None,
        validation_alias="ORCHESTRATOR_DEFAULT_IMAGE_PATH",
    )
    default_use_mock: bool = Field(
        default=True,
        validation_alias="ORCHESTRATOR_DEFAULT_USE_MOCK",
    )
    training_backend: str = Field(
        default="mock",
        validation_alias="ORCHESTRATOR_TRAINING_BACKEND",
    )
    training_dataset_uri_root: str = Field(
        default="/tmp/ktp_training_datasets",
        validation_alias="ORCHESTRATOR_TRAINING_DATASET_URI_ROOT",
    )
    training_model_prefix: str = Field(
        default="remote-sensing",
        validation_alias="ORCHESTRATOR_TRAINING_MODEL_PREFIX",
    )
    inference_mask_output_dir: str = Field(
        default="/tmp/ktp_orchestrator_masks",
        validation_alias="ORCHESTRATOR_INFERENCE_MASK_OUTPUT_DIR",
    )


@lru_cache(maxsize=1)
def get_orchestrator_runtime_config() -> OrchestratorRuntimeConfig:
    """Return a cached orchestrator runtime configuration instance."""
    return OrchestratorRuntimeConfig()
