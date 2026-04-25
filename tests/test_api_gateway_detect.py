"""Gateway detect route tests."""

from __future__ import annotations

import asyncio

import httpx

from apps.api_gateway.main import create_app
from apps.api_gateway.schemas.agent import GatewayAgentResponse, GatewayDebugView, GatewayWorkflowView


class _StubGatewayAgentService:
    def handle_chat(self, request, *, public_base_url: str) -> GatewayAgentResponse:
        del request, public_base_url
        raise AssertionError("chat path should not be used in detect tests")

    def handle_detect(self, request, *, public_base_url: str) -> GatewayAgentResponse:
        return GatewayAgentResponse(
            request_id=request.request_id,
            conversation_id="conv-detect-001",
            session_id="session-detect-001",
            run_id="run-detect-001",
            status="failed",
            answer="registry connection failed",
            artifacts=[],
            sources=[],
            tool_invocations=[],
            workflow=GatewayWorkflowView(),
            debug=GatewayDebugView(
                session_url=f"{public_base_url}/v2/sessions/session-detect-001",
                run_url=f"{public_base_url}/v2/runs/run-detect-001",
                trace_url=f"{public_base_url}/v2/runs/run-detect-001/trace",
                replay_url=f"{public_base_url}/v2/runs/run-detect-001/replay",
                ui_url=f"{public_base_url}/v2/ui?session_id=session-detect-001&run_id=run-detect-001",
            ),
        )


def test_detect_returns_gateway_agent_response() -> None:
    app = create_app(chat_service=_StubGatewayAgentService())

    async def _run() -> None:
        transport = httpx.ASGITransport(app=app)
        async with httpx.AsyncClient(
            transport=transport,
            base_url="http://testserver",
        ) as client:
            response = await client.post(
                "/detect",
                json={
                    "request_id": "req-detect-fail-001",
                    "user_query": "Assess wheat health in Henan.",
                    "region": "henan",
                    "crop_type": "wheat",
                    "task_type": "crop_health_detection",
                    "use_mock": False,
                    "extra_params": {},
                },
            )
            assert response.status_code == 200
            payload = response.json()
            assert payload["status"] == "failed"
            assert payload["answer"] == "registry connection failed"
            assert payload["session_id"] == "session-detect-001"
            assert payload["run_id"] == "run-detect-001"
            assert payload["workflow"]["inference_result"] is None
            assert payload["debug"]["trace_url"].endswith("/v2/runs/run-detect-001/trace")

    asyncio.run(_run())
