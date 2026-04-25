"""State definitions for the self-scheduling chat runtime."""

from __future__ import annotations

from typing import TypedDict


class ChatRuntimeState(TypedDict, total=False):
    """Mutable state carried across chat-runtime graph nodes."""

    request_id: str
    user_id: str
    conversation_id: str
    user_message: str
    conversation_history: str
    region: str | None
    crop_type: str | None
    task_type: str | None
    available_tools: list[dict]
    planner_decision: dict | None
    current_step: dict | None
    executor_action: dict | None
    tool_observation: dict | None
    final_answer: str | None
    final_mode: str | None
    workflow_status: str | None
    replan_count: int
    max_replans: int
    runtime_trace: list[dict]
    errors: list[str]
    status: str


def create_initial_chat_state(
    *,
    request_id: str,
    user_id: str,
    conversation_id: str,
    user_message: str,
    conversation_history: str = "",
    region: str | None = None,
    crop_type: str | None = None,
    task_type: str | None = None,
    max_replans: int = 1,
) -> ChatRuntimeState:
    """Build the initial state for the future chat graph runtime."""
    return ChatRuntimeState(
        request_id=request_id,
        user_id=user_id,
        conversation_id=conversation_id,
        user_message=user_message,
        conversation_history=conversation_history,
        region=region,
        crop_type=crop_type,
        task_type=task_type,
        available_tools=[],
        planner_decision=None,
        current_step=None,
        executor_action=None,
        tool_observation=None,
        final_answer=None,
        final_mode=None,
        workflow_status=None,
        replan_count=0,
        max_replans=max_replans,
        runtime_trace=[],
        errors=[],
        status="received",
    )
