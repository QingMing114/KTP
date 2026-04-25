"""Conversation list/detail APIs for the chat UI."""

from __future__ import annotations

from fastapi import APIRouter, Depends, Query, Request

from apps.api_gateway.schemas.conversation import (
    ConversationDetailResponse,
    ConversationListResponse,
)
from apps.api_gateway.services.conversation_service import ConversationService

router = APIRouter(tags=["chat-conversations"])


async def get_conversation_service(request: Request) -> ConversationService:
    """Return the application-scoped conversation service."""
    return request.app.state.conversation_service


@router.get(
    "/chat/conversations",
    response_model=ConversationListResponse,
    summary="List recent conversations for one user",
)
async def list_conversations(
    user_id: str = Query(default="anonymous", description="User identifier for isolation."),
    limit: int = Query(default=50, ge=1, le=200, description="Maximum conversation count."),
    service: ConversationService = Depends(get_conversation_service),
) -> ConversationListResponse:
    """Return recent conversation summaries for one user."""
    return service.list_conversations(user_id=user_id, limit=limit)


@router.get(
    "/chat/conversations/{conversation_id}",
    response_model=ConversationDetailResponse,
    summary="Get one conversation timeline for one user",
)
async def get_conversation(
    conversation_id: str,
    user_id: str = Query(default="anonymous", description="User identifier for isolation."),
    service: ConversationService = Depends(get_conversation_service),
) -> ConversationDetailResponse:
    """Return one conversation detail timeline for one user."""
    return service.get_conversation(user_id=user_id, conversation_id=conversation_id)
