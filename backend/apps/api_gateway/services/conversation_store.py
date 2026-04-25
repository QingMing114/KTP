"""Durable conversation storage for multi-turn gateway chat."""

from __future__ import annotations

import json
import logging
import sqlite3
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

logger = logging.getLogger(__name__)

_ANONYMOUS_USER_ID = "anonymous"


class ConversationStoreError(RuntimeError):
    """Raised when conversation history cannot be persisted or loaded."""


@dataclass(frozen=True)
class ConversationTurn:
    """Single persisted chat turn."""

    user_id: str
    conversation_id: str
    request_id: str
    created_at: str
    mode: str
    route_reason: str
    success: bool
    user_message: str
    answer: str
    region: str | None
    crop_type: str | None
    task_type: str | None
    image_path: str | None
    use_mock: bool | None
    workflow_status: str | None
    sources: list[str]
    extra_params: dict[str, Any]
    context: dict[str, Any]
    response_payload: dict[str, Any]


@dataclass(frozen=True)
class ConversationSummary:
    """Aggregated conversation summary for listing in the chat UI."""

    user_id: str
    conversation_id: str
    title: str
    created_at: str
    updated_at: str
    turn_count: int
    last_mode: str
    workflow_status: str | None
    last_request_id: str
    last_message_preview: str


