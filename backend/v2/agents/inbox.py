"""Inbox for subagent settlements.

A child agent never writes into its parent's message history directly. It drops
a settlement into the parent's inbox; the parent runtime drains it at its next
step boundary. This mirrors the harness architecture: activation is immediate,
settlement is asynchronous, and the parent stays the only writer of its history.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from threading import Lock
from time import monotonic
from typing import Any


@dataclass(frozen=True)
class AgentSettlement:
    """One finished child agent run, delivered to the parent inbox."""

    agent_run_id: str
    parent_run_id: str
    role: str
    goal: str
    success: bool
    summary: str
    duration_seconds: float
    artifact_count: int = 0
    tool_count: int = 0
    error: str | None = None

    def as_history_item(self) -> dict[str, Any]:
        status = "success" if self.success else "error"
        return {
            "role": "tool",
            "content": f"[子代理 {self.role} · {status}] {self.summary}",
            "tool_call_id": f"settlement_{self.agent_run_id}",
        }


@dataclass
class AgentInbox:
    """Thread-safe per-parent settlement queue."""

    _items: dict[str, list[AgentSettlement]] = field(default_factory=dict)
    _lock: Lock = field(default_factory=Lock)

    def push(self, settlement: AgentSettlement) -> None:
        with self._lock:
            self._items.setdefault(settlement.parent_run_id, []).append(settlement)

    def drain(self, parent_run_id: str) -> list[AgentSettlement]:
        with self._lock:
            return self._items.pop(parent_run_id, [])

    def pending(self, parent_run_id: str) -> int:
        with self._lock:
            return len(self._items.get(parent_run_id, ()))

    def wait(self, parent_run_id: str, timeout_seconds: float, poll_interval: float = 0.05) -> list[AgentSettlement]:
        """Drain as soon as anything arrives, or return empty after the timeout."""
        deadline = monotonic() + max(0.0, timeout_seconds)
        while True:
            drained = self.drain(parent_run_id)
            if drained:
                return drained
            if monotonic() >= deadline:
                return []
            from time import sleep

            sleep(poll_interval)
