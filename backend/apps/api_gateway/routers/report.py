"""Report routes for rendered workflow reports."""

from __future__ import annotations

from pathlib import Path

from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import HTMLResponse

from apps.api_gateway.clients.orchestrator_client import LocalOrchestratorClient
from apps.api_gateway.routers.dependencies import get_orchestrator_client

router = APIRouter(tags=["report"])

_ALLOWED_DIRS: list[Path] = [
    Path("/tmp/ktp_reports"),
    Path("./data/reports"),
    Path("./data/output"),
    Path("./output"),
]


def _validate_path(file_uri: str) -> Path:
    resolved = Path(str(file_uri)).resolve()
    if not any(resolved.is_relative_to(d.resolve()) for d in _ALLOWED_DIRS if d.resolve().exists() or True):
        raise HTTPException(status_code=403, detail="Report path outside allowed directories")
    return resolved


@router.get(
    "/workflow/{request_id}/report",
    response_class=HTMLResponse,
    summary="Return the rendered workflow report HTML",
)
async def get_workflow_report(
    request_id: str,
    client: LocalOrchestratorClient = Depends(get_orchestrator_client),
) -> HTMLResponse:
    """Return the stored report HTML for a completed workflow."""
    workflow_response = client.get_workflow(request_id)
    if workflow_response is None:
        return HTMLResponse(
            content=f"<html><body><h1>Report not found</h1><p>{request_id}</p></body></html>",
            status_code=404,
        )

    report_result = workflow_response.final_state.get("report_result") or {}
    html = report_result.get("html")
    if isinstance(html, str) and html.strip():
        return HTMLResponse(content=html)

    report_uri = report_result.get("report_uri")
    if not report_uri:
        return HTMLResponse(
            content=(
                "<html><body><h1>Report unavailable</h1>"
                f"<p>No report was generated for {request_id}.</p></body></html>"
            ),
            status_code=404,
        )

    report_path = _validate_path(report_uri)
    if not report_path.exists():
        return HTMLResponse(
            content=(
                "<html><body><h1>Report missing</h1>"
                f"<p>Expected report at {report_path}.</p></body></html>"
            ),
            status_code=404,
        )
    return HTMLResponse(content=report_path.read_text(encoding="utf-8"))
