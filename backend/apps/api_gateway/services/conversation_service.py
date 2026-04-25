"""Conversation listing and detail service for the chat UI."""

from __future__ import annotations

import logging

from apps.api_gateway.schemas.conversation import (
    ConversationDetailResponse,
    ConversationListResponse,
    ConversationMessageItem,
    ConversationSummaryItem,
)
from apps.api_gateway.services.conversation_store import (
    ConversationStore,
    ConversationStoreError,
    ConversationTurn,
)

logger = logging.getLogger(__name__)


class ConversationService:
    """Read chat conversations from the shared conversation store."""

    def __init__(self, *, conversation_store: ConversationStore) -> None:
        self._conversation_store = conversation_store

    def list_conversations(
        self,
        *,
        user_id: str,
        limit: int = 50,
    ) -> ConversationListResponse:
        """Return recent conversation summaries for one user."""
        resolved_user_id = user_id.strip() or "anonymous"
        logger.info(
            "conversation_service_list_started | user_id=%s | limit=%s",
            resolved_user_id,
            limit,
        )
        summaries = self._conversation_store.list_conversations(
            user_id=resolved_user_id,
            limit=limit,
        )
        response = ConversationListResponse(
            user_id=resolved_user_id,
            conversations=[
                ConversationSummaryItem(
                    user_id=item.user_id,
                    conversation_id=item.conversation_id,
                    title=item.title,
                    created_at=item.created_at,
                    updated_at=item.updated_at,
                    turn_count=item.turn_count,
                    last_mode=item.last_mode,
                    workflow_status=item.workflow_status,
                    last_request_id=item.last_request_id,
                    last_message_preview=item.last_message_preview,
                )
                for item in summaries
            ],
        )
        logger.info(
            "conversation_service_list_succeeded | user_id=%s | conversation_count=%s",
            resolved_user_id,
            len(response.conversations),
        )
        return response

    def get_conversation(
        self,
        *,
        user_id: str,
        conversation_id: str,
    ) -> ConversationDetailResponse:
        """Return one conversation timeline for one user."""
        resolved_user_id = user_id.strip() or "anonymous"
        logger.info(
            "conversation_service_detail_started | user_id=%s | conversation_id=%s",
            resolved_user_id,
            conversation_id,
        )
        turns = self._conversation_store.get_all_turns(
            user_id=resolved_user_id,
            conversation_id=conversation_id,
        )
        title = self._build_title(turns)
        response = ConversationDetailResponse(
            user_id=resolved_user_id,
            conversation_id=conversation_id,
            title=title,
            messages=self._build_messages(turns),
        )
        logger.info(
            "conversation_service_detail_succeeded | user_id=%s | conversation_id=%s | message_count=%s",
            resolved_user_id,
            conversation_id,
            len(response.messages),
        )
        return response

    @staticmethod
    def _build_title(turns: list[ConversationTurn]) -> str:
        if not turns:
            return "未命名会话"
        content = " ".join(turns[0].user_message.split())
        if not content:
            return "未命名会话"
        return content[:24] + ("…" if len(content) > 24 else "")

    @staticmethod
    def _build_messages(turns: list[ConversationTurn]) -> list[ConversationMessageItem]:
        messages: list[ConversationMessageItem] = []
        for turn in turns:
            messages.append(
                ConversationMessageItem(
                    role="user",
                    content=turn.user_message,
                    request_id=turn.request_id,
                    created_at=turn.created_at,
                    mode=turn.mode,
                    route_reason=turn.route_reason,
                    workflow_status=turn.workflow_status,
                    response_payload=None,
                )
            )
            messages.append(
                ConversationMessageItem(
                    role="assistant",
                    content=turn.answer,
                    request_id=turn.request_id,
                    created_at=turn.created_at,
                    mode=turn.mode,
                    route_reason=turn.route_reason,
                    workflow_status=turn.workflow_status,
                    response_payload=turn.response_payload,
                )
            )
        return messages


__all__ = ["ConversationService", "ConversationStoreError"]
