"""Gateway UI and report route tests."""

from __future__ import annotations

import asyncio
from pathlib import Path

import httpx

from apps.api_gateway.main import create_app
from apps.api_gateway.routers.v2_artifacts import open_v2_artifact
from shared.schemas.orchestrator import WorkflowResponse


class _StubOrchestratorClient:
    def __init__(self, *, report_path: str | None = None) -> None:
        self._report_path = report_path

    def get_workflow(self, request_id: str) -> WorkflowResponse | None:
        if self._report_path is None:
            return None
        return WorkflowResponse(
            request_id=request_id,
            status="completed",
            final_state={
                "report_result": {
                    "report_uri": self._report_path,
                },
            },
        )


def test_chat_ui_route_redirects_to_v2_ui() -> None:
    app = create_app(chat_service=None)

    async def _run() -> None:
        transport = httpx.ASGITransport(app=app)
        async with httpx.AsyncClient(
            transport=transport,
            base_url="http://testserver",
            follow_redirects=False,
        ) as client:
            response = await client.get("/chat/ui")
            assert response.status_code == 307
            assert response.headers["location"] == "/v2/ui"

    asyncio.run(_run())


def test_v2_ui_route_renders_html() -> None:
    app = create_app(chat_service=None)

    async def _run() -> None:
        transport = httpx.ASGITransport(app=app)
        async with httpx.AsyncClient(
            transport=transport,
            base_url="http://testserver",
        ) as client:
            response = await client.get("/v2/ui")
            assert response.status_code == 200
            assert "KTP 智能体" in response.text
            assert "/v2/ui/dist/main.js" in response.text

    asyncio.run(_run())


def test_report_route_returns_rendered_report_html(tmp_path: Path) -> None:
    report_path = tmp_path / "demo-report.html"
    report_path.write_text("<html><body><h1>示例报告</h1></body></html>", encoding="utf-8")
    app = create_app(orchestrator_client=_StubOrchestratorClient(report_path=str(report_path)))

    async def _run() -> None:
        transport = httpx.ASGITransport(app=app)
        async with httpx.AsyncClient(
            transport=transport,
            base_url="http://testserver",
        ) as client:
            response = await client.get("/workflow/req-report-001/report")
            assert response.status_code == 200
            assert "示例报告" in response.text

    asyncio.run(_run())


def test_v2_artifact_open_route_returns_local_html(tmp_path: Path) -> None:
    artifact_path = tmp_path / "artifact-dashboard.html"
    artifact_path.write_text("<html><body><h1>Artifact Ready</h1></body></html>", encoding="utf-8")

    async def _run() -> None:
        response = await open_v2_artifact(path=str(artifact_path))
        assert response.path == str(artifact_path)
        assert response.media_type == "text/html"

    asyncio.run(_run())
