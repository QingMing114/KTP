"""Helpers for bridging async service calls from sync orchestration code."""

from __future__ import annotations

import asyncio
import threading
from typing import Any, Coroutine, TypeVar

ResultT = TypeVar("ResultT")


def run_coro_sync(coro: Coroutine[Any, Any, ResultT]) -> ResultT:
    """Run a coroutine from synchronous code, even under a running event loop."""
    try:
        asyncio.get_running_loop()
    except RuntimeError:
        return asyncio.run(coro)

    result: dict[str, ResultT] = {}
    error: dict[str, BaseException] = {}

    def _runner() -> None:
        try:
            result["value"] = asyncio.run(coro)
        except BaseException as exc:  # pragma: no cover - passthrough branch
            error["value"] = exc

    thread = threading.Thread(target=_runner, daemon=True)
    thread.start()
    thread.join()

    if "value" in error:
        raise error["value"]
    return result["value"]
