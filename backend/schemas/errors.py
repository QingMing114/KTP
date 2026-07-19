"""Canonical error envelope for the product protocol (/api/product/v1).

Follows ``canonical_api_spec.md`` -- Error Envelope: every error response
is wrapped in ``{"error": {"code": "...", "message": "...", "detail": {}, "request_id": "..."}}``.

Usage::

    from schemas.errors import canonical_error_response
    return canonical_error_response(404, code="CONVERSATION_NOT_FOUND", message="...")
"""

from __future__ import annotations

from enum import StrEnum

from fastapi.responses import JSONResponse
from pydantic import BaseModel, Field


# ── Error codes (from canonical_api_spec.md) ──

class ErrorCode(StrEnum):
    INVALID_REQUEST = "INVALID_REQUEST"
    UNAUTHORIZED = "UNAUTHORIZED"
    DATASET_NOT_FOUND = "DATASET_NOT_FOUND"
    DATASET_SOURCE_NOT_FOUND = "DATASET_SOURCE_NOT_FOUND"
    CONVERSATION_NOT_FOUND = "CONVERSATION_NOT_FOUND"
    SUBMISSION_NOT_FOUND = "SUBMISSION_NOT_FOUND"
    RUN_NOT_FOUND = "RUN_NOT_FOUND"
    ARTIFACT_NOT_FOUND = "ARTIFACT_NOT_FOUND"
    UNSUPPORTED_SOURCE_KIND = "UNSUPPORTED_SOURCE_KIND"
    UNSUPPORTED_DELIVERY_MODE = "UNSUPPORTED_DELIVERY_MODE"
    INVALID_REFERENCE = "INVALID_REFERENCE"
    IDEMPOTENCY_CONFLICT = "IDEMPOTENCY_CONFLICT"
    UPSTREAM_LLM_TIMEOUT = "UPSTREAM_LLM_TIMEOUT"
    UPSTREAM_LLM_OVERLOADED = "UPSTREAM_LLM_OVERLOADED"
    IMAGERY_SEARCH_FAILED = "IMAGERY_SEARCH_FAILED"
    SCHEMA_MISMATCH = "SCHEMA_MISMATCH"
    TOOL_EXECUTION_FAILED = "TOOL_EXECUTION_FAILED"
    REPLAN_BUDGET_EXCEEDED = "REPLAN_BUDGET_EXCEEDED"
    CANCELLATION_NOT_SUPPORTED = "CANCELLATION_NOT_SUPPORTED"
    ALREADY_TERMINAL = "ALREADY_TERMINAL"
    INTERNAL_ERROR = "INTERNAL_ERROR"


# ── Pydantic models ──

class CanonicalError(BaseModel):
    """Single error entry for the canonical error envelope."""
    code: str
    message: str
    detail: dict = Field(default_factory=dict)
    request_id: str | None = None


class ErrorResponse(BaseModel):
    """Canonical error envelope wrapper."""
    error: CanonicalError


# ── Helper ──

def canonical_error_response(
    status_code: int,
    *,
    code: str,
    message: str,
    detail: dict | None = None,
    request_id: str | None = None,
    headers: dict[str, str] | None = None,
) -> JSONResponse:
    """Return a JSONResponse with the canonical error envelope."""
    return JSONResponse(
        status_code=status_code,
        content=ErrorResponse(
            error=CanonicalError(
                code=code,
                message=message,
                detail=detail or {},
                request_id=request_id,
            ),
        ).model_dump(mode="json"),
        headers=headers,
    )


__all__ = [
    "CanonicalError",
    "ErrorCode",
    "ErrorResponse",
    "canonical_error_response",
]
