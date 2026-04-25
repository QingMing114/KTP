from __future__ import annotations

from v2.apps.api.config import V2ApiSettings
from v2.runtime.sqlite_store import SQLiteRuntimeStore
from v2.runtime.store import InMemoryRuntimeStore, RuntimeStore


def build_runtime_store(*, settings: V2ApiSettings) -> RuntimeStore:
    if settings.store_backend == "sqlite":
        return SQLiteRuntimeStore(database_path=settings.sqlite_path)
    return InMemoryRuntimeStore()
