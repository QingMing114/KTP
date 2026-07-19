"""Shared SQLite connection factory for product stores.

All three product stores (SubmissionStore, DatasetStore, ArtifactStore) use
this module to open connections to the same SQLite database file, ensuring
consistent WAL configuration and a single point of change for DB settings.
"""

from __future__ import annotations

import sqlite3
from pathlib import Path

_DEFAULT_DB = Path(__file__).parent.parent / "data" / "ktp_v2_runtime.sqlite3"


def open_db(db_path: str | Path | None = None) -> sqlite3.Connection:
    """Open a SQLite connection configured for the product stores.

    Uses WAL journal mode + ``synchronous=NORMAL`` + ``busy_timeout=5000``,
    matching the existing ``v2/runtime/sqlite_store.py`` convention.
    """
    path = Path(db_path) if db_path else _DEFAULT_DB
    path.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(str(path), check_same_thread=False)
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute("PRAGMA synchronous=NORMAL")
    conn.execute("PRAGMA busy_timeout=5000")
    conn.row_factory = sqlite3.Row
    return conn
