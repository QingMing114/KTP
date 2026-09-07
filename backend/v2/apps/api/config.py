from __future__ import annotations

from functools import lru_cache
from typing import ClassVar

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict

from shared.config.paths import DATA_DIR


class V2ApiSettings(BaseSettings):
    """Settings for the V2 API surface."""

    model_config = SettingsConfigDict(
        env_prefix="V2_API_",
        env_file=".env",
        extra="ignore",
    )

    title: str = Field(default="KTP V2 Platform")
    version: str = Field(default="0.1.0")
    host: str = Field(default="0.0.0.0")
    port: int = Field(default=18180)
    log_level: str = Field(default="INFO")
    store_backend: str = Field(default="memory")
    sqlite_path: str = Field(default=str(DATA_DIR / "ktp_v2_runtime.sqlite3"))
    cors_allow_origins: str = Field(default="*")
    memory_dir: str | None = Field(
        default=None,
        description="Directory containing MEMORY.md and the Markdown documents available for read-only retrieval.",
    )
    memory_top_k: int = Field(default=5, ge=1, le=20)
    memory_max_chars: int = Field(default=2_000, ge=200, le=12_000)
    memory_auto_write_enabled: bool = Field(
        default=False,
        description="Whether completed conversations may create memory facts. Keep disabled for document retrieval.",
    )

    @property
    def cors_origins_list(self) -> list[str]:
        origins = [origin.strip() for origin in self.cors_allow_origins.split(",") if origin.strip()]
        return origins or ["*"]


@lru_cache(maxsize=1)
def get_v2_api_settings() -> V2ApiSettings:
    return V2ApiSettings()
