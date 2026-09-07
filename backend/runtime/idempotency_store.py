"""Transactional SQLite idempotency records for canonical mutating endpoints."""

from __future__ import annotations

import json
import threading
import time
from dataclasses import dataclass
from typing import Literal

from runtime.db import open_db


ClaimStatus = Literal["claimed", "replay", "conflict", "in_progress"]


@dataclass(frozen=True)
class IdempotencyClaim:
    status: ClaimStatus
    response_status: int | None = None
    response_body: dict | list | None = None


class IdempotencyStore:
    """Claim and complete idempotency keys atomically across processes."""

    def __init__(
        self,
        db_path: str | None = None,
        *,
        record_ttl_seconds: int = 86_400,
        processing_lease_seconds: int = 60,
    ) -> None:
        self._db = open_db(db_path)
        self._lock = threading.RLock()
        self._record_ttl_seconds = max(60, int(record_ttl_seconds))
        self._processing_lease_seconds = max(5, int(processing_lease_seconds))
        self._initialize_schema()

    def _initialize_schema(self) -> None:
        self._db.execute("""CREATE TABLE IF NOT EXISTS product_idempotency (
            principal TEXT NOT NULL,
            idempotency_key TEXT NOT NULL,
            endpoint TEXT NOT NULL,
            request_hash TEXT NOT NULL,
            state TEXT NOT NULL,
            response_status INTEGER,
            response_body_json TEXT,
            created_at REAL NOT NULL,
            expires_at REAL NOT NULL,
            PRIMARY KEY (principal, idempotency_key)
        )""")
        self._db.execute(
            "CREATE INDEX IF NOT EXISTS idx_product_idempotency_expiry "
            "ON product_idempotency(expires_at)"
        )
        self._db.commit()

    def claim(self, *, principal: str, key: str, endpoint: str, request_hash: str) -> IdempotencyClaim:
        now = time.time()
        with self._lock:
            self._db.execute("BEGIN IMMEDIATE")
            try:
                self._db.execute("DELETE FROM product_idempotency WHERE expires_at<=?", (now,))
                row = self._db.execute(
                    "SELECT * FROM product_idempotency WHERE principal=? AND idempotency_key=?",
                    (principal, key),
                ).fetchone()
                if row is None:
                    self._db.execute(
                        "INSERT INTO product_idempotency "
                        "(principal, idempotency_key, endpoint, request_hash, state, created_at, expires_at) "
                        "VALUES (?, ?, ?, ?, 'processing', ?, ?)",
                        (principal, key, endpoint, request_hash, now, now + self._processing_lease_seconds),
                    )
                    self._db.commit()
                    return IdempotencyClaim("claimed")
                if row["endpoint"] != endpoint or row["request_hash"] != request_hash:
                    self._db.commit()
                    return IdempotencyClaim("conflict")
                if row["state"] == "completed":
                    body = json.loads(row["response_body_json"]) if row["response_body_json"] else None
                    self._db.commit()
                    return IdempotencyClaim("replay", int(row["response_status"]), body)
                self._db.commit()
                return IdempotencyClaim("in_progress")
            except Exception:
                self._db.rollback()
                raise

    def complete(
        self,
        *,
        principal: str,
        key: str,
        endpoint: str,
        request_hash: str,
        response_status: int,
        response_body: dict | list,
    ) -> bool:
        now = time.time()
        with self._lock:
            cursor = self._db.execute(
                "UPDATE product_idempotency SET state='completed', response_status=?, "
                "response_body_json=?, expires_at=? "
                "WHERE principal=? AND idempotency_key=? AND endpoint=? AND request_hash=? AND state='processing'",
                (
                    int(response_status),
                    json.dumps(response_body, ensure_ascii=False),
                    now + self._record_ttl_seconds,
                    principal,
                    key,
                    endpoint,
                    request_hash,
                ),
            )
            self._db.commit()
            return cursor.rowcount == 1

    def wait_for_completion(
        self,
        *,
        principal: str,
        key: str,
        endpoint: str,
        request_hash: str,
        timeout_seconds: float = 5.0,
    ) -> IdempotencyClaim:
        deadline = time.monotonic() + max(0.0, timeout_seconds)
        while time.monotonic() < deadline:
            with self._lock:
                row = self._db.execute(
                    "SELECT endpoint, request_hash, state, response_status, response_body_json "
                    "FROM product_idempotency WHERE principal=? AND idempotency_key=?",
                    (principal, key),
                ).fetchone()
            if row is None:
                return IdempotencyClaim("in_progress")
            if row["endpoint"] != endpoint or row["request_hash"] != request_hash:
                return IdempotencyClaim("conflict")
            if row["state"] == "completed":
                body = json.loads(row["response_body_json"]) if row["response_body_json"] else None
                return IdempotencyClaim("replay", int(row["response_status"]), body)
            time.sleep(0.02)
        return IdempotencyClaim("in_progress")

    def release(self, *, principal: str, key: str, endpoint: str, request_hash: str) -> None:
        """Release an uncompleted claim when request processing is rejected."""
        with self._lock:
            self._db.execute(
                "DELETE FROM product_idempotency WHERE principal=? AND idempotency_key=? "
                "AND endpoint=? AND request_hash=? AND state='processing'",
                (principal, key, endpoint, request_hash),
            )
            self._db.commit()

    def cleanup_expired(self) -> int:
        with self._lock:
            cursor = self._db.execute("DELETE FROM product_idempotency WHERE expires_at<=?", (time.time(),))
            self._db.commit()
            return cursor.rowcount

    def close(self) -> None:
        with self._lock:
            self._db.close()


__all__ = ["IdempotencyClaim", "IdempotencyStore"]
