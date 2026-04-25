"""Dependency wiring for the bounded chat agent runtime."""

from __future__ import annotations

from functools import lru_cache

from agents.core_70b.chat_planner import ChatPlanner
from agents.executor_30b.chat_executor import ChatExecutor
from apps.api_gateway.clients.orchestrator_client import LocalOrchestratorClient
from infra.llm.config import get_agent_llm_config
from infra.llm.provider import get_agent_llm_provider
from services.rag_service.client import LocalRAGServiceClient


@lru_cache(maxsize=1)
def get_chat_runtime_planner() -> ChatPlanner:
    """Return the bounded 70B chat planner."""
    config = get_agent_llm_config()
    llm_provider = get_agent_llm_provider() if config.planner_enabled else None
    return ChatPlanner(llm_provider=llm_provider)


@lru_cache(maxsize=1)
def get_chat_runtime_executor() -> ChatExecutor:
    """Return the bounded 30B chat executor."""
    config = get_agent_llm_config()
    llm_provider = get_agent_llm_provider() if config.executor_enabled else None
    return ChatExecutor(llm_provider=llm_provider)


@lru_cache(maxsize=1)
def get_chat_runtime_rag_client() -> LocalRAGServiceClient:
    """Return the local RAG client used by chat runtime tool dispatch."""
    return LocalRAGServiceClient()


@lru_cache(maxsize=1)
def get_chat_runtime_orchestrator_client() -> LocalOrchestratorClient:
    """Return the local orchestrator client used by chat runtime tool dispatch."""
    return LocalOrchestratorClient()
