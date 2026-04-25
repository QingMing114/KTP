"""Integration test for the gateway detect route and orchestrator client."""

from __future__ import annotations

import asyncio
import httpx


def test_gateway_detect_route_returns_structured_result(
    integration_runtime: dict[str, object],
) -> None:
    app = integration_runtime["gateway_app"]

    async def _run() -> None:
        transport = httpx.ASGITransport(app=app)
        async with httpx.AsyncClient(
            transport=transport,
            base_url="http://testserver",
        ) as client:
            response = await client.post(
                "/detect",
                json={
                    "request_id": "req-gateway-001",
                    "user_query": "Assess wheat health in Henan and provide a report with confidence.",
                    "region": "henan",
                    "crop_type": "wheat",
                    "task_type": "crop_health_detection",
                    "use_mock": True,
                    "extra_params": {},
                },
            )
            assert response.status_code == 200
            payload = response.json()
            assert payload["status"] == "completed"
            assert payload["workflow"]["report_result"] is not None
            assert payload["workflow"]["confidence_result"] is not None
            assert payload["workflow"]["visualization_result"] is not None

            run_response = await client.get(payload["debug"]["run_url"].replace("http://testserver", ""))
            assert run_response.status_code == 200
            assert run_response.json()["run_id"] == payload["run_id"]

            trace_response = await client.get(payload["debug"]["trace_url"].replace("http://testserver", ""))
            assert trace_response.status_code == 200
            assert len(trace_response.json()) >= 3

    asyncio.run(_run())
