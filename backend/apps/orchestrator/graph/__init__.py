"""LangGraph workflow assembly helpers."""

from __future__ import annotations

from apps.orchestrator.graph.states import WorkflowState, create_initial_state

__all__ = ["WorkflowState", "build_workflow", "create_initial_state", "get_workflow"]


def build_workflow():
    """Lazy import to avoid hard dependency at package import time."""
    from apps.orchestrator.graph.workflow import build_workflow as _build_workflow

    return _build_workflow()


def get_workflow():
    """Lazy import to avoid hard dependency at package import time."""
    from apps.orchestrator.graph.workflow import get_workflow as _get_workflow

    return _get_workflow()
