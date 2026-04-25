from __future__ import annotations

from dataclasses import dataclass

from fastapi import FastAPI

from infra.llm.provider import AgentLLMProvider
from v2.agents.registry import AgentProfileRegistry, build_default_agent_registry
from v2.apps.api.config import V2ApiSettings, get_v2_api_settings
from v2.packs.registry import DomainPackRegistry, build_default_pack_registry
from v2.policies.registry import PolicyRegistryV2, build_default_policy_registry
from v2.runtime.engine import BoundedRuntimeEngine
from v2.runtime.factory import build_runtime_store
from v2.runtime.store import RuntimeStore
from v2.tools.registry import ToolRegistryV2, build_default_tool_registry


@dataclass(slots=True)
class BackendRuntimeHost:
    settings: V2ApiSettings
    runtime_store: RuntimeStore
    tool_registry: ToolRegistryV2
    agent_registry: AgentProfileRegistry
    policy_registry: PolicyRegistryV2
    pack_registry: DomainPackRegistry
    runtime_engine: BoundedRuntimeEngine
    llm_provider: AgentLLMProvider | None = None


def build_backend_runtime_host(
    *,
    settings_override: V2ApiSettings | None = None,
    runtime_store_override: RuntimeStore | None = None,
    tool_registry_override: ToolRegistryV2 | None = None,
    agent_registry_override: AgentProfileRegistry | None = None,
    policy_registry_override: PolicyRegistryV2 | None = None,
    pack_registry_override: DomainPackRegistry | None = None,
    llm_provider_override: AgentLLMProvider | None = None,
) -> BackendRuntimeHost:
    resolved_settings = settings_override or get_v2_api_settings()
    runtime_store = runtime_store_override or build_runtime_store(settings=resolved_settings)
    tool_registry = tool_registry_override or build_default_tool_registry()
    agent_registry = agent_registry_override or build_default_agent_registry()
    policy_registry = policy_registry_override or build_default_policy_registry()
    pack_registry = pack_registry_override or build_default_pack_registry()
    runtime_engine = BoundedRuntimeEngine(
        store=runtime_store,
        tool_registry=tool_registry,
        policy_registry=policy_registry,
        agent_registry=agent_registry,
        pack_registry=pack_registry,
        llm_provider=llm_provider_override,
    )
    return BackendRuntimeHost(
        settings=resolved_settings,
        runtime_store=runtime_store,
        tool_registry=tool_registry,
        agent_registry=agent_registry,
        policy_registry=policy_registry,
        pack_registry=pack_registry,
        runtime_engine=runtime_engine,
        llm_provider=llm_provider_override,
    )


def install_backend_runtime_host(app: FastAPI, host: BackendRuntimeHost) -> None:
    app.state.runtime_store = host.runtime_store
    app.state.tool_registry = host.tool_registry
    app.state.agent_registry = host.agent_registry
    app.state.policy_registry = host.policy_registry
    app.state.pack_registry = host.pack_registry
    app.state.runtime_engine = host.runtime_engine
    app.state.agent_llm_provider = host.llm_provider

    from v2.tools.plugin_router import router as plugin_router, set_registry
    set_registry(host.tool_registry)
    app.include_router(plugin_router)

