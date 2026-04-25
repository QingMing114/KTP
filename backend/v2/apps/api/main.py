"""Compatibility wrapper around the standalone KTP backend API."""

from __future__ import annotations

from fastapi import FastAPI

from infra.llm.provider import AgentLLMProvider
from ktp_backend.api import _encode_sse, create_backend_app, install_backend_api
from v2.apps.api.config import V2ApiSettings


def install_v2_api(
    app: FastAPI,
    *,
    settings_override: V2ApiSettings | None = None,
    include_root_health: bool = True,
    runtime_store_override=None,
    tool_registry_override=None,
    agent_registry_override=None,
    policy_registry_override=None,
    pack_registry_override=None,
    llm_provider_override: AgentLLMProvider | None = None,
) -> None:
    install_backend_api(
        app,
        settings_override=settings_override,
        include_root_health=include_root_health,
        runtime_store_override=runtime_store_override,
        tool_registry_override=tool_registry_override,
        agent_registry_override=agent_registry_override,
        policy_registry_override=policy_registry_override,
        pack_registry_override=pack_registry_override,
        llm_provider_override=llm_provider_override,
    )


def create_app(
    *,
    settings_override: V2ApiSettings | None = None,
    runtime_store_override=None,
    tool_registry_override=None,
    agent_registry_override=None,
    policy_registry_override=None,
    pack_registry_override=None,
    llm_provider_override: AgentLLMProvider | None = None,
) -> FastAPI:
    return create_backend_app(
        settings_override=settings_override,
        runtime_store_override=runtime_store_override,
        tool_registry_override=tool_registry_override,
        agent_registry_override=agent_registry_override,
        policy_registry_override=policy_registry_override,
        pack_registry_override=pack_registry_override,
        llm_provider_override=llm_provider_override,
    )


app = create_app()

__all__ = ["_encode_sse", "app", "create_app", "install_v2_api"]
