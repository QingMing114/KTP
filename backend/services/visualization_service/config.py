"""Configuration for the workflow visualization service."""

from __future__ import annotations

from functools import lru_cache
from pathlib import Path

from pydantic import Field, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

from shared.config.paths import VISUALIZATIONS_DIR


def _default_template_dir() -> str:
    return str(Path(__file__).resolve().parent / "templates")


class VisualizationServiceConfig(BaseSettings):
    """Settings used by the workflow visualization service."""

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    visualization_service_name: str = Field(
        default="visualization-service",
        validation_alias="VISUALIZATION_SERVICE_NAME",
    )
    visualization_output_dir: str = Field(
        default=str(VISUALIZATIONS_DIR),
        validation_alias="VISUALIZATION_OUTPUT_DIR",
    )
    visualization_template_dir: str = Field(
        default_factory=_default_template_dir,
        validation_alias="VISUALIZATION_TEMPLATE_DIR",
    )
    visualization_embed_html_in_response: bool = Field(
        default=False,
        validation_alias="VISUALIZATION_EMBED_HTML_IN_RESPONSE",
    )

    @field_validator("visualization_template_dir", mode="before")
    @classmethod
    def _normalize_template_dir(cls, value: str | None) -> str:
        if value is None or not str(value).strip():
            return _default_template_dir()
        return str(value)


@lru_cache(maxsize=1)
def get_visualization_service_config() -> VisualizationServiceConfig:
    """Return the cached visualization service configuration."""
    return VisualizationServiceConfig()
