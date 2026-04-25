"""Helpers for bounded chat-runtime regression evaluation."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Literal

from pydantic import BaseModel, Field


class ChatRuntimeEvalCase(BaseModel):
    """One regression case for the chat runtime."""

    name: str = Field(..., description="Human-readable case identifier.")
    category: str = Field(default="general", description="Case category for grouping and reporting.")
    objective: str | None = Field(default=None, description="Short statement of what the case verifies.")
    message: str = Field(..., description="User message sent to /chat.")
    mode: Literal["auto", "agent", "qa", "workflow"] = Field(
        default="agent",
        description="Chat mode used for this evaluation case.",
    )
    user_id: str = Field(default="eval-user", description="User id for conversation isolation.")
    automated: bool = Field(default=True, description="Whether this case is expected to be runnable by the script.")
    expected_mode: Literal["agent", "qa", "workflow"] | None = Field(
        default=None,
        description="Expected resolved response mode when known.",
    )
    expected_success: bool | None = Field(
        default=None,
        description="Expected success flag when known.",
    )
    expected_route_reason_contains: list[str] = Field(
        default_factory=list,
        description="Substrings that must appear in route_reason.",
    )
    expected_answer_contains: list[str] = Field(
        default_factory=list,
        description="Substrings that must appear in answer.",
    )


class ChatRuntimeEvalResult(BaseModel):
    """Structured evaluation result for one case."""

    name: str
    passed: bool
    mismatches: list[str] = Field(default_factory=list)
    response_mode: str | None = None
    success: bool | None = None
    route_reason: str | None = None


class ChatRuntimeEvalSummary(BaseModel):
    """Aggregate regression summary for a case batch."""

    total: int
    passed: int
    failed: int
    results: list[ChatRuntimeEvalResult]


def load_eval_cases(path: str | Path) -> list[ChatRuntimeEvalCase]:
    """Load evaluation cases from a JSON file."""
    data = json.loads(Path(path).read_text(encoding="utf-8"))
    if not isinstance(data, list):
        raise ValueError("evaluation case file must contain a JSON list")
    return [ChatRuntimeEvalCase.model_validate(item) for item in data]


def evaluate_chat_response(
    case: ChatRuntimeEvalCase,
    response_payload: dict[str, Any],
) -> ChatRuntimeEvalResult:
    """Compare one chat response payload against one regression case."""
    mismatches: list[str] = []
    response_mode = _string_or_none(response_payload.get("mode"))
    success = _bool_or_none(response_payload.get("success"))
    route_reason = _string_or_none(response_payload.get("route_reason"))
    answer = _string_or_none(response_payload.get("answer")) or ""

    if case.expected_mode is not None and response_mode != case.expected_mode:
        mismatches.append(
            f"expected mode={case.expected_mode!r}, got {response_mode!r}",
        )
    if case.expected_success is not None and success != case.expected_success:
        mismatches.append(
            f"expected success={case.expected_success!r}, got {success!r}",
        )
    for substring in case.expected_route_reason_contains:
        if substring not in (route_reason or ""):
            mismatches.append(f"route_reason missing substring {substring!r}")
    for substring in case.expected_answer_contains:
        if substring not in answer:
            mismatches.append(f"answer missing substring {substring!r}")

    return ChatRuntimeEvalResult(
        name=case.name,
        passed=not mismatches,
        mismatches=mismatches,
        response_mode=response_mode,
        success=success,
        route_reason=route_reason,
    )


def summarize_eval_results(results: list[ChatRuntimeEvalResult]) -> ChatRuntimeEvalSummary:
    """Aggregate a batch of evaluation results."""
    passed = sum(1 for result in results if result.passed)
    total = len(results)
    return ChatRuntimeEvalSummary(
        total=total,
        passed=passed,
        failed=total - passed,
        results=results,
    )


def _string_or_none(value: Any) -> str | None:
    return value if isinstance(value, str) else None


def _bool_or_none(value: Any) -> bool | None:
    return value if isinstance(value, bool) else None
