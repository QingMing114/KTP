"""Configuration for planner/executor local LLM integration."""

from __future__ import annotations

from functools import lru_cache
from pathlib import Path
from typing import Literal

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict

from shared.config.paths import LOGS_DIR

_PROJECT_ROOT = Path(__file__).resolve().parents[2]
_ENV_FILE = _PROJECT_ROOT / ".env"


class AgentLLMConfig(BaseSettings):
    """Runtime configuration for the shared planner/executor LLM."""

    model_config = SettingsConfigDict(
        env_file=str(_ENV_FILE),
        env_file_encoding="utf-8",
        extra="ignore",
    )

    backend: Literal["heuristic", "subprocess_qwen", "openai_compatible"] = Field(
        default="heuristic",
        validation_alias="AGENT_LLM_BACKEND",
    )
    model_path: str | None = Field(
        default=None,
        validation_alias="AGENT_LLM_MODEL_PATH",
    )
    openai_api_base: str = Field(
        default="http://127.0.0.1:8000/v1",
        validation_alias="AGENT_LLM_OPENAI_API_BASE",
    )
    openai_api_key: str = Field(
        default="sk-dummy",
        validation_alias="AGENT_LLM_OPENAI_API_KEY",
    )
    openai_model_name: str = Field(
        default="qwen",
        validation_alias="AGENT_LLM_OPENAI_MODEL_NAME",
    )
    openai_max_retries: int = Field(
        default=2,
        validation_alias="AGENT_LLM_OPENAI_MAX_RETRIES",
    )
    openai_retry_backoff_seconds: float = Field(
        default=1.0,
        validation_alias="AGENT_LLM_OPENAI_RETRY_BACKOFF_SECONDS",
    )
    openai_disable_thinking: bool = Field(
        default=False,
        validation_alias="AGENT_LLM_OPENAI_DISABLE_THINKING",
    )
    runtime_python: str = Field(
        default="python",
        validation_alias="AGENT_LLM_RUNTIME_PYTHON",
    )
    cuda_visible_devices: str | None = Field(
        default=None,
        validation_alias="AGENT_LLM_CUDA_VISIBLE_DEVICES",
    )
    device_map: str = Field(
        default="auto",
        validation_alias="AGENT_LLM_DEVICE_MAP",
    )
    dtype: str = Field(
        default="auto",
        validation_alias="AGENT_LLM_DTYPE",
    )
    max_new_tokens: int = Field(
        default=2048,
        validation_alias="AGENT_LLM_MAX_NEW_TOKENS",
    )
    structured_max_new_tokens: int = Field(
        default=384,
        validation_alias="AGENT_LLM_STRUCTURED_MAX_NEW_TOKENS",
    )
    chat_max_new_tokens: int = Field(
        default=256,
        validation_alias="AGENT_LLM_CHAT_MAX_NEW_TOKENS",
    )
    context_window_tokens: int = Field(
        default=32768,
        validation_alias="AGENT_LLM_CONTEXT_WINDOW_TOKENS",
    )
    context_reserve_output_tokens: int = Field(
        default=2048,
        validation_alias="AGENT_LLM_CONTEXT_RESERVE_OUTPUT_TOKENS",
    )
    context_history_messages: int = Field(
        default=20,
        validation_alias="AGENT_LLM_CONTEXT_HISTORY_MESSAGES",
    )
    context_message_max_chars: int = Field(
        default=300,
        validation_alias="AGENT_LLM_CONTEXT_MESSAGE_MAX_CHARS",
    )
    agent_max_steps: int = Field(
        default=20,
        validation_alias="AGENT_LLM_AGENT_MAX_STEPS",
    )
    request_timeout_seconds: float = Field(
        default=45.0,
        validation_alias="AGENT_LLM_REQUEST_TIMEOUT_SECONDS",
    )
    startup_timeout_seconds: float = Field(
        default=120.0,
        validation_alias="AGENT_LLM_STARTUP_TIMEOUT_SECONDS",
    )
    require_accelerator: bool = Field(
        default=True,
        validation_alias="AGENT_LLM_REQUIRE_ACCELERATOR",
    )
    temperature: float = Field(
        default=0.0,
        validation_alias="AGENT_LLM_TEMPERATURE",
    )
    top_p: float = Field(
        default=0.9,
        validation_alias="AGENT_LLM_TOP_P",
    )
    planner_enabled: bool = Field(
        default=True,
        validation_alias="AGENT_LLM_PLANNER_ENABLED",
    )
    executor_enabled: bool = Field(
        default=True,
        validation_alias="AGENT_LLM_EXECUTOR_ENABLED",
    )
    allow_fallback: bool = Field(
        default=True,
        validation_alias="AGENT_LLM_ALLOW_FALLBACK",
    )
    worker_log_path: str = Field(
        default=str(LOGS_DIR / "ktp_agent_llm_worker.log"),
        validation_alias="AGENT_LLM_WORKER_LOG_PATH",
    )


@lru_cache(maxsize=1)
def get_agent_llm_config() -> AgentLLMConfig:
    """Return cached planner/executor LLM configuration."""
    return AgentLLMConfig()
