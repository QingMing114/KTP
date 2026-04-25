"""Redirect legacy chat UI requests to the V2 product UI."""

from __future__ import annotations

from fastapi import APIRouter
from fastapi.responses import RedirectResponse

router = APIRouter(tags=["chat-ui"])


@router.get("/chat/ui", summary="Redirect the legacy chat UI to the V2 product UI")
async def chat_ui() -> RedirectResponse:
    """Redirect to the V2 KTP single-agent UI."""
    return RedirectResponse(url="/v2/ui", status_code=307)
