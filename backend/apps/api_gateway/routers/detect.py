"""Public detect entrypoint backed by the V2 KTP single-agent runtime."""

from __future__ import annotations

from fastapi import APIRouter, Depends, Request

from apps.api_gateway.schemas.agent import GatewayAgentResponse
from apps.api_gateway.schemas.detect import DetectRequest
from apps.api_gateway.services.gateway_agent_service import GatewayAgentService

router = APIRouter(tags=["detect"])


async def get_gateway_agent_service(request: Request) -> GatewayAgentService:
    """Return the application-scoped gateway agent bridge."""
    return request.app.state.gateway_agent_service


@router.post("/detect", response_model=GatewayAgentResponse, summary="Run the KTP single-agent detect workflow")
async def detect(
    payload: DetectRequest,
    request: Request,
    service: GatewayAgentService = Depends(get_gateway_agent_service),
) -> GatewayAgentResponse:
    """Run one detect request through the V2 KTP agent flow."""
    return service.handle_detect(payload, public_base_url=str(request.base_url).rstrip("/"))
