import json
import sqlite3
import uuid
from typing import Any

from src.features.membership.core.database import get_membership_connection, membership_transaction
from src.features.membership.core.time import utc_now_iso


class RbacRepository:
    def list_roles(self, *, keyword: str = "", status_filter: str = "") -> list[dict[str, Any]]:
        where_sql, params = self._build_role_filter(keyword, status_filter)
        with get_membership_connection() as connection:
            rows = connection.execute(
                f"""
                SELECT r.*,
                       COUNT(DISTINCT ur.user_id) AS user_count,
                       COUNT(DISTINCT rp.permission_id) AS permission_count
                FROM membership_role r
                LEFT JOIN membership_user_role ur
                    ON ur.role_id = r.id AND ur.deleted_at IS NULL
                LEFT JOIN membership_role_permission rp
                    ON rp.role_id = r.id AND rp.deleted_at IS NULL AND rp.effect = 'ALLOW'
                WHERE r.deleted_at IS NULL
                {where_sql}
                GROUP BY r.id
                ORDER BY r.is_system DESC, r.created_at DESC, r.id DESC
                """,
                params,
            ).fetchall()
        return [self.role_row(row) for row in rows]

    def get_role(self, role_id: str) -> dict[str, Any] | None:
        with get_membership_connection() as connection:
            row = connection.execute(
                """
                SELECT r.*,
                       COUNT(DISTINCT ur.user_id) AS user_count,
                       COUNT(DISTINCT rp.permission_id) AS permission_count
                FROM membership_role r
                LEFT JOIN membership_user_role ur
                    ON ur.role_id = r.id AND ur.deleted_at IS NULL
                LEFT JOIN membership_role_permission rp
                    ON rp.role_id = r.id AND rp.deleted_at IS NULL AND rp.effect = 'ALLOW'
                WHERE r.id = ? AND r.deleted_at IS NULL
                GROUP BY r.id
                """,
                [role_id],
            ).fetchone()
        return self.role_row(row) if row else None

    def create_role(self, values: dict[str, Any]) -> dict[str, Any]:
        role_id = str(uuid.uuid4())
        now = utc_now_iso()
        payload = {
            "id": role_id,
            "code": values["code"],
            "name": values["name"],
            "description": values.get("description", ""),
            "role_type": values.get("roleType", "BUSINESS"),
            "status": values.get("status", "ACTIVE"),
            "is_system": 1 if values.get("isSystem") else 0,
            "created_at": now,
            "updated_at": now,
            "deleted_at": None,
        }
        with membership_transaction() as connection:
            self._insert(connection, "membership_role", payload)
        return self.get_role(role_id) or payload

    def update_role(self, role_id: str, values: dict[str, Any]) -> dict[str, Any] | None:
        payload = {
            "code": values["code"],
            "name": values["name"],
            "description": values.get("description", ""),
            "role_type": values.get("roleType", "BUSINESS"),
            "status": values.get("status", "ACTIVE"),
            "updated_at": utc_now_iso(),
        }
        assignments = ", ".join(f"{column} = ?" for column in payload)
        with membership_transaction() as connection:
            cursor = connection.execute(
                f"UPDATE membership_role SET {assignments} WHERE id = ? AND deleted_at IS NULL",
                [*payload.values(), role_id],
            )
            if cursor.rowcount == 0:
                return None
        return self.get_role(role_id)

    def delete_role(self, role_id: str) -> bool:
        now = utc_now_iso()
        with membership_transaction() as connection:
            cursor = connection.execute(
                """
                UPDATE membership_role
                SET deleted_at = ?, updated_at = ?
                WHERE id = ? AND deleted_at IS NULL AND is_system = 0
                """,
                [now, now, role_id],
            )
            return cursor.rowcount > 0

    def list_permission_groups(self) -> list[dict[str, Any]]:
        with get_membership_connection() as connection:
            rows = connection.execute(
                """
                SELECT g.*,
                       COUNT(p.id) AS permission_count
                FROM membership_permission_group g
                LEFT JOIN membership_permission p
                    ON p.group_id = g.id AND p.deleted_at IS NULL
                WHERE g.deleted_at IS NULL
                GROUP BY g.id
                ORDER BY g.code ASC
                """
            ).fetchall()
        return [self.permission_group_row(row) for row in rows]

    def create_permission_group(self, values: dict[str, Any]) -> dict[str, Any]:
        group_id = str(uuid.uuid4())
        now = utc_now_iso()
        payload = {
            "id": group_id,
            "code": values["code"],
            "name": values["name"],
            "description": values.get("description", ""),
            "status": values.get("status", "ACTIVE"),
            "created_at": now,
            "updated_at": now,
            "deleted_at": None,
        }
        with membership_transaction() as connection:
            self._insert(connection, "membership_permission_group", payload)
        return self.get_permission_group(group_id) or payload

    def get_permission_group(self, group_id: str) -> dict[str, Any] | None:
        with get_membership_connection() as connection:
            row = connection.execute(
                """
                SELECT g.*,
                       COUNT(p.id) AS permission_count
                FROM membership_permission_group g
                LEFT JOIN membership_permission p
                    ON p.group_id = g.id AND p.deleted_at IS NULL
                WHERE g.id = ? AND g.deleted_at IS NULL
                GROUP BY g.id
                """,
                [group_id],
            ).fetchone()
        return self.permission_group_row(row) if row else None

    def update_permission_group(self, group_id: str, values: dict[str, Any]) -> dict[str, Any] | None:
        payload = {
            "code": values["code"],
            "name": values["name"],
            "description": values.get("description", ""),
            "status": values.get("status", "ACTIVE"),
            "updated_at": utc_now_iso(),
        }
        assignments = ", ".join(f"{column} = ?" for column in payload)
        with membership_transaction() as connection:
            cursor = connection.execute(
                f"UPDATE membership_permission_group SET {assignments} WHERE id = ? AND deleted_at IS NULL",
                [*payload.values(), group_id],
            )
            if cursor.rowcount == 0:
                return None
        return self.get_permission_group(group_id)

    def delete_permission_group(self, group_id: str) -> bool:
        now = utc_now_iso()
        with membership_transaction() as connection:
            cursor = connection.execute(
                """
                UPDATE membership_permission_group
                SET deleted_at = ?, updated_at = ?
                WHERE id = ? AND deleted_at IS NULL
                """,
                [now, now, group_id],
            )
            return cursor.rowcount > 0

    def list_permissions(self, *, keyword: str = "", group_id: str = "", status_filter: str = "") -> list[dict[str, Any]]:
        where_sql, params = self._build_permission_filter(keyword, group_id, status_filter)
        with get_membership_connection() as connection:
            rows = connection.execute(
                f"""
                SELECT p.*,
                       g.code AS group_code,
                       g.name AS group_name
                FROM membership_permission p
                LEFT JOIN membership_permission_group g
                    ON g.id = p.group_id AND g.deleted_at IS NULL
                WHERE p.deleted_at IS NULL
                {where_sql}
                ORDER BY COALESCE(g.code, 'ZZZZZZZZ'), p.action, p.code
                """,
                params,
            ).fetchall()
        return [self.permission_row(row) for row in rows]

    def get_permission(self, permission_id: str) -> dict[str, Any] | None:
        with get_membership_connection() as connection:
            row = connection.execute(
                """
                SELECT p.*,
                       g.code AS group_code,
                       g.name AS group_name
                FROM membership_permission p
                LEFT JOIN membership_permission_group g
                    ON g.id = p.group_id AND g.deleted_at IS NULL
                WHERE p.id = ? AND p.deleted_at IS NULL
                """,
                [permission_id],
            ).fetchone()
        return self.permission_row(row) if row else None

    def create_permission(self, values: dict[str, Any]) -> dict[str, Any]:
        permission_id = str(uuid.uuid4())
        now = utc_now_iso()
        payload = {
            "id": permission_id,
            "code": values["code"],
            "name": values["name"],
            "description": values.get("description", ""),
            "action": values["action"],
            "status": values.get("status", "ACTIVE"),
            "group_id": values.get("groupId"),
            "created_at": now,
            "updated_at": now,
            "deleted_at": None,
        }
        with membership_transaction() as connection:
            self._insert(connection, "membership_permission", payload)
        return self.get_permission(permission_id) or payload

    def update_permission(self, permission_id: str, values: dict[str, Any]) -> dict[str, Any] | None:
        payload = {
            "code": values["code"],
            "name": values["name"],
            "description": values.get("description", ""),
            "action": values["action"],
            "status": values.get("status", "ACTIVE"),
            "group_id": values.get("groupId"),
            "updated_at": utc_now_iso(),
        }
        assignments = ", ".join(f"{column} = ?" for column in payload)
        with membership_transaction() as connection:
            cursor = connection.execute(
                f"UPDATE membership_permission SET {assignments} WHERE id = ? AND deleted_at IS NULL",
                [*payload.values(), permission_id],
            )
            if cursor.rowcount == 0:
                return None
        return self.get_permission(permission_id)

    def delete_permission(self, permission_id: str) -> bool:
        now = utc_now_iso()
        with membership_transaction() as connection:
            cursor = connection.execute(
                """
                UPDATE membership_permission
                SET deleted_at = ?, updated_at = ?
                WHERE id = ? AND deleted_at IS NULL
                """,
                [now, now, permission_id],
            )
            return cursor.rowcount > 0

    def get_role_permission_ids(self, role_id: str) -> list[str]:
        with get_membership_connection() as connection:
            rows = connection.execute(
                """
                SELECT permission_id
                FROM membership_role_permission
                WHERE role_id = ? AND deleted_at IS NULL AND effect = 'ALLOW'
                """,
                [role_id],
            ).fetchall()
        return [row["permission_id"] for row in rows]

    def set_role_permissions(self, role_id: str, permission_ids: list[str]) -> list[str]:
        now = utc_now_iso()
        with membership_transaction() as connection:
            connection.execute(
                """
                UPDATE membership_role_permission
                SET deleted_at = ?, updated_at = ?
                WHERE role_id = ? AND deleted_at IS NULL
                """,
                [now, now, role_id],
            )
            for permission_id in permission_ids:
                connection.execute(
                    """
                    INSERT OR REPLACE INTO membership_role_permission (
                        id, role_id, permission_id, effect, created_at, updated_at, deleted_at
                    )
                    VALUES (?, ?, ?, 'ALLOW', ?, ?, NULL)
                    """,
                    [f"role-permission-{role_id}-{permission_id}", role_id, permission_id, now, now],
                )
            self._insert_notification(
                connection,
                recipient_user_id=None,
                payload={
                    "roleId": role_id,
                    "permissionIds": permission_ids,
                    "changeType": "role_permissions",
                },
            )
        return self.get_role_permission_ids(role_id)

    def get_user_role_ids(self, user_id: str) -> list[str]:
        with get_membership_connection() as connection:
            rows = connection.execute(
                """
                SELECT role_id
                FROM membership_user_role
                WHERE user_id = ? AND deleted_at IS NULL
                """,
                [user_id],
            ).fetchall()
        return [row["role_id"] for row in rows]

    def set_user_roles(self, user_id: str, role_ids: list[str], organization_id: str | None = None) -> list[str]:
        now = utc_now_iso()
        with membership_transaction() as connection:
            connection.execute(
                """
                UPDATE membership_user_role
                SET deleted_at = ?, updated_at = ?
                WHERE user_id = ? AND deleted_at IS NULL
                """,
                [now, now, user_id],
            )
            for role_id in role_ids:
                connection.execute(
                    """
                    INSERT OR REPLACE INTO membership_user_role (
                        id, user_id, role_id, organization_id, effective_from,
                        effective_to, created_at, updated_at, deleted_at
                    )
                    VALUES (?, ?, ?, ?, ?, NULL, ?, ?, NULL)
                    """,
                    [f"user-role-{user_id}-{role_id}", user_id, role_id, organization_id, now, now, now],
                )
            self._insert_notification(
                connection,
                recipient_user_id=user_id,
                payload={
                    "userId": user_id,
                    "roleIds": role_ids,
                    "organizationId": organization_id,
                    "changeType": "user_roles",
                },
            )
        return self.get_user_role_ids(user_id)

    def list_user_permissions(self, user_id: str) -> list[str]:
        with get_membership_connection() as connection:
            rows = connection.execute(
                """
                SELECT DISTINCT p.code
                FROM membership_user_role ur
                JOIN membership_role r
                    ON r.id = ur.role_id
                   AND r.deleted_at IS NULL
                   AND r.status = 'ACTIVE'
                JOIN membership_role_permission rp
                    ON rp.role_id = r.id
                   AND rp.deleted_at IS NULL
                   AND rp.effect = 'ALLOW'
                JOIN membership_permission p
                    ON p.id = rp.permission_id
                   AND p.deleted_at IS NULL
                   AND p.status = 'ACTIVE'
                WHERE ur.user_id = ?
                  AND ur.deleted_at IS NULL
                ORDER BY p.code
                """,
                [user_id],
            ).fetchall()
        return [row["code"] for row in rows]

    def has_permission(self, user_id: str, permission_code: str) -> bool:
        return permission_code in self.list_user_permissions(user_id)

    def role_exists(self, role_id: str) -> bool:
        return self.get_role(role_id) is not None

    def permission_ids_exist(self, permission_ids: list[str]) -> bool:
        if not permission_ids:
            return True
        placeholders = ", ".join("?" for _ in permission_ids)
        with get_membership_connection() as connection:
            count = connection.execute(
                f"""
                SELECT COUNT(*) AS total
                FROM membership_permission
                WHERE id IN ({placeholders}) AND deleted_at IS NULL
                """,
                permission_ids,
            ).fetchone()["total"]
        return count == len(set(permission_ids))

    def role_ids_exist(self, role_ids: list[str]) -> bool:
        if not role_ids:
            return True
        placeholders = ", ".join("?" for _ in role_ids)
        with get_membership_connection() as connection:
            count = connection.execute(
                f"""
                SELECT COUNT(*) AS total
                FROM membership_role
                WHERE id IN ({placeholders}) AND deleted_at IS NULL
                """,
                role_ids,
            ).fetchone()["total"]
        return count == len(set(role_ids))

    def user_exists(self, user_id: str) -> bool:
        with get_membership_connection() as connection:
            row = connection.execute(
                "SELECT id FROM membership_user WHERE id = ? AND deleted_at IS NULL",
                [user_id],
            ).fetchone()
        return row is not None

    def code_exists(self, table_name: str, code: str, exclude_id: str | None = None) -> bool:
        params: list[Any] = [code]
        exclude_sql = ""
        if exclude_id:
            exclude_sql = "AND id != ?"
            params.append(exclude_id)
        with get_membership_connection() as connection:
            row = connection.execute(
                f"""
                SELECT id
                FROM {table_name}
                WHERE code = ? AND deleted_at IS NULL
                {exclude_sql}
                LIMIT 1
                """,
                params,
            ).fetchone()
        return row is not None

    def role_row(self, row: sqlite3.Row) -> dict[str, Any]:
        return {
            "id": row["id"],
            "code": row["code"],
            "name": row["name"],
            "description": row["description"],
            "roleType": row["role_type"],
            "status": row["status"],
            "isSystem": bool(row["is_system"]),
            "userCount": row["user_count"],
            "permissionCount": row["permission_count"],
            "createdAt": row["created_at"],
            "updatedAt": row["updated_at"],
        }

    def permission_group_row(self, row: sqlite3.Row) -> dict[str, Any]:
        return {
            "id": row["id"],
            "code": row["code"],
            "name": row["name"],
            "description": row["description"],
            "status": row["status"],
            "permissionCount": row["permission_count"],
            "createdAt": row["created_at"],
            "updatedAt": row["updated_at"],
        }

    def permission_row(self, row: sqlite3.Row) -> dict[str, Any]:
        return {
            "id": row["id"],
            "code": row["code"],
            "name": row["name"],
            "description": row["description"],
            "action": row["action"],
            "status": row["status"],
            "groupId": row["group_id"],
            "groupCode": row["group_code"],
            "groupName": row["group_name"],
            "createdAt": row["created_at"],
            "updatedAt": row["updated_at"],
        }

    def _build_role_filter(self, keyword: str, status_filter: str) -> tuple[str, list[Any]]:
        clauses: list[str] = []
        params: list[Any] = []
        normalized_keyword = " ".join(keyword.split())
        if normalized_keyword:
            like_keyword = f"%{normalized_keyword}%"
            clauses.append("(r.code LIKE ? OR r.name LIKE ? OR r.description LIKE ?)")
            params.extend([like_keyword] * 3)
        if status_filter.strip():
            clauses.append("r.status = ?")
            params.append(status_filter.strip().upper())
        return ("AND " + " AND ".join(clauses), params) if clauses else ("", [])

    def _build_permission_filter(
        self,
        keyword: str,
        group_id: str,
        status_filter: str,
    ) -> tuple[str, list[Any]]:
        clauses: list[str] = []
        params: list[Any] = []
        normalized_keyword = " ".join(keyword.split())
        if normalized_keyword:
            like_keyword = f"%{normalized_keyword}%"
            clauses.append("(p.code LIKE ? OR p.name LIKE ? OR p.action LIKE ?)")
            params.extend([like_keyword] * 3)
        if group_id.strip():
            clauses.append("p.group_id = ?")
            params.append(group_id.strip())
        if status_filter.strip():
            clauses.append("p.status = ?")
            params.append(status_filter.strip().upper())
        return ("AND " + " AND ".join(clauses), params) if clauses else ("", [])

    def _insert(self, connection: sqlite3.Connection, table_name: str, payload: dict[str, Any]) -> None:
        columns = list(payload.keys())
        placeholders = ", ".join("?" for _ in columns)
        connection.execute(
            f"INSERT INTO {table_name} ({', '.join(columns)}) VALUES ({placeholders})",
            [payload[column] for column in columns],
        )

    def _insert_notification(
        self,
        connection: sqlite3.Connection,
        *,
        recipient_user_id: str | None,
        payload: dict[str, Any],
    ) -> None:
        now = utc_now_iso()
        connection.execute(
            """
            INSERT INTO membership_notification_outbox (
                id, template_code, recipient_user_id, channel, payload_json,
                status, created_at, updated_at
            )
            VALUES (?, 'RBAC_PERMISSION_CHANGED', ?, 'EMAIL', ?, 'PENDING', ?, ?)
            """,
            [
                str(uuid.uuid4()),
                recipient_user_id,
                json.dumps(payload, ensure_ascii=False),
                now,
                now,
            ],
        )
