"""Thread-safe lease manager for reusable algorithm model resources."""

from __future__ import annotations

from contextlib import contextmanager
from dataclasses import dataclass
from threading import Lock
from typing import Callable, Generic, Iterator, TypeVar

T = TypeVar("T")


@dataclass
class _Entry(Generic[T]):
    resource: T
    references: int = 0


class ModelRuntimeManager(Generic[T]):
    def __init__(self) -> None:
        self._entries: dict[str, _Entry[T]] = {}
        self._lock = Lock()

    @contextmanager
    def lease(
        self,
        key: str,
        *,
        loader: Callable[[], T],
        unloader: Callable[[T], None] | None = None,
        retain: bool = True,
    ) -> Iterator[T]:
        with self._lock:
            entry = self._entries.get(key)
            if entry is None:
                entry = _Entry(resource=loader())
                self._entries[key] = entry
            entry.references += 1
        try:
            yield entry.resource
        finally:
            release: T | None = None
            with self._lock:
                entry.references -= 1
                if entry.references == 0 and not retain:
                    release = entry.resource
                    self._entries.pop(key, None)
            if release is not None and unloader is not None:
                unloader(release)

    def evict(self, key: str, *, unloader: Callable[[T], None] | None = None) -> bool:
        with self._lock:
            entry = self._entries.get(key)
            if entry is None or entry.references:
                return False
            self._entries.pop(key)
        if unloader is not None:
            unloader(entry.resource)
        return True

    def active_references(self, key: str) -> int:
        with self._lock:
            entry = self._entries.get(key)
            return 0 if entry is None else entry.references


__all__ = ["ModelRuntimeManager"]
