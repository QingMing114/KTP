"""Configuration for the inference service."""

from __future__ import annotations

from functools import lru_cache

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict

from shared.config.settings import get_settings

base_settings = get_settings()


class InferenceServiceConfig(BaseSettings):
    """Settings for the inference service runtime."""

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    inference_service_name: str = Field(
        default="inference-service",
        validation_alias="INFERENCE_SERVICE_NAME",
    )
    model_registry_url: str = Field(
        default=base_settings.model_registry_url or "http://127.0.0.1:8000",
        validation_alias="MODEL_REGISTRY_URL",
    )
    default_task_type: str = Field(
        default="baldness_detection",
        validation_alias="DEFAULT_TASK_TYPE",
    )
    default_use_mock: bool = Field(
        default=True,
        validation_alias="DEFAULT_USE_MOCK",
    )
    mask_output_dir: str = Field(
        default="/tmp/ktp_masks",
        validation_alias="MASK_OUTPUT_DIR",
    )
    real_predictor_backend: str = Field(
        default="baldness_rf",
        validation_alias="REAL_PREDICTOR_BACKEND",
    )
    baldness_rf_source_root: str | None = Field(
        default=None,
        validation_alias="BALDNESS_RF_SOURCE_ROOT",
    )
    baldness_rf_default_model_path: str | None = Field(
        default=None,
        validation_alias="BALDNESS_RF_DEFAULT_MODEL_PATH",
    )
    baldness_rf_work_dir: str = Field(
        default="/tmp/ktp_baldness_rf",
        validation_alias="BALDNESS_RF_WORK_DIR",
    )
    inference_http_timeout_seconds: float = Field(
        default=600.0,
        validation_alias="INFERENCE_HTTP_TIMEOUT_SECONDS",
    )
    default_prediction_class_semantics_json: str | None = Field(
        default=None,
        validation_alias="DEFAULT_PREDICTION_CLASS_SEMANTICS_JSON",
    )


@lru_cache
def get_inference_service_config() -> InferenceServiceConfig:
    """Return a cached inference service configuration instance."""
    return InferenceServiceConfig()
