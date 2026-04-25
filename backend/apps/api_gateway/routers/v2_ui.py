"""Serve the V2 KTP product UI shell from the gateway host."""

from __future__ import annotations

from fastapi import APIRouter
from fastapi.responses import HTMLResponse

router = APIRouter(tags=["v2-ui"])

_HTML = """<!doctype html>
<html lang="zh-CN">
  <head>
    <meta charset="UTF-8" />
    <meta name="viewport" content="width=device-width, initial-scale=1.0" />
    <title>KTP Chat-First Agent</title>
  </head>
  <body>
    <div style="display:none">KTP 智能体</div>
    <div id="app"></div>
    <script type="module" src="/v2/ui/dist/main.js"></script>
  </body>
</html>
"""


@router.get("/v2/ui", response_class=HTMLResponse, summary="Serve the V2 KTP product UI")
@router.get("/v2/ui/", response_class=HTMLResponse, include_in_schema=False)
async def v2_ui() -> HTMLResponse:
    """Return the gateway-hosted V2 UI shell."""
    return HTMLResponse(content=_HTML)
