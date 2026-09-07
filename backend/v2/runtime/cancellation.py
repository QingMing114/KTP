"""Cooperative cancellation primitives for bounded runtime execution."""

from __future__ import annotations

from threading import Event


class RuntimeCancellationError(RuntimeError):
    """Raised at a safe execution boundary after cancellation is requested."""


def raise_if_cancelled(cancellation_event: Event | None) -> None:
    if cancellation_event is not None and cancellation_event.is_set():
        raise RuntimeCancellationError("runtime_cancelled")
