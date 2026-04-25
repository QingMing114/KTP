"""Schemas for chat conversation listing and detail APIs."""

from __future__ import annotations

from typing import Any, Literal

from pydantic import Field

from shared.schemas.common import BaseSchema


class ConversationSummaryItem(BaseSchema):
    """Compact conversation summary used by the chat UI sidebar."""

    user_id: str = Field(..., description="Conversation owner identifier.")
    conversation_id: str = Field(..., description="Stable conversation identifier.")
    title: str = Field(..., description="Display title derived from the first message.")
    created_at: str = Field(..., description="Conversation creation timestamp.")
    updated_at: str = Field(..., description="Latest turn timestamp.")
    turn_count: int = Field(..., description="Persisted turn count.")
    last_mode: Literal["agent", "qa", "workflow"] | str = Field(
        ...,
        description="Mode of the latest persisted turn.",
    )
    workflow_status: str | None = Field(
        default=None,
        description="Latest workflow status when applicable.",
    )
    last_request_id: str = Field(..., description="Latest request identifier.")
    last_message_preview: str = Field(..., description="Compact preview of the latest user prompt.")


class ConversationMessageItem(BaseSchema):
    """One normalized message entry for rendering a conversation timeline."""

    role: Literal["user", "assistant"] = Field(..., description="Timeline role.")
    content: str = Field(..., description="Rendered message content.")
    request_id: str = Field(..., description="Associated request identifier.")
    created_at: str = Field(..., description="Turn creation timestamp.")
    mode: Literal["agent", "qa", "workflow"] | str = Field(
        ...,
        description="Mode associated with the persisted turn.",
    )
    route_reason: str = Field(..., description="Gateway route reason for the turn.")
    workflow_status: str | None = Field(
        default=None,
        description="Workflow status when available.",
    )
    response_payload: dict[str, Any] | None = Field(
        default=None,
        description="Structured assistant payload; empty for user role.",
    )


class ConversationListResponse(BaseSchema):
    """List of recent conversations belonging to one user."""

    user_id: str = Field(..., description="Resolved user identifier.")
    conversations: list[ConversationSummaryItem] = Field(
        default_factory=list,
        description="Recent conversations ordered by latest activity.",
    )


class ConversationDetailResponse(BaseSchema):
    """Full message timeline for a conversation."""

    user_id: str = Field(..., description="Resolved user identifier.")
    conversation_id: str = Field(..., description="Stable conversation identifier.")
    title: str = Field(..., description="Display title derived from the first message.")
    messages: list[ConversationMessageItem] = Field(
        default_factory=list,
        description="Normalized user/assistant timeline.",
    )
