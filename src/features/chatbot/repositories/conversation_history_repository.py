import json
import sqlite3
from typing import Any

from src.features.membership.core.database import get_membership_connection, membership_transaction
from src.features.membership.core.time import utc_now_iso
from src.shared.database.serialization import database_json_dumps


class ConversationHistoryRepository:
    def list_for_user(self, user_id: str) -> list[dict[str, Any]]:
        with get_membership_connection() as connection:
            rows = connection.execute(
                """
                SELECT *
                FROM chat_conversation
                WHERE user_id = ? AND deleted_at IS NULL
                ORDER BY updated_at DESC, id DESC
                """,
                [user_id],
            ).fetchall()
            return [self._conversation_row(connection, row) for row in rows]

    def get_for_user(self, conversation_id: str, user_id: str) -> dict[str, Any] | None:
        with get_membership_connection() as connection:
            row = connection.execute(
                """
                SELECT *
                FROM chat_conversation
                WHERE id = ? AND user_id = ? AND deleted_at IS NULL
                """,
                [conversation_id, user_id],
            ).fetchone()
            return self._conversation_row(connection, row) if row else None

    def upsert_for_user(
        self,
        conversation_id: str,
        user_id: str,
        payload: dict[str, Any],
    ) -> dict[str, Any] | None:
        now = utc_now_iso()
        with membership_transaction() as connection:
            owner = connection.execute(
                "SELECT user_id FROM chat_conversation WHERE id = ?",
                [conversation_id],
            ).fetchone()
            if owner is not None and owner["user_id"] != user_id:
                return None

            existing = owner is not None
            if existing:
                connection.execute(
                    """
                    UPDATE chat_conversation
                    SET title = ?, updated_at = ?, deleted_at = NULL
                    WHERE id = ? AND user_id = ?
                    """,
                    [payload.get("title") or "新對話", now, conversation_id, user_id],
                )
            else:
                connection.execute(
                    """
                    INSERT INTO chat_conversation (id, user_id, title, created_at, updated_at)
                    VALUES (?, ?, ?, ?, ?)
                    """,
                    [
                        conversation_id,
                        user_id,
                        payload.get("title") or "新對話",
                        payload.get("createdAt") or now,
                        now,
                    ],
                )

            connection.execute(
                "DELETE FROM chat_conversation_message WHERE conversation_id = ?",
                [conversation_id],
            )
            data_sources = payload.get("dataSourcesForMessages") or {}
            expert_knowledge = payload.get("expertKnowledgeForMessages") or {}
            external_data = payload.get("externalDataForMessages") or {}
            for index, message in enumerate(payload.get("messages") or []):
                message_id = message["id"]
                connection.execute(
                    """
                    INSERT INTO chat_conversation_message (
                        id, conversation_id, role, content_json, sort_order,
                        data_sources_json, created_at, updated_at
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                    """,
                    [
                        message_id,
                        conversation_id,
                        message.get("role") or "user",
                        database_json_dumps(message.get("content", ""), ensure_ascii=False),
                        index,
                        database_json_dumps(data_sources.get(message_id, []), ensure_ascii=False),
                        now,
                        now,
                    ],
                )
                self._insert_expert_knowledge(
                    connection,
                    conversation_id,
                    message_id,
                    expert_knowledge.get(message_id, []),
                    now,
                )
                self._insert_external_data(
                    connection,
                    conversation_id,
                    message_id,
                    external_data.get(message_id, []),
                    now,
                )

        return self.get_for_user(conversation_id, user_id)

    def delete_for_user(self, conversation_id: str, user_id: str) -> bool:
        now = utc_now_iso()
        with membership_transaction() as connection:
            cursor = connection.execute(
                """
                UPDATE chat_conversation
                SET deleted_at = ?, updated_at = ?
                WHERE id = ? AND user_id = ? AND deleted_at IS NULL
                """,
                [now, now, conversation_id, user_id],
            )
            return cursor.rowcount > 0

    def _conversation_row(
        self,
        connection: sqlite3.Connection,
        row: sqlite3.Row,
    ) -> dict[str, Any]:
        message_rows = connection.execute(
            """
            SELECT *
            FROM chat_conversation_message
            WHERE conversation_id = ?
            ORDER BY sort_order ASC, id ASC
            """,
            [row["id"]],
        ).fetchall()
        messages: list[dict[str, Any]] = []
        data_sources: dict[str, list[Any]] = {}
        expert_knowledge: dict[str, list[Any]] = {}
        external_data: dict[str, list[Any]] = {}
        for message_row in message_rows:
            message_id = message_row["id"]
            messages.append(
                {
                    "id": message_id,
                    "role": message_row["role"],
                    "content": self._json(message_row["content_json"], ""),
                }
            )
            self._add_reference(data_sources, message_id, message_row["data_sources_json"])
            expert_rows = connection.execute(
                """
                SELECT *
                FROM chat_message_expert_knowledge
                WHERE conversation_id = ? AND message_id = ?
                ORDER BY sort_order ASC, id ASC
                """,
                [row["id"], message_id],
            ).fetchall()
            if expert_rows:
                expert_knowledge[message_id] = [
                    {
                        "title": item["title"],
                        "anchorDescription": item["anchor_description"],
                        "systemPrompt": item["system_prompt"],
                        "createdAt": item["source_created_at"],
                        "updatedAt": item["source_updated_at"],
                    }
                    for item in expert_rows
                ]
            external_rows = connection.execute(
                """
                SELECT *
                FROM chat_message_external_data
                WHERE conversation_id = ? AND message_id = ?
                ORDER BY sort_order ASC, id ASC
                """,
                [row["id"], message_id],
            ).fetchall()
            if external_rows:
                external_data[message_id] = [
                    {
                        "source": item["source"],
                        "response": item["response"],
                    }
                    for item in external_rows
                ]
        return {
            "id": row["id"],
            "title": row["title"],
            "createdAt": row["created_at"],
            "updatedAt": row["updated_at"],
            "messages": messages,
            "dataSourcesForMessages": data_sources,
            "expertKnowledgeForMessages": expert_knowledge,
            "externalDataForMessages": external_data,
        }

    def _add_reference(
        self,
        target: dict[str, list[Any]],
        message_id: str,
        raw: str,
    ) -> None:
        value = self._json(raw, [])
        if isinstance(value, list) and value:
            target[message_id] = value

    def _insert_expert_knowledge(
        self,
        connection: sqlite3.Connection,
        conversation_id: str,
        message_id: str,
        entries: list[Any],
        now: str,
    ) -> None:
        for index, raw_entry in enumerate(entries):
            entry = raw_entry if isinstance(raw_entry, dict) else {}
            connection.execute(
                """
                INSERT INTO chat_message_expert_knowledge (
                    conversation_id, message_id, sort_order, title,
                    anchor_description, system_prompt, source_created_at,
                    source_updated_at, created_at, updated_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                [
                    conversation_id,
                    message_id,
                    index,
                    str(entry.get("title") or ""),
                    str(entry.get("anchorDescription") or ""),
                    str(entry.get("systemPrompt") or ""),
                    str(entry.get("createdAt") or ""),
                    str(entry.get("updatedAt") or ""),
                    now,
                    now,
                ],
            )

    def _insert_external_data(
        self,
        connection: sqlite3.Connection,
        conversation_id: str,
        message_id: str,
        entries: list[Any],
        now: str,
    ) -> None:
        for index, raw_entry in enumerate(entries):
            entry = raw_entry if isinstance(raw_entry, dict) else {}
            connection.execute(
                """
                INSERT INTO chat_message_external_data (
                    conversation_id, message_id, sort_order, source,
                    response, created_at, updated_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?)
                """,
                [
                    conversation_id,
                    message_id,
                    index,
                    str(entry.get("source") or ""),
                    str(entry.get("response") or ""),
                    now,
                    now,
                ],
            )

    def _json(self, raw: str, default: Any) -> Any:
        try:
            return json.loads(raw)
        except (json.JSONDecodeError, TypeError):
            return default
