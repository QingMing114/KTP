from __future__ import annotations

import hashlib
import hmac
import logging
import os
import sqlite3
import threading
import time
from pathlib import Path

from v2.shared.schemas import UserRecord

logger = logging.getLogger(__name__)

_DEFAULT_DB_PATH = str(Path(__file__).resolve().parents[2] / "data" / "users.sqlite3")


def _hash_password(password: str, salt: str | None = None) -> tuple[str, str]:
    if salt is None:
        salt = os.urandom(16).hex()
    dk = hashlib.pbkdf2_hmac("sha256", password.encode(), salt.encode(), 100000)
    return dk.hex(), salt


def hmac_compare(a: str, b: str) -> bool:
    return hmac.compare_digest(a.encode(), b.encode())


class UserStore:
    def __init__(self, db_path: str | None = None) -> None:
        self._db_path = db_path or os.environ.get("KTP_USER_DB_PATH", _DEFAULT_DB_PATH)
        self._lock = threading.Lock()
        self._conn = self._connect()

    def _connect(self) -> sqlite3.Connection:
        Path(self._db_path).parent.mkdir(parents=True, exist_ok=True)
        conn = sqlite3.connect(self._db_path, check_same_thread=False)
        conn.row_factory = sqlite3.Row
        self._initialize_schema(conn)
        return conn

    def _initialize_schema(self, conn: sqlite3.Connection) -> None:
        conn.execute("""
            CREATE TABLE IF NOT EXISTS users (
                user_id TEXT PRIMARY KEY,
                password_hash TEXT NOT NULL,
                role TEXT NOT NULL DEFAULT 'user',
                created_at TEXT NOT NULL,
                last_login TEXT,
                salt TEXT
            )
        """)
        try:
            conn.execute("ALTER TABLE users ADD COLUMN salt TEXT")
        except sqlite3.OperationalError:
            pass
        conn.commit()
        self._migrate_legacy_hashes(conn)

    def _migrate_legacy_hashes(self, conn: sqlite3.Connection) -> None:
        rows = conn.execute("SELECT user_id, password_hash FROM users WHERE salt IS NULL").fetchall()
        for row in rows:
            old_hash = row["password_hash"]
            new_hash, salt = _hash_password(old_hash)
            conn.execute("UPDATE users SET password_hash = ?, salt = ? WHERE user_id = ?",
                         (new_hash, salt, row["user_id"]))
        if rows:
            conn.commit()

    def create_user(self, user_id: str, password: str, role: str = "user") -> UserRecord:
        existing = self.get_user(user_id)
        if existing is not None:
            raise ValueError(f"User '{user_id}' already exists")
        pw_hash, salt = _hash_password(password)
        now = time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())
        with self._lock:
            self._conn.execute(
                "INSERT INTO users (user_id, password_hash, role, created_at, salt) VALUES (?, ?, ?, ?, ?)",
                (user_id, pw_hash, role, now, salt),
            )
            self._conn.commit()
        return UserRecord(user_id=user_id, password_hash=pw_hash, role=role, created_at=now)

    def get_user(self, user_id: str) -> UserRecord | None:
        with self._lock:
            row = self._conn.execute("SELECT * FROM users WHERE user_id = ?", (user_id,)).fetchone()
            if row is None:
                return None
            return UserRecord(
                user_id=row["user_id"],
                password_hash=row["password_hash"],
                role=row["role"],
                created_at=row["created_at"],
                last_login=row["last_login"],
            )

    def verify_password(self, user_id: str, password: str) -> bool:
        with self._lock:
            row = self._conn.execute("SELECT password_hash, salt FROM users WHERE user_id = ?", (user_id,)).fetchone()
            if row is None:
                return False
            stored_hash = row["password_hash"]
            salt = row["salt"]
            if salt:
                computed_hash, _ = _hash_password(password, salt)
            else:
                computed_hash = hashlib.sha256(password.encode()).hexdigest()
            return hmac_compare(stored_hash, computed_hash)

    def list_users(self) -> list[UserRecord]:
        with self._lock:
            rows = self._conn.execute("SELECT * FROM users ORDER BY created_at").fetchall()
            return [
                UserRecord(
                    user_id=r["user_id"],
                    password_hash=r["password_hash"],
                    role=r["role"],
                    created_at=r["created_at"],
                    last_login=r["last_login"],
                )
                for r in rows
            ]

    def update_last_login(self, user_id: str) -> None:
        now = time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())
        with self._lock:
            self._conn.execute("UPDATE users SET last_login = ? WHERE user_id = ?", (now, user_id))
            self._conn.commit()

    def update_password(self, user_id: str, new_password: str) -> None:
        new_hash, new_salt = _hash_password(new_password)
        with self._lock:
            self._conn.execute(
                "UPDATE users SET password_hash = ?, salt = ? WHERE user_id = ?",
                (new_hash, new_salt, user_id),
            )
            self._conn.commit()
