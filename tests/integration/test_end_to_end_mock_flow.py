"""End-to-end style mock-path validation through the gateway."""

from __future__ import annotations

import asyncio
import httpx


def test_gateway_services_health_and_mock_flow(
    integration_runtime: dict[str, object],
) -> None:
    app = integration_runtime["gateway_app"]

    async def _run() -> None:
        transport = httpx.ASGITransport(app=app)
        async with httpx.AsyncClient(
            transport=transport,
            base_url="http://testserver",
        ) as client:
            health_response = await client.get("/services/health")
            assert health_response.status_code == 200
            assert health_response.json()["success"] is True
            assert "model_registry" in health_response.json()["services"]
            assert "visualization_service" in health_response.json()["services"]

            detect_response = await client.post(
                "/detect",
                json={
                    "request_id": "req-e2e-mock-001",
                    "user_query": "Assess wheat health in Henan and provide a report with confidence.",
                    "region": "henan",
                    "crop_type": "wheat",
                    "task_type": "crop_health_detection",
                    "use_mock": True,
                    "extra_params": {},
                },
            )
            assert detect_response.status_code == 200
            payload = detect_response.json()
            assert payload["status"] == "completed"
            assert payload["workflow"]["inference_result"] is not None
            assert payload["workflow"]["knowledge_result"] is not None
            assert payload["workflow"]["report_result"] is not None
            assert payload["workflow"]["confidence_result"] is not None
            assert payload["workflow"]["visualization_result"] is not None
            assert payload["debug"]["ui_url"].endswith(
                f"/v2/ui?session_id={payload['session_id']}&run_id={payload['run_id']}"
            )

    asyncio.run(_run())
