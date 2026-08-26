import json
import sqlite3
import uuid
from typing import Any

from src.features.membership.core.database import get_membership_connection, membership_transaction
from src.features.membership.core.permission_registry import (
    PERMISSION_CODE_TO_LEGACY_ID,
    permission_by_code,
    permission_exists,
    permission_group_rows,
    permission_rows,
)
from src.features.membership.core.time import utc_now_iso
from src.shared.database.connection import get_table_columns, is_postgresql


class RbacRepository:
    def list_roles(self, *, keyword: str = "", status_filter: str = "") -> list[dict[str, Any]]:
        where_sql, params = self._build_role_filter(keyword, status_filter)
        with get_membership_connection() as connection:
            rows = connection.execute(
                f"""
                SELECT r.*,
                       COUNT(DISTINCT ur.user_id) AS user_count,
                       COUNT(DISTINCT rp.permission_code) AS permission_count
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
                       COUNT(DISTINCT rp.permission_code) AS permission_count
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
            "code": self._build_role_code(role_id, values["name"]),
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
            "code": self._build_role_code(role_id, values["name"]),
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
        return permission_group_rows()

    def create_permission_group(self, values: dict[str, Any]) -> dict[str, Any]:
        raise RuntimeError("Permission groups are code-defined and cannot be stored in DB.")

    def get_permission_group(self, group_id: str) -> dict[str, Any] | None:
        return next((group for group in permission_group_rows() if group["id"] == group_id), None)

    def update_permission_group(self, group_id: str, values: dict[str, Any]) -> dict[str, Any] | None:
        raise RuntimeError("Permission groups are code-defined and cannot be stored in DB.")

    def delete_permission_group(self, group_id: str) -> bool:
        raise RuntimeError("Permission groups are code-defined and cannot be stored in DB.")

    def list_permissions(self, *, keyword: str = "", group_id: str = "", status_filter: str = "") -> list[dict[str, Any]]:
        return permission_rows(keyword=keyword, group_id=group_id, status_filter=status_filter)

    def get_permission(self, permission_id: str) -> dict[str, Any] | None:
        return permission_by_code(permission_id)

    def create_permission(self, values: dict[str, Any]) -> dict[str, Any]:
        raise RuntimeError("Permissions are code-defined and cannot be stored in DB.")

    def update_permission(self, permission_id: str, values: dict[str, Any]) -> dict[str, Any] | None:
        raise RuntimeError("Permissions are code-defined and cannot be stored in DB.")

    def delete_permission(self, permission_id: str) -> bool:
        raise RuntimeError("Permissions are code-defined and cannot be stored in DB.")

    def get_role_permission_codes(self, role_id: str) -> list[str]:
        with get_membership_connection() as connection:
            rows = connection.execute(
                """
                SELECT permission_code
                FROM membership_role_permission
                WHERE role_id = ?
                  AND permission_code IS NOT NULL
                  AND permission_code != ''
                  AND deleted_at IS NULL
                  AND effect = 'ALLOW'
                ORDER BY permission_code
                """,
                [role_id],
            ).fetchall()
        return [row["permission_code"] for row in rows]

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
            columns = self._table_columns(connection, "membership_role_permission")
            for permission_id in permission_ids:
                payload = {
                    "id": f"role-permission-{role_id}-{permission_id}",
                    "role_id": role_id,
                    "permission_code": permission_id,
                    "effect": "ALLOW",
                    "created_at": now,
                    "updated_at": now,
                    "deleted_at": None,
                }
                if "permission_id" in columns:
                    payload["permission_id"] = PERMISSION_CODE_TO_LEGACY_ID.get(permission_id, permission_id)
                self._insert_or_replace(connection, "membership_role_permission", payload)
            self._insert_notification(
                connection,
                recipient_user_id=None,
                payload={
                    "roleId": role_id,
                    "permissionIds": permission_ids,
                    "changeType": "role_permissions",
                },
            )
        return self.get_role_permission_codes(role_id)

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
                self._insert_or_replace(connection, "membership_user_role", {
                    "id": f"user-role-{user_id}-{role_id}",
                    "user_id": user_id,
                    "role_id": role_id,
                    "organization_id": organization_id,
                    "effective_from": now,
                    "effective_to": None,
                    "created_at": now,
                    "updated_at": now,
                    "deleted_at": None,
                })
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
                SELECT DISTINCT rp.permission_code
                FROM membership_user_role ur
                JOIN membership_role r
                    ON r.id = ur.role_id
                   AND r.deleted_at IS NULL
                   AND r.status = 'ACTIVE'
                JOIN membership_role_permission rp
                    ON rp.role_id = r.id
                   AND rp.deleted_at IS NULL
                   AND rp.effect = 'ALLOW'
                WHERE ur.user_id = ?
                  AND ur.deleted_at IS NULL
                  AND rp.permission_code IS NOT NULL
                  AND rp.permission_code != ''
                ORDER BY rp.permission_code
                """,
                [user_id],
            ).fetchall()
        return [row["permission_code"] for row in rows]

    def has_permission(self, user_id: str, permission_code: str) -> bool:
        return permission_code in self.list_user_permissions(user_id)

    def role_exists(self, role_id: str) -> bool:
        return self.get_role(role_id) is not None

    def permission_ids_exist(self, permission_ids: list[str]) -> bool:
        return all(permission_exists(permission_id) for permission_id in permission_ids)

    def role_ids_exist(self, role_ids: list[str]) -> bool:
        if not role_ids:
            print("[membership.rbac.role_ids_exist]", {"role_ids": [], "exists": True}, flush=True)
            return True
        placeholders = ", ".join("?" for _ in role_ids)
        with get_membership_connection() as connection:
            rows = connection.execute(
                f"""
                SELECT id, code, name, status, deleted_at
                FROM membership_role
                WHERE id IN ({placeholders}) AND deleted_at IS NULL
                """,
                role_ids,
            ).fetchall()
        found_ids = {row["id"] for row in rows}
        unique_role_ids = set(role_ids)
        missing_ids = sorted(unique_role_ids - found_ids)
        exists = len(found_ids) == len(unique_role_ids)
        print(
            "[membership.rbac.role_ids_exist]",
            {
                "role_ids": role_ids,
                "unique_role_ids": sorted(unique_role_ids),
                "found_count": len(found_ids),
                "expected_count": len(unique_role_ids),
                "missing_ids": missing_ids,
                "found_roles": [
                    {
                        "id": row["id"],
                        "code": row["code"],
                        "name": row["name"],
                        "status": row["status"],
                    }
                    for row in rows
                ],
                "exists": exists,
            },
            flush=True,
        )
        return exists

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
            "moduleName": row["module_name"],
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

    def _insert_or_replace(self, connection: sqlite3.Connection, table_name: str, payload: dict[str, Any]) -> None:
        columns = list(payload.keys())
        placeholders = ", ".join("?" for _ in columns)
        if is_postgresql():
            update_columns = [column for column in columns if column != "id"]
            assignments = ", ".join(
                f"{column} = EXCLUDED.{column}" for column in update_columns
            )
            connection.execute(
                f"INSERT INTO {table_name} ({', '.join(columns)}) VALUES ({placeholders}) "
                f"ON CONFLICT (id) DO UPDATE SET {assignments}",
                [payload[column] for column in columns],
            )
            return
        connection.execute(
            f"INSERT OR REPLACE INTO {table_name} ({', '.join(columns)}) VALUES ({placeholders})",
            [payload[column] for column in columns],
        )

    def _table_columns(self, connection: sqlite3.Connection, table_name: str) -> set[str]:
        return get_table_columns(connection, table_name)

    def _build_role_code(self, role_id: str, name: str) -> str:
        normalized_name = "_".join(name.split())
        return f"{role_id}_{normalized_name}"

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
