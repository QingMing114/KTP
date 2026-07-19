"""Centralized application settings."""

from __future__ import annotations

from functools import lru_cache
from pathlib import Path

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict

_PROJECT_ROOT = Path(__file__).resolve().parents[2]
_ENV_FILE = _PROJECT_ROOT / ".env"


class Settings(BaseSettings):
    """Runtime settings loaded from environment variables or `.env`."""

    model_config = SettingsConfigDict(
        env_file=str(_ENV_FILE),
        env_file_encoding="utf-8",
        extra="ignore",
    )

    app_name: str = Field(
        default="remote-sensing-multi-agent",
        validation_alias="APP_NAME",
    )
    app_env: str = Field(default="development", validation_alias="APP_ENV")
    app_host: str = Field(default="0.0.0.0", validation_alias="APP_HOST")
    app_port: int = Field(default=18080, validation_alias="APP_PORT")
    log_level: str = Field(default="INFO", validation_alias="LOG_LEVEL")
    database_url: str = Field(
        default="postgresql://postgres:postgres@localhost:5432/remote_sensing",
        validation_alias="DATABASE_URL",
    )
    redis_url: str = Field(
        default="redis://localhost:6379/0",
        validation_alias="REDIS_URL",
    )

    app_auth_enabled: bool = Field(default=False, validation_alias="APP_AUTH_ENABLED")
    app_auth_token: str = Field(default="", validation_alias="APP_AUTH_TOKEN")
    app_cors_origins: str = Field(default="", validation_alias="APP_CORS_ORIGINS")
    app_rate_limit: int = Field(default=300, validation_alias="APP_RATE_LIMIT")
    app_rate_window: int = Field(default=60, validation_alias="APP_RATE_WINDOW")
    app_max_request_body_mb: int = Field(default=10, validation_alias="APP_MAX_REQUEST_BODY_MB")

    temporal_server_url: str | None = Field(
        default=None,
        validation_alias="TEMPORAL_SERVER_URL",
    )
    openai_api_key: str | None = Field(
        default=None,
        validation_alias="OPENAI_API_KEY",
    )
    model_registry_url: str | None = Field(
        default=None,
        validation_alias="MODEL_REGISTRY_URL",
    )

    ktp_default_region: str = Field(default="henan", validation_alias="KTP_DEFAULT_REGION")
    ktp_default_crop_type: str = Field(default="wheat", validation_alias="KTP_DEFAULT_CROP_TYPE")
    ktp_default_task_type: str = Field(default="crop_health_detection", validation_alias="KTP_DEFAULT_TASK_TYPE")
    agent_max_steps: int = Field(default=20, validation_alias="AGENT_MAX_STEPS")
    agent_duplicate_call_threshold: int = Field(default=2, validation_alias="AGENT_DUPLICATE_CALL_THRESHOLD")

    @property
    def get_cors_origins(self) -> list[str]:
        if not self.app_cors_origins:
            return ["*"]
        return [o.strip() for o in self.app_cors_origins.split(",") if o.strip()]


@lru_cache
def get_settings() -> Settings:
    """Return a cached settings instance."""
    return Settings()


settings = get_settings()
