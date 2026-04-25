"""Integration tests for the gateway-hosted KTP chat route."""

from __future__ import annotations

import asyncio

import httpx


def test_gateway_chat_route_supports_knowledge_and_analysis(
    integration_runtime: dict[str, object],
) -> None:
    app = integration_runtime["gateway_app"]

    async def _run() -> None:
        transport = httpx.ASGITransport(app=app)
        async with httpx.AsyncClient(
            transport=transport,
            base_url="http://testserver",
        ) as client:
            qa_response = await client.post(
                "/chat",
                json={
                    "request_id": "req-chat-int-qa-001",
                    "message": "请概述河南小麦监测中常见的干旱和病害因素。",
                    "extra_params": {},
                },
            )
            assert qa_response.status_code == 200
            qa_payload = qa_response.json()
            assert qa_payload["status"] == "completed"
            assert qa_payload["conversation_id"]
            assert qa_payload["workflow"]["knowledge_result"] is not None
            assert qa_payload["sources"]
            assert qa_payload["answer"]

            workflow_response = await client.post(
                "/chat",
                json={
                    "request_id": "req-chat-int-wf-001",
                    "message": "请分析河南小麦长势，并生成报告和置信度说明。",
                    "region": "henan",
                    "crop_type": "wheat",
                    "use_mock": True,
                    "extra_params": {},
                },
            )
            assert workflow_response.status_code == 200
            workflow_payload = workflow_response.json()
            assert workflow_payload["status"] == "completed"
            assert workflow_payload["conversation_id"]
            assert workflow_payload["workflow"]["report_result"] is not None
            assert workflow_payload["workflow"]["confidence_result"] is not None
            assert workflow_payload["workflow"]["visualization_result"] is None
            assert workflow_payload["answer"]

    asyncio.run(_run())


def test_gateway_chat_route_inherits_workflow_context_from_conversation(
    integration_runtime: dict[str, object],
) -> None:
    app = integration_runtime["gateway_app"]

    async def _run() -> None:
        transport = httpx.ASGITransport(app=app)
        async with httpx.AsyncClient(
            transport=transport,
            base_url="http://testserver",
        ) as client:
            first_response = await client.post(
                "/chat",
                json={
                    "request_id": "req-chat-int-followup-001",
                    "message": "请分析河南小麦长势，并生成报告和可视化。",
                    "region": "henan",
                    "crop_type": "wheat",
                    "use_mock": True,
                    "extra_params": {},
                },
            )
            assert first_response.status_code == 200
            first_payload = first_response.json()
            assert first_payload["status"] == "completed"
            conversation_id = first_payload["conversation_id"]

            second_response = await client.post(
                "/chat",
                json={
                    "request_id": "req-chat-int-followup-002",
                    "conversation_id": conversation_id,
                    "message": "那再来一次，并保留可视化",
                    "extra_params": {},
                },
            )
            assert second_response.status_code == 200
            second_payload = second_response.json()
            assert second_payload["status"] == "completed"
            assert second_payload["conversation_id"] == conversation_id
            assert second_payload["session_id"] == conversation_id
            assert second_payload["workflow"]["report_result"] is not None
            assert second_payload["workflow"]["confidence_result"] is not None
            assert second_payload["workflow"]["visualization_result"] is not None
            assert second_payload["debug"]["ui_url"].endswith(
                f"/v2/ui?session_id={conversation_id}&run_id={second_payload['run_id']}"
            )

    asyncio.run(_run())