class ConversationStore:
    """Persist chat turns in a small local SQLite database."""

    def __init__(self, *, db_path: str) -> None:
        self._db_path = db_path
        self._ensure_parent_directory()
        self._initialize_schema()

    def append_turn(self, turn: ConversationTurn) -> None:
        """Persist one completed chat turn."""
        logger.info(
            "conversation_store_append_started | user_id=%s | conversation_id=%s | request_id=%s",
            turn.user_id,
            turn.conversation_id,
            turn.request_id,
        )
        try:
            with self._connect() as connection:
                connection.execute(
                    """
                    INSERT INTO conversation_turns (
                        user_id,
                        conversation_id,
                        request_id,
                        created_at,
                        mode,
                        route_reason,
                        success,
                        user_message,
                        answer,
                        region,
                        crop_type,
                        task_type,
                        image_path,
                        use_mock,
                        workflow_status,
                        sources_json,
                        extra_params_json,
                        context_json,
                        response_payload_json
                    )
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                    """,
                    (
                        turn.user_id,
                        turn.conversation_id,
                        turn.request_id,
                        turn.created_at,
                        turn.mode,
                        turn.route_reason,
                        1 if turn.success else 0,
                        turn.user_message,
                        turn.answer,
                        turn.region,
                        turn.crop_type,
                        turn.task_type,
                        turn.image_path,
                        self._encode_bool(turn.use_mock),
                        turn.workflow_status,
                        json.dumps(turn.sources, ensure_ascii=False, sort_keys=True),
                        json.dumps(turn.extra_params, ensure_ascii=False, sort_keys=True),
                        json.dumps(turn.context, ensure_ascii=False, sort_keys=True),
                        json.dumps(turn.response_payload, ensure_ascii=False, sort_keys=True),
                    ),
                )
        except sqlite3.Error as exc:
            raise ConversationStoreError(f"unable to append conversation turn: {exc}") from exc
        logger.info(
            "conversation_store_append_succeeded | user_id=%s | conversation_id=%s | request_id=%s",
            turn.user_id,
            turn.conversation_id,
            turn.request_id,
        )

    def get_recent_turns(
        self,
        *,
        user_id: str,
        conversation_id: str,
        limit: int,
    ) -> list[ConversationTurn]:
        """Return the most recent turns for a conversation in chronological order."""
        logger.info(
            "conversation_store_read_started | user_id=%s | conversation_id=%s | limit=%s",
            user_id,
            conversation_id,
            limit,
        )
        try:
            with self._connect() as connection:
                rows = connection.execute(
                    """
                    SELECT
                        user_id,
                        conversation_id,
                        request_id,
                        created_at,
                        mode,
                        route_reason,
                        success,
                        user_message,
                        answer,
                        region,
                        crop_type,
                        task_type,
                        image_path,
                        use_mock,
                        workflow_status,
                        sources_json,
                        extra_params_json,
                        context_json,
                        response_payload_json
                    FROM conversation_turns
                    WHERE user_id = ? AND conversation_id = ?
                    ORDER BY id DESC
                    LIMIT ?
                    """,
                    (user_id, conversation_id, limit),
                ).fetchall()
        except sqlite3.Error as exc:
            raise ConversationStoreError(f"unable to read conversation turns: {exc}") from exc

        turns = [self._row_to_turn(row) for row in reversed(rows)]
        logger.info(
            "conversation_store_read_succeeded | user_id=%s | conversation_id=%s | turn_count=%s",
            user_id,
            conversation_id,
            len(turns),
        )
        return turns

    def get_all_turns(
        self,
        *,
        user_id: str,
        conversation_id: str,
    ) -> list[ConversationTurn]:
        """Return all turns for one conversation in chronological order."""
        logger.info(
            "conversation_store_detail_started | user_id=%s | conversation_id=%s",
            user_id,
            conversation_id,
        )
        try:
            with self._connect() as connection:
                rows = connection.execute(
                    """
                    SELECT
                        user_id,
                        conversation_id,
                        request_id,
                        created_at,
                        mode,
                        route_reason,
                        success,
                        user_message,
                        answer,
                        region,
                        crop_type,
                        task_type,
                        image_path,
                        use_mock,
                        workflow_status,
                        sources_json,
                        extra_params_json,
                        context_json,
                        response_payload_json
                    FROM conversation_turns
                    WHERE user_id = ? AND conversation_id = ?
                    ORDER BY id ASC
                    """,
                    (user_id, conversation_id),
                ).fetchall()
        except sqlite3.Error as exc:
            raise ConversationStoreError(f"unable to read conversation detail: {exc}") from exc

        turns = [self._row_to_turn(row) for row in rows]
        logger.info(
            "conversation_store_detail_succeeded | user_id=%s | conversation_id=%s | turn_count=%s",
            user_id,
            conversation_id,
            len(turns),
        )
        return turns

    def list_conversations(
        self,
        *,
        user_id: str,
        limit: int,
    ) -> list[ConversationSummary]:
        """Return latest conversation summaries for one user."""
        logger.info(
            "conversation_store_list_started | user_id=%s | limit=%s",
            user_id,
            limit,
        )
        try:
            with self._connect() as connection:
                rows = connection.execute(
                    """
                    SELECT
                        user_id,
                        conversation_id,
                        request_id,
                        created_at,
                        mode,
                        user_message,
                        workflow_status
                    FROM conversation_turns
                    WHERE user_id = ?
                    ORDER BY id DESC
                    """,
                    (user_id,),
                ).fetchall()
        except sqlite3.Error as exc:
            raise ConversationStoreError(f"unable to list conversations: {exc}") from exc

        summaries: list[ConversationSummary] = []
        seen: set[str] = set()
        grouped_counts: dict[str, int] = {}
        first_message_by_conversation: dict[str, str] = {}
        first_created_at_by_conversation: dict[str, str] = {}

        for row in reversed(rows):
            conversation_id = str(row["conversation_id"])
            grouped_counts[conversation_id] = grouped_counts.get(conversation_id, 0) + 1
            first_message_by_conversation.setdefault(
                conversation_id,
                str(row["user_message"]),
            )
            first_created_at_by_conversation.setdefault(
                conversation_id,
                str(row["created_at"]),
            )

        for row in rows:
            conversation_id = str(row["conversation_id"])
            if conversation_id in seen:
                continue
            seen.add(conversation_id)
            title = self._build_title(first_message_by_conversation.get(conversation_id, ""))
            summaries.append(
                ConversationSummary(
                    user_id=str(row["user_id"]),
                    conversation_id=conversation_id,
                    title=title,
                    created_at=first_created_at_by_conversation.get(
                        conversation_id,
                        str(row["created_at"]),
                    ),
                    updated_at=str(row["created_at"]),
                    turn_count=grouped_counts.get(conversation_id, 1),
                    last_mode=str(row["mode"]),
                    workflow_status=row["workflow_status"],
                    last_request_id=str(row["request_id"]),
                    last_message_preview=self._build_preview(str(row["user_message"])),
                )
            )
            if len(summaries) >= limit:
                break

        logger.info(
            "conversation_store_list_succeeded | user_id=%s | conversation_count=%s",
            user_id,
            len(summaries),
        )
        return summaries

    @staticmethod
    def build_turn(
        *,
        user_id: str,
        conversation_id: str,
        request_id: str,
        mode: str,
        route_reason: str,
        success: bool,
        user_message: str,
        answer: str,
        region: str | None,
        crop_type: str | None,
        task_type: str | None,
        image_path: str | None,
        use_mock: bool | None,
        workflow_status: str | None,
        sources: list[str],
        extra_params: dict[str, Any],
        context: dict[str, Any],
        response_payload: dict[str, Any],
    ) -> ConversationTurn:
        """Create a persisted conversation turn payload."""
        return ConversationTurn(
            user_id=user_id or _ANONYMOUS_USER_ID,
            conversation_id=conversation_id,
            request_id=request_id,
            created_at=datetime.now(UTC).isoformat(),
            mode=mode,
            route_reason=route_reason,
            success=success,
            user_message=user_message,
            answer=answer,
            region=region,
            crop_type=crop_type,
            task_type=task_type,
            image_path=image_path,
            use_mock=use_mock,
            workflow_status=workflow_status,
            sources=list(sources),
            extra_params=dict(extra_params),
            context=dict(context),
            response_payload=dict(response_payload),
        )

    def _initialize_schema(self) -> None:
        try:
            with self._connect() as connection:
                connection.execute(
                    """
                    CREATE TABLE IF NOT EXISTS conversation_turns (
                        id INTEGER PRIMARY KEY AUTOINCREMENT,
                        user_id TEXT NOT NULL DEFAULT 'anonymous',
                        conversation_id TEXT NOT NULL,
                        request_id TEXT NOT NULL UNIQUE,
                        created_at TEXT NOT NULL,
                        mode TEXT NOT NULL,
                        route_reason TEXT NOT NULL,
                        success INTEGER NOT NULL,
                        user_message TEXT NOT NULL,
                        answer TEXT NOT NULL,
                        region TEXT NULL,
                        crop_type TEXT NULL,
                        task_type TEXT NULL,
                        image_path TEXT NULL,
                        use_mock INTEGER NULL,
                        workflow_status TEXT NULL,
                        sources_json TEXT NOT NULL,
                        extra_params_json TEXT NOT NULL,
                        context_json TEXT NOT NULL,
                        response_payload_json TEXT NOT NULL DEFAULT '{}'
                    )
                    """
                )
                self._ensure_columns(connection)
                connection.execute(
                    """
                    CREATE INDEX IF NOT EXISTS idx_conversation_turns_user_conversation_id
                    ON conversation_turns(user_id, conversation_id, id)
                    """
                )
                connection.execute(
                    """
                    CREATE INDEX IF NOT EXISTS idx_conversation_turns_user_id
                    ON conversation_turns(user_id, id)
                    """
                )
        except sqlite3.Error as exc:
            raise ConversationStoreError(f"unable to initialize conversation store: {exc}") from exc

    def _ensure_columns(self, connection: sqlite3.Connection) -> None:
        columns = {
            str(row["name"])
            for row in connection.execute("PRAGMA table_info(conversation_turns)").fetchall()
        }
        if "user_id" not in columns:
            connection.execute(
                "ALTER TABLE conversation_turns ADD COLUMN user_id TEXT NOT NULL DEFAULT 'anonymous'"
            )
        if "response_payload_json" not in columns:
            connection.execute(
                "ALTER TABLE conversation_turns ADD COLUMN response_payload_json TEXT NOT NULL DEFAULT '{}'"
            )

    def _ensure_parent_directory(self) -> None:
        parent = Path(self._db_path).expanduser().resolve().parent
        parent.mkdir(parents=True, exist_ok=True)

    def _connect(self) -> sqlite3.Connection:
        connection = sqlite3.connect(self._db_path)
        connection.row_factory = sqlite3.Row
        return connection

    @staticmethod
    def _encode_bool(value: bool | None) -> int | None:
        if value is None:
            return None
        return 1 if value else 0

    @staticmethod
    def _decode_bool(value: int | None) -> bool | None:
        if value is None:
            return None
        return bool(value)

    def _row_to_turn(self, row: sqlite3.Row) -> ConversationTurn:
        return ConversationTurn(
            user_id=str(row["user_id"] or _ANONYMOUS_USER_ID),
            conversation_id=str(row["conversation_id"]),
            request_id=str(row["request_id"]),
            created_at=str(row["created_at"]),
            mode=str(row["mode"]),
            route_reason=str(row["route_reason"]),
            success=bool(row["success"]),
            user_message=str(row["user_message"]),
            answer=str(row["answer"]),
            region=row["region"],
            crop_type=row["crop_type"],
            task_type=row["task_type"],
            image_path=row["image_path"],
            use_mock=self._decode_bool(row["use_mock"]),
            workflow_status=row["workflow_status"],
            sources=list(json.loads(str(row["sources_json"]))),
            extra_params=dict(json.loads(str(row["extra_params_json"]))),
            context=dict(json.loads(str(row["context_json"]))),
            response_payload=dict(json.loads(str(row["response_payload_json"] or "{}"))),
        )

    @staticmethod
    def _build_title(message: str) -> str:
        content = " ".join(message.split())
        if not content:
            return "未命名会话"
        return content[:24] + ("…" if len(content) > 24 else "")

    @staticmethod
    def _build_preview(message: str) -> str:
        content = " ".join(message.split())
        return content[:40] + ("…" if len(content) > 40 else "")
