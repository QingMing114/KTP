"""Configuration for the HTML report service."""

from __future__ import annotations

from functools import lru_cache
from pathlib import Path

from pydantic import Field, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

from shared.config.paths import REPORTS_DIR


def _default_template_dir() -> str:
    return str(Path(__file__).resolve().parent / "templates")


class ReportServiceConfig(BaseSettings):
    """Settings used by the report generation service."""

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    report_service_name: str = Field(
        default="report-service",
        validation_alias="REPORT_SERVICE_NAME",
    )
    report_output_dir: str = Field(
        default=str(REPORTS_DIR),
        validation_alias="REPORT_OUTPUT_DIR",
    )
    report_template_dir: str = Field(
        default_factory=_default_template_dir,
        validation_alias="REPORT_TEMPLATE_DIR",
    )
    embed_html_in_response: bool = Field(
        default=True,
        validation_alias="EMBED_HTML_IN_RESPONSE",
    )
    generate_charts: bool = Field(
        default=True,
        validation_alias="GENERATE_CHARTS",
    )

    @field_validator("report_template_dir", mode="before")
    @classmethod
    def _normalize_template_dir(cls, value: str | None) -> str:
        if value is None or not str(value).strip():
            return _default_template_dir()
        return str(value)


@lru_cache(maxsize=1)
def get_report_service_config() -> ReportServiceConfig:
    """Return the cached report service configuration."""
    return ReportServiceConfig()
