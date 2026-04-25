"""Shared FastAPI dependency injection functions for API gateway routers."""

from __future__ import annotations

from fastapi import Request

from apps.api_gateway.clients.orchestrator_client import LocalOrchestratorClient


async def get_orchestrator_client(request: Request) -> LocalOrchestratorClient:
    """Return the application-scoped orchestrator client."""
    return request.app.state.orchestrator_client
