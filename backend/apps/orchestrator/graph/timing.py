"""Helpers for capturing per-stage workflow timing."""

from __future__ import annotations

from time import perf_counter
from typing import Any

from apps.orchestrator.graph.states import WorkflowState


def stage_started() -> float:
    """Return a monotonic start timestamp for one workflow stage."""
    return perf_counter()


def append_stage_timing(
    state: WorkflowState,
    *,
    stage_name: str,
    started_at: float,
    status: str,
    detail: str | None = None,
) -> list[dict[str, Any]]:
    """Append one stage timing entry to the workflow state."""
    duration_ms = round((perf_counter() - started_at) * 1000.0, 3)
    return [
        *state.get("stage_timings", []),
        {
            "stage": stage_name,
            "status": status,
            "duration_ms": duration_ms,
            "detail": detail,
        },
    ]
