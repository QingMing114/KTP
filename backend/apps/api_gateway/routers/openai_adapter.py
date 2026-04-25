"""OpenAI-compatible endpoints for frontend integrations like Open-WebUI."""

import time
import uuid
from typing import Any, List, Optional

from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import BaseModel, Field

from apps.api_gateway.services.gateway_agent_service import GatewayAgentService
from v2.shared.schemas import SessionMessage

router = APIRouter(tags=["openai"])


# Schemas
class OpenAIMessage(BaseModel):
    role: str
    content: str


class OpenAIChatRequest(BaseModel):
    model: str
    messages: List[OpenAIMessage]
    stream: Optional[bool] = False
    temperature: Optional[float] = 0.0
    user: Optional[str] = None


class OpenAIChoice(BaseModel):
    index: int
    message: OpenAIMessage
    finish_reason: str


class OpenAIUsage(BaseModel):
    prompt_tokens: int = 0
    completion_tokens: int = 0
    total_tokens: int = 0


class OpenAIChatResponse(BaseModel):
    id: str
    object: str = "chat.completion"
    created: int
    model: str
    choices: List[OpenAIChoice]
    usage: OpenAIUsage


class OpenAIModelList(BaseModel):
    object: str = "list"
    data: List[dict]


# Dependencies
async def get_chat_service(request: Request) -> GatewayAgentService:
    """Return the application-scoped chat service."""
    return request.app.state.chat_service


# Endpoints
@router.get("/models", response_model=OpenAIModelList, summary="List available models")
async def list_models():
    """Returns a static model list to trick clients into thinking we are an OpenAI server."""
    return OpenAIModelList(
        data=[
            {
                "id": "ktp-multi-agent",
                "object": "model",
                "created": int(time.time()),
                "owned_by": "ktp",
            }
        ]
    )


@router.post("/chat/completions", response_model=OpenAIChatResponse, summary="OpenAI Chat Completion Wrapper")
async def chat_completions(
    req: OpenAIChatRequest,
    request: Request,
    service: GatewayAgentService = Depends(get_chat_service),
):
    """Translate a minimal OpenAI chat completion request into the KTP backend runtime."""
    if req.stream:
        raise HTTPException(status_code=400, detail="stream_not_supported_yet")

    session_messages = [
        SessionMessage(role=msg.role if msg.role in {"user", "assistant", "system"} else "user", content=msg.content)
        for msg in req.messages
        if msg.content.strip()
    ]
    try:
        res = service.handle_openai_chat(
            model=req.model,
            messages=session_messages,
            user_id=req.user,
            conversation_id=None,
            public_base_url=str(request.base_url).rstrip("/"),
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc

    final_output = res.answer
    for artifact in res.artifacts:
        if artifact.uri:
            final_output += f"\n\n[{artifact.title}]({artifact.uri})"

    return OpenAIChatResponse(
        id=f"chatcmpl-{uuid.uuid4().hex[:8]}",
        created=int(time.time()),
        model=req.model,
        choices=[
            OpenAIChoice(
                index=0,
                message=OpenAIMessage(
                    role="assistant",
                    content=final_output,
                ),
                finish_reason="stop",
            )
        ],
        usage=OpenAIUsage(),
    )
