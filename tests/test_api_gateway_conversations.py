"""Conversation list/detail route tests."""

from __future__ import annotations

import asyncio
from pathlib import Path

import httpx

from apps.api_gateway.main import create_app
from apps.api_gateway.services.conversation_service import ConversationService
from apps.api_gateway.services.conversation_store import ConversationStore


def _append_demo_turn(
    store: ConversationStore,
    *,
    user_id: str,
    conversation_id: str,
    request_id: str,
    message: str,
    answer: str,
    mode: str = "agent",
) -> None:
    store.append_turn(
        ConversationStore.build_turn(
            user_id=user_id,
            conversation_id=conversation_id,
            request_id=request_id,
            mode=mode,
            route_reason=f"explicit:{mode}",
            success=True,
            user_message=message,
            answer=answer,
            region=None,
            crop_type=None,
            task_type=None,
            image_path=None,
            use_mock=None,
            workflow_status=None,
            sources=[],
            extra_params={},
            context={"history_turn_count": 0},
            response_payload={
                "request_id": request_id,
                "conversation_id": conversation_id,
                "user_id": user_id,
                "mode": mode,
                "route_reason": f"explicit:{mode}",
                "answer": answer,
                "message": "chat completed",
                "success": True,
                "history_turn_count": 0,
                "sources": [],
            },
        )
    )


def test_conversation_routes_filter_by_user_id(tmp_path: Path) -> None:
    store = ConversationStore(db_path=str(tmp_path / "conversation_api.sqlite3"))
    _append_demo_turn(
        store,
        user_id="user-a",
        conversation_id="conv-shared",
        request_id="req-a-001",
        message="NDVI 和 EVI 有什么区别？",
        answer="assistant-a-1",
    )
    _append_demo_turn(
        store,
        user_id="user-a",
        conversation_id="conv-shared",
        request_id="req-a-002",
        message="那高植被覆盖区呢？",
        answer="assistant-a-2",
    )
    _append_demo_turn(
        store,
        user_id="user-b",
        conversation_id="conv-shared",
        request_id="req-b-001",
        message="同一个 conversation id，但不同用户",
        answer="assistant-b-1",
        mode="qa",
    )
    _append_demo_turn(
        store,
        user_id="user-a",
        conversation_id="conv-other",
        request_id="req-a-003",
        message="请分析河南小麦长势",
        answer="assistant-a-3",
        mode="workflow",
    )

    app = create_app()
    app.state.conversation_service = ConversationService(conversation_store=store)

    async def _run() -> None:
        transport = httpx.ASGITransport(app=app)
        async with httpx.AsyncClient(
            transport=transport,
            base_url="http://testserver",
        ) as client:
            list_response = await client.get("/chat/conversations", params={"user_id": "user-a"})
            assert list_response.status_code == 200
            list_payload = list_response.json()
            assert list_payload["user_id"] == "user-a"
            assert [item["conversation_id"] for item in list_payload["conversations"]] == [
                "conv-other",
                "conv-shared",
            ]

            detail_response = await client.get(
                "/chat/conversations/conv-shared",
                params={"user_id": "user-a"},
            )
            assert detail_response.status_code == 200
            detail_payload = detail_response.json()
            assert detail_payload["user_id"] == "user-a"
            assert detail_payload["conversation_id"] == "conv-shared"
            assert len(detail_payload["messages"]) == 4
            assert detail_payload["messages"][0]["role"] == "user"
            assert detail_payload["messages"][1]["role"] == "assistant"
            assert detail_payload["messages"][1]["response_payload"]["answer"] == "assistant-a-1"

            other_user_response = await client.get(
                "/chat/conversations/conv-shared",
                params={"user_id": "user-b"},
            )
            assert other_user_response.status_code == 200
            other_user_payload = other_user_response.json()
            assert len(other_user_payload["messages"]) == 2
            assert other_user_payload["messages"][0]["content"] == "同一个 conversation id，但不同用户"

    asyncio.run(_run())
