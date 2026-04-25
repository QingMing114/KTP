"""Visualization routes for rendered workflow dashboards."""

from __future__ import annotations

from pathlib import Path

from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import HTMLResponse

from apps.api_gateway.clients.orchestrator_client import LocalOrchestratorClient
from apps.api_gateway.routers.dependencies import get_orchestrator_client

router = APIRouter(tags=["visualization"])

_ALLOWED_DIRS: list[Path] = [
    Path("/tmp/ktp_visualizations"),
    Path("./data/visualizations"),
    Path("./data/output"),
    Path("./output"),
]


def _validate_path(file_uri: str) -> Path:
    resolved = Path(str(file_uri)).resolve()
    if not any(resolved.is_relative_to(d.resolve()) for d in _ALLOWED_DIRS if d.resolve().exists() or True):
        raise HTTPException(status_code=403, detail="Visualization path outside allowed directories")
    return resolved


@router.get(
    "/workflow/{request_id}/visualization",
    response_class=HTMLResponse,
    summary="Return the rendered workflow dashboard HTML",
)
async def get_workflow_visualization(
    request_id: str,
    client: LocalOrchestratorClient = Depends(get_orchestrator_client),
) -> HTMLResponse:
    """Return the stored visualization HTML for a completed workflow."""
    workflow_response = client.get_workflow(request_id)
    if workflow_response is None:
        return HTMLResponse(
            content=f"<html><body><h1>Visualization not found</h1><p>{request_id}</p></body></html>",
            status_code=404,
        )

    visualization_result = workflow_response.final_state.get("visualization_result") or {}
    html = visualization_result.get("html")
    if isinstance(html, str) and html.strip():
        return HTMLResponse(content=html)

    visualization_uri = visualization_result.get("visualization_uri")
    if not visualization_uri:
        return HTMLResponse(
            content=(
                "<html><body><h1>Visualization unavailable</h1>"
                f"<p>No dashboard was generated for {request_id}.</p></body></html>"
            ),
            status_code=404,
        )

    dashboard_path = _validate_path(visualization_uri)
    if not dashboard_path.exists():
        return HTMLResponse(
            content=(
                "<html><body><h1>Visualization missing</h1>"
                f"<p>Expected dashboard at {dashboard_path}.</p></body></html>"
            ),
            status_code=404,
        )
    return HTMLResponse(content=dashboard_path.read_text(encoding="utf-8"))
