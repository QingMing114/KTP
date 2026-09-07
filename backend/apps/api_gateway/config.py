"""Runtime settings for API gateway local integrations."""

from __future__ import annotations

from functools import lru_cache

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict

from shared.config.paths import DATA_DIR


class APIGatewayConfig(BaseSettings):
    """Settings used by the gateway chat and conversation integrations."""

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    conversation_db_path: str = Field(
        default=str(DATA_DIR / "ktp_gateway_conversations.sqlite3"),
        validation_alias="API_GATEWAY_CONVERSATION_DB_PATH",
    )
    conversation_history_limit: int = Field(
        default=6,
        validation_alias="API_GATEWAY_CONVERSATION_HISTORY_LIMIT",
    )
    chat_agent_runtime_enabled: bool = Field(
        default=True,
        validation_alias="API_GATEWAY_CHAT_AGENT_RUNTIME_ENABLED",
    )
    chat_agent_shadow_compare_enabled: bool = Field(
        default=False,
        validation_alias="API_GATEWAY_CHAT_AGENT_SHADOW_COMPARE_ENABLED",
    )
    chat_agent_legacy_fallback_enabled: bool = Field(
        default=True,
        validation_alias="API_GATEWAY_CHAT_AGENT_LEGACY_FALLBACK_ENABLED",
    )
    chat_agent_max_replans: int = Field(
        default=1,
        validation_alias="API_GATEWAY_CHAT_AGENT_MAX_REPLANS",
    )


@lru_cache(maxsize=1)
def get_api_gateway_config() -> APIGatewayConfig:
    """Return a cached API gateway configuration instance."""
    return APIGatewayConfig()
