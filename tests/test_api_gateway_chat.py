"""Gateway chat route tests."""

from __future__ import annotations

import asyncio

import httpx

from apps.api_gateway.main import create_app
from apps.api_gateway.schemas.agent import GatewayAgentResponse, GatewayDebugView, GatewayWorkflowView


class _StubChatService:
    def handle_chat(self, request, *, public_base_url: str) -> GatewayAgentResponse:
        return GatewayAgentResponse(
            request_id=request.request_id or "req-chat-route-001",
            conversation_id=request.conversation_id or "conv-chat-route-001",
            session_id=request.conversation_id or "conv-chat-route-001",
            run_id="run-chat-route-001",
            status="completed",
            answer=f"echo:{request.message}",
            artifacts=[],
            sources=["local://source/demo"],
            tool_invocations=[],
            workflow=GatewayWorkflowView(),
            debug=GatewayDebugView(
                session_url=f"{public_base_url}/v2/sessions/conv-chat-route-001",
                run_url=f"{public_base_url}/v2/runs/run-chat-route-001",
                trace_url=f"{public_base_url}/v2/runs/run-chat-route-001/trace",
                replay_url=f"{public_base_url}/v2/runs/run-chat-route-001/replay",
                ui_url=f"{public_base_url}/v2/ui?session_id=conv-chat-route-001&run_id=run-chat-route-001",
            ),
        )


class _StubDirectAnswerLLMProvider:
    def generate_text(self, *, system_prompt: str, user_prompt: str, max_tokens: int | None = None) -> str:
        assert "通用智能体" in system_prompt or "Chat-First Agent" in system_prompt
        assert "你是？" in user_prompt
        assert max_tokens is not None
        return "我是接入共享大模型的通用智能体。"

    def generate_structured(self, *, system_prompt: str, user_prompt: str, response_model):
        assert "chat-first" in system_prompt.lower() or "planner" in system_prompt.lower()
        assert "你是？" in user_prompt
        return response_model.model_validate(
            {
                "action": "reply",
                "reasoning": "Identity question should be answered directly.",
                "response_message": "我是接入共享大模型的通用智能体。",
            }
        )


def test_chat_route_returns_structured_payload() -> None:
    app = create_app(chat_service=_StubChatService())

    async def _run() -> None:
        transport = httpx.ASGITransport(app=app)
        async with httpx.AsyncClient(
            transport=transport,
            base_url="http://testserver",
        ) as client:
            response = await client.post(
                "/chat",
                json={
                    "request_id": "req-chat-route-001",
                    "message": "NDVI 和 EVI 有什么区别？",
                    "mode": "qa",
                    "extra_params": {},
                },
            )
            assert response.status_code == 200
            payload = response.json()
            assert payload["status"] == "completed"
            assert payload["answer"] == "echo:NDVI 和 EVI 有什么区别？"
            assert payload["conversation_id"] == "conv-chat-route-001"
            assert payload["session_id"] == "conv-chat-route-001"
            assert payload["run_id"] == "run-chat-route-001"
            assert payload["sources"] == ["local://source/demo"]
            assert payload["debug"]["ui_url"].endswith(
                "/v2/ui?session_id=conv-chat-route-001&run_id=run-chat-route-001"
            )

    asyncio.run(_run())


def test_chat_route_uses_llm_for_general_direct_answer() -> None:
    app = create_app(llm_provider_override=_StubDirectAnswerLLMProvider())

    async def _run() -> None:
        transport = httpx.ASGITransport(app=app)
        async with httpx.AsyncClient(
            transport=transport,
            base_url="http://testserver",
        ) as client:
            response = await client.post(
                "/chat",
                json={
                    "conversation_id": "conv-direct-answer-001",
                    "message": "你是？",
                    "extra_params": {},
                },
            )
            assert response.status_code == 200
            payload = response.json()
            assert payload["status"] == "completed"
            assert payload["conversation_id"] == "conv-direct-answer-001"
            assert payload["session_id"] == "conv-direct-answer-001"
            assert payload["answer"] == "我是接入共享大模型的通用智能体。"
            assert payload["assistant_message"]["parts"][-1]["text"] == "我是接入共享大模型的通用智能体。"

    asyncio.run(_run())
