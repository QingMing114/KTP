from __future__ import annotations

import os
from pathlib import Path

from infra.llm.config import AgentLLMConfig
from shared.config.settings import Settings
from shared.config.paths import project_root, var_path


def test_agent_llm_config_loads_product_env_even_when_cwd_changes(
    tmp_path: Path,
    monkeypatch,
) -> None:
    monkeypatch.delenv("AGENT_LLM_BACKEND", raising=False)
    monkeypatch.delenv("AGENT_LLM_OPENAI_API_BASE", raising=False)
    previous_cwd = Path.cwd()
    try:
        os.chdir(tmp_path)
        config = AgentLLMConfig()
    finally:
        os.chdir(previous_cwd)

    assert config.backend == "openai_compatible"
    assert config.openai_api_base == "http://127.0.0.1:8000/v1"


def test_shared_settings_load_product_env_even_when_cwd_changes(
    tmp_path: Path,
    monkeypatch,
) -> None:
    monkeypatch.delenv("APP_PORT", raising=False)
    monkeypatch.delenv("DATABASE_URL", raising=False)
    previous_cwd = Path.cwd()
    try:
        os.chdir(tmp_path)
        settings = Settings()
    finally:
        os.chdir(previous_cwd)

    assert settings.app_port == 18080
    assert settings.database_url == f"sqlite:///{var_path('runtime', 'product.db')}"
    assert project_root() == Path(__file__).resolve().parents[1]
