"""Executor agent package."""

from __future__ import annotations

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from agents.executor_30b.agent import ExecutorAgent

__all__ = ["ExecutorAgent"]
