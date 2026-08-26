import sqlite3
import uuid
from typing import Any

from src.features.membership.core.database import get_membership_connection, membership_transaction
from src.features.membership.core.time import utc_now_iso


class GroupRepository:
    def list_groups(self, *, keyword: str = "", status_filter: str = "") -> list[dict[str, Any]]:
        clauses = ["g.deleted_at IS NULL"]
        params: list[Any] = []
        if keyword:
            clauses.append(
                "(LOWER(g.code) LIKE LOWER(?) OR LOWER(g.name) LIKE LOWER(?) "
                "OR LOWER(g.category) LIKE LOWER(?) OR LOWER(g.description) LIKE LOWER(?))"
            )
            pattern = f"%{keyword}%"
            params.extend([pattern, pattern, pattern, pattern])
        if status_filter:
            clauses.append("g.status = ?")
            params.append(status_filter)
        with get_membership_connection() as connection:
            rows = connection.execute(
                f"""
                SELECT g.*, master.username AS master_username,
                       master.display_name AS master_display_name,
                       COUNT(member.id) AS member_count
                FROM membership_group g
                LEFT JOIN membership_user master
                    ON master.id = g.master_user_id AND master.deleted_at IS NULL
                LEFT JOIN membership_group_member member
                    ON member.group_id = g.id AND member.deleted_at IS NULL
                WHERE {' AND '.join(clauses)}
                GROUP BY g.id, master.username, master.display_name
                ORDER BY g.status ASC, g.name ASC, g.code ASC
                """,
                params,
            ).fetchall()
            return [self._group_row(row) for row in rows]

    def get_group(self, group_id: str) -> dict[str, Any] | None:
        with get_membership_connection() as connection:
            row = self._fetch_group(connection, group_id)
            return self._group_row(row) if row else None

    def group_code_exists(self, code: str, *, exclude_id: str | None = None) -> bool:
        clauses = ["LOWER(code) = LOWER(?)", "deleted_at IS NULL"]
        params: list[Any] = [code]
        if exclude_id:
            clauses.append("id != ?")
            params.append(exclude_id)
        with get_membership_connection() as connection:
            row = connection.execute(
                f"SELECT 1 FROM membership_group WHERE {' AND '.join(clauses)} LIMIT 1",
                params,
            ).fetchone()
        return row is not None

    def list_members(self, group_id: str) -> list[dict[str, Any]]:
        with get_membership_connection() as connection:
            return self._list_members(connection, group_id)

    def list_available_users(self) -> list[dict[str, str]]:
        with get_membership_connection() as connection:
            rows = connection.execute(
                """
                SELECT id, username, display_name, email, status
                FROM membership_user
                WHERE deleted_at IS NULL
                ORDER BY display_name ASC, username ASC
                """
            ).fetchall()
            return [
                {
                    "id": row["id"],
                    "username": row["username"],
                    "displayName": row["display_name"],
                    "email": row["email"],
                    "status": row["status"],
                }
                for row in rows
            ]

    def create_group(self, values: dict[str, Any], actor_user_id: str) -> dict[str, Any]:
        group_id = str(uuid.uuid4())
        now = utc_now_iso()
        master_user_id = values.get("masterUserId")
        with membership_transaction() as connection:
            connection.execute(
                """
                INSERT INTO membership_group (
                    id, code, name, category, description, master_user_id,
                    status, created_by_user_id, created_at, updated_at, deleted_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, NULL)
                """,
                [
                    group_id,
                    values["code"],
                    values["name"],
                    values.get("category") or "GENERAL",
                    values.get("description") or "",
                    master_user_id,
                    values.get("status") or "ACTIVE",
                    actor_user_id,
                    now,
                    now,
                ],
            )
            if master_user_id:
                self._insert_member(connection, group_id, master_user_id, actor_user_id, now)
            row = self._fetch_group(connection, group_id)
            group = self._group_row(row) if row else {}
            if group:
                group["members"] = self._list_members(connection, group_id)
        return group

    def update_group(self, group_id: str, values: dict[str, Any], actor_user_id: str) -> dict[str, Any] | None:
        now = utc_now_iso()
        master_user_id = values.get("masterUserId")
        with membership_transaction() as connection:
            cursor = connection.execute(
                """
                UPDATE membership_group
                SET code = ?, name = ?, category = ?, description = ?,
                    master_user_id = ?, status = ?, updated_at = ?
                WHERE id = ? AND deleted_at IS NULL
                """,
                [
                    values["code"],
                    values["name"],
                    values.get("category") or "GENERAL",
                    values.get("description") or "",
                    master_user_id,
                    values.get("status") or "ACTIVE",
                    now,
                    group_id,
                ],
            )
            if cursor.rowcount == 0:
                return None
            if master_user_id:
                active_member = connection.execute(
                    """
                    SELECT 1 FROM membership_group_member
                    WHERE group_id = ? AND user_id = ? AND deleted_at IS NULL
                    """,
                    [group_id, master_user_id],
                ).fetchone()
                if active_member is None:
                    self._insert_member(connection, group_id, master_user_id, actor_user_id, now)
            row = self._fetch_group(connection, group_id)
            group = self._group_row(row) if row else None
            if group is not None:
                group["members"] = self._list_members(connection, group_id)
        return group

    def delete_group(self, group_id: str) -> bool:
        now = utc_now_iso()
        with membership_transaction() as connection:
            cursor = connection.execute(
                """
                UPDATE membership_group
                SET deleted_at = ?, updated_at = ?
                WHERE id = ? AND deleted_at IS NULL
                """,
                [now, now, group_id],
            )
            if cursor.rowcount:
                connection.execute(
                    """
                    UPDATE membership_group_member
                    SET deleted_at = ?, updated_at = ?
                    WHERE group_id = ? AND deleted_at IS NULL
                    """,
                    [now, now, group_id],
                )
            return cursor.rowcount > 0

    def add_members(self, group_id: str, user_ids: list[str], actor_user_id: str) -> None:
        now = utc_now_iso()
        with membership_transaction() as connection:
            for user_id in user_ids:
                exists = connection.execute(
                    """
                    SELECT 1 FROM membership_group_member
                    WHERE group_id = ? AND user_id = ? AND deleted_at IS NULL
                    """,
                    [group_id, user_id],
                ).fetchone()
                if exists is None:
                    self._insert_member(connection, group_id, user_id, actor_user_id, now)

    def remove_member(self, group_id: str, user_id: str) -> bool:
        now = utc_now_iso()
        with membership_transaction() as connection:
            cursor = connection.execute(
                """
                UPDATE membership_group_member
                SET deleted_at = ?, updated_at = ?
                WHERE group_id = ? AND user_id = ? AND deleted_at IS NULL
                """,
                [now, now, group_id, user_id],
            )
            return cursor.rowcount > 0

    def remove_members(self, group_id: str, user_ids: list[str]) -> bool:
        unique_user_ids = list(dict.fromkeys(user_ids))
        if not unique_user_ids:
            return True
        placeholders = ", ".join("?" for _ in unique_user_ids)
        now = utc_now_iso()
        with membership_transaction() as connection:
            existing_ids = {
                row["user_id"]
                for row in connection.execute(
                    f"""
                    SELECT user_id
                    FROM membership_group_member
                    WHERE group_id = ?
                      AND user_id IN ({placeholders})
                      AND deleted_at IS NULL
                    """,
                    [group_id, *unique_user_ids],
                ).fetchall()
            }
            if existing_ids != set(unique_user_ids):
                return False
            connection.executemany(
                """
                UPDATE membership_group_member
                SET deleted_at = ?, updated_at = ?
                WHERE group_id = ? AND user_id = ? AND deleted_at IS NULL
                """,
                [[now, now, group_id, user_id] for user_id in unique_user_ids],
            )
            return True

    def users_exist(self, user_ids: list[str]) -> bool:
        unique_ids = list(dict.fromkeys(user_ids))
        if not unique_ids:
            return True
        placeholders = ", ".join("?" for _ in unique_ids)
        with get_membership_connection() as connection:
            count = connection.execute(
                f"""
                SELECT COUNT(*) AS total FROM membership_user
                WHERE id IN ({placeholders}) AND deleted_at IS NULL
                """,
                unique_ids,
            ).fetchone()["total"]
            return count == len(unique_ids)

    def is_master(self, group_id: str, user_id: str) -> bool:
        with get_membership_connection() as connection:
            return connection.execute(
                """
                SELECT 1 FROM membership_group
                WHERE id = ? AND master_user_id = ? AND deleted_at IS NULL
                """,
                [group_id, user_id],
            ).fetchone() is not None

    def is_any_group_master(self, user_id: str) -> bool:
        with get_membership_connection() as connection:
            return connection.execute(
                """
                SELECT 1 FROM membership_group
                WHERE master_user_id = ? AND deleted_at IS NULL
                LIMIT 1
                """,
                [user_id],
            ).fetchone() is not None

    def _insert_member(
        self,
        connection: sqlite3.Connection,
        group_id: str,
        user_id: str,
        actor_user_id: str,
        now: str,
    ) -> None:
        connection.execute(
            """
            INSERT INTO membership_group_member (
                id, group_id, user_id, added_by_user_id,
                created_at, updated_at, deleted_at
            ) VALUES (?, ?, ?, ?, ?, ?, NULL)
            """,
            [str(uuid.uuid4()), group_id, user_id, actor_user_id, now, now],
        )

    def _fetch_group(self, connection: sqlite3.Connection, group_id: str) -> sqlite3.Row | None:
        return connection.execute(
            """
            SELECT g.*, master.username AS master_username,
                   master.display_name AS master_display_name,
                   COUNT(member.id) AS member_count
            FROM membership_group g
            LEFT JOIN membership_user master
                ON master.id = g.master_user_id AND master.deleted_at IS NULL
            LEFT JOIN membership_group_member member
                ON member.group_id = g.id AND member.deleted_at IS NULL
            WHERE g.id = ? AND g.deleted_at IS NULL
            GROUP BY g.id, master.username, master.display_name
            """,
            [group_id],
        ).fetchone()

    def _list_members(self, connection: sqlite3.Connection, group_id: str) -> list[dict[str, Any]]:
        rows = connection.execute(
            """
            SELECT member.id, member.user_id, member.created_at,
                   member_user.username, member_user.display_name,
                   member_user.email, member_user.status,
                   CASE WHEN group_row.master_user_id = member.user_id THEN 1 ELSE 0 END AS is_master
            FROM membership_group_member member
            JOIN membership_group group_row
                ON group_row.id = member.group_id AND group_row.deleted_at IS NULL
            JOIN membership_user member_user
                ON member_user.id = member.user_id AND member_user.deleted_at IS NULL
            WHERE member.group_id = ? AND member.deleted_at IS NULL
            ORDER BY is_master DESC, member_user.display_name ASC, member_user.username ASC
            """,
            [group_id],
        ).fetchall()
        return [
            {
                "id": row["id"],
                "userId": row["user_id"],
                "username": row["username"],
                "displayName": row["display_name"],
                "email": row["email"],
                "status": row["status"],
                "isMaster": bool(row["is_master"]),
                "createdAt": row["created_at"],
            }
            for row in rows
        ]

    def _group_row(self, row: sqlite3.Row) -> dict[str, Any]:
        return {
            "id": row["id"],
            "code": row["code"],
            "name": row["name"],
            "category": row["category"],
            "description": row["description"],
            "masterUserId": row["master_user_id"],
            "masterUsername": row["master_username"],
            "masterDisplayName": row["master_display_name"],
            "status": row["status"],
            "memberCount": row["member_count"],
            "createdAt": row["created_at"],
            "updatedAt": row["updated_at"],
        }
