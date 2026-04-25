"""Unified chat entrypoint for QA and workflow requests."""

from __future__ import annotations

from fastapi import APIRouter, Depends, Request

from apps.api_gateway.schemas.agent import GatewayAgentResponse
from apps.api_gateway.schemas.chat import ChatRequest
from apps.api_gateway.services.gateway_agent_service import GatewayAgentService

router = APIRouter(tags=["chat"])


async def get_chat_service(request: Request) -> GatewayAgentService:
    """Return the application-scoped chat service."""
    return request.app.state.gateway_agent_service


@router.post("/chat", response_model=GatewayAgentResponse, summary="Unified KTP single-agent chat entrypoint")
async def chat(
    payload: ChatRequest,
    request: Request,
    service: GatewayAgentService = Depends(get_chat_service),
) -> GatewayAgentResponse:
    """Handle a chat request by routing directly into the V2 KTP runtime."""
    return service.handle_chat(payload, public_base_url=str(request.base_url).rstrip("/"))
