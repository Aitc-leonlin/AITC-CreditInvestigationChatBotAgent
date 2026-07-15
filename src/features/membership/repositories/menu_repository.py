import sqlite3
import uuid
from typing import Any

from src.features.membership.core.database import get_membership_connection, membership_transaction
from src.features.membership.core.time import utc_now_iso


class MenuRepository:
    def list_menus(self, *, status_filter: str = "") -> list[dict[str, Any]]:
        params: list[Any] = []
        status_sql = ""
        if status_filter:
            status_sql = "AND m.status = ?"
            params.append(status_filter)
        with get_membership_connection() as connection:
            rows = connection.execute(
                f"""
                SELECT m.*
                FROM membership_menu_item m
                WHERE m.deleted_at IS NULL
                {status_sql}
                ORDER BY m.sort_order ASC, m.title ASC, m.id ASC
                """,
                params,
            ).fetchall()
        return [self.menu_row(row) for row in rows]

    def list_current_menus(self, user_id: str) -> list[dict[str, Any]]:
        with get_membership_connection() as connection:
            rows = connection.execute(
                """
                SELECT DISTINCT m.*
                FROM membership_menu_item m
                LEFT JOIN membership_role_menu_permission rmp
                    ON rmp.menu_item_id = m.id
                   AND rmp.deleted_at IS NULL
                   AND rmp.can_view = 1
                LEFT JOIN membership_user_role ur
                    ON ur.role_id = rmp.role_id
                   AND ur.deleted_at IS NULL
                   AND ur.user_id = ?
                LEFT JOIN membership_role_permission rp
                    ON rp.role_id = ur.role_id
                   AND rp.deleted_at IS NULL
                   AND rp.effect = 'ALLOW'
                LEFT JOIN membership_permission p
                    ON p.id = rp.permission_id
                   AND p.deleted_at IS NULL
                   AND p.status = 'ACTIVE'
                WHERE m.deleted_at IS NULL
                  AND m.status = 'ACTIVE'
                  AND (
                    (ur.user_id IS NOT NULL AND m.required_permission_code IS NULL)
                    OR p.code = m.required_permission_code
                  )
                ORDER BY m.sort_order ASC, m.title ASC, m.id ASC
                """,
                [user_id],
            ).fetchall()
        return [self.menu_row(row) for row in rows]

    def get_menu(self, menu_id: str) -> dict[str, Any] | None:
        with get_membership_connection() as connection:
            row = connection.execute(
                """
                SELECT *
                FROM membership_menu_item
                WHERE id = ? AND deleted_at IS NULL
                """,
                [menu_id],
            ).fetchone()
        return self.menu_row(row) if row else None

    def create_menu(self, values: dict[str, Any]) -> dict[str, Any]:
        menu_id = str(uuid.uuid4())
        now = utc_now_iso()
        payload = {
            "id": menu_id,
            "code": values["code"],
            "title": values["title"],
            "parent_id": values.get("parentId"),
            "route_path": values.get("routePath", ""),
            "component_key": values.get("componentKey", ""),
            "icon": values.get("icon", ""),
            "sort_order": values.get("sortOrder", 0),
            "status": values.get("status", "ACTIVE"),
            "required_permission_code": values.get("requiredPermissionCode"),
            "created_at": now,
            "updated_at": now,
            "deleted_at": None,
        }
        with membership_transaction() as connection:
            self._insert(connection, "membership_menu_item", payload)
        return self.get_menu(menu_id) or payload

    def update_menu(self, menu_id: str, values: dict[str, Any]) -> dict[str, Any] | None:
        payload = {
            "code": values["code"],
            "title": values["title"],
            "parent_id": values.get("parentId"),
            "route_path": values.get("routePath", ""),
            "component_key": values.get("componentKey", ""),
            "icon": values.get("icon", ""),
            "sort_order": values.get("sortOrder", 0),
            "status": values.get("status", "ACTIVE"),
            "required_permission_code": values.get("requiredPermissionCode"),
            "updated_at": utc_now_iso(),
        }
        assignments = ", ".join(f"{column} = ?" for column in payload)
        with membership_transaction() as connection:
            cursor = connection.execute(
                f"UPDATE membership_menu_item SET {assignments} WHERE id = ? AND deleted_at IS NULL",
                [*payload.values(), menu_id],
            )
            if cursor.rowcount == 0:
                return None
        return self.get_menu(menu_id)

    def delete_menu(self, menu_id: str) -> bool:
        now = utc_now_iso()
        with membership_transaction() as connection:
            cursor = connection.execute(
                """
                UPDATE membership_menu_item
                SET deleted_at = ?, updated_at = ?
                WHERE id = ? AND deleted_at IS NULL
                """,
                [now, now, menu_id],
            )
            return cursor.rowcount > 0

    def list_menu_permissions(self, menu_id: str) -> list[dict[str, Any]]:
        with get_membership_connection() as connection:
            rows = connection.execute(
                """
                SELECT rmp.*,
                       r.code AS role_code,
                       r.name AS role_name
                FROM membership_role_menu_permission rmp
                JOIN membership_role r
                    ON r.id = rmp.role_id
                   AND r.deleted_at IS NULL
                WHERE rmp.menu_item_id = ?
                  AND rmp.deleted_at IS NULL
                ORDER BY r.is_system DESC, r.name ASC
                """,
                [menu_id],
            ).fetchall()
        return [self.menu_permission_row(row) for row in rows]

    def set_menu_permission(self, menu_id: str, values: dict[str, Any]) -> dict[str, Any] | None:
        now = utc_now_iso()
        role_id = values["roleId"]
        permission_id = f"role-menu-{role_id}-{menu_id}"
        with membership_transaction() as connection:
            connection.execute(
                """
                INSERT OR REPLACE INTO membership_role_menu_permission (
                    id, role_id, menu_item_id, can_view, can_create, can_update, can_delete,
                    created_at, updated_at, deleted_at
                )
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, NULL)
                """,
                [
                    permission_id,
                    role_id,
                    menu_id,
                    1 if values.get("canView") else 0,
                    1 if values.get("canCreate") else 0,
                    1 if values.get("canUpdate") else 0,
                    1 if values.get("canDelete") else 0,
                    now,
                    now,
                ],
            )
        return self.get_menu_permission(menu_id, role_id)

    def get_menu_permission(self, menu_id: str, role_id: str) -> dict[str, Any] | None:
        with get_membership_connection() as connection:
            row = connection.execute(
                """
                SELECT rmp.*,
                       r.code AS role_code,
                       r.name AS role_name
                FROM membership_role_menu_permission rmp
                JOIN membership_role r
                    ON r.id = rmp.role_id
                   AND r.deleted_at IS NULL
                WHERE rmp.menu_item_id = ?
                  AND rmp.role_id = ?
                  AND rmp.deleted_at IS NULL
                """,
                [menu_id, role_id],
            ).fetchone()
        return self.menu_permission_row(row) if row else None

    def delete_menu_permission(self, menu_id: str, role_id: str) -> bool:
        now = utc_now_iso()
        with membership_transaction() as connection:
            cursor = connection.execute(
                """
                UPDATE membership_role_menu_permission
                SET deleted_at = ?, updated_at = ?
                WHERE menu_item_id = ? AND role_id = ? AND deleted_at IS NULL
                """,
                [now, now, menu_id, role_id],
            )
            return cursor.rowcount > 0

    def code_exists(self, code: str, exclude_id: str | None = None) -> bool:
        params: list[Any] = [code]
        exclude_sql = ""
        if exclude_id:
            exclude_sql = "AND id != ?"
            params.append(exclude_id)
        with get_membership_connection() as connection:
            row = connection.execute(
                f"""
                SELECT id
                FROM membership_menu_item
                WHERE code = ? AND deleted_at IS NULL
                {exclude_sql}
                LIMIT 1
                """,
                params,
            ).fetchone()
        return row is not None

    def role_exists(self, role_id: str) -> bool:
        with get_membership_connection() as connection:
            row = connection.execute(
                "SELECT id FROM membership_role WHERE id = ? AND deleted_at IS NULL",
                [role_id],
            ).fetchone()
        return row is not None

    def permission_code_exists(self, permission_code: str | None) -> bool:
        if not permission_code:
            return True
        with get_membership_connection() as connection:
            row = connection.execute(
                """
                SELECT id
                FROM membership_permission
                WHERE code = ? AND deleted_at IS NULL
                LIMIT 1
                """,
                [permission_code],
            ).fetchone()
        return row is not None

    def has_children(self, menu_id: str) -> bool:
        with get_membership_connection() as connection:
            row = connection.execute(
                """
                SELECT id
                FROM membership_menu_item
                WHERE parent_id = ? AND deleted_at IS NULL
                LIMIT 1
                """,
                [menu_id],
            ).fetchone()
        return row is not None

    def menu_row(self, row: sqlite3.Row) -> dict[str, Any]:
        return {
            "id": row["id"],
            "code": row["code"],
            "title": row["title"],
            "parentId": row["parent_id"],
            "routePath": row["route_path"],
            "componentKey": row["component_key"],
            "icon": row["icon"],
            "sortOrder": row["sort_order"],
            "status": row["status"],
            "requiredPermissionCode": row["required_permission_code"],
            "children": [],
            "createdAt": row["created_at"],
            "updatedAt": row["updated_at"],
        }

    def menu_permission_row(self, row: sqlite3.Row) -> dict[str, Any]:
        return {
            "id": row["id"],
            "menuId": row["menu_item_id"],
            "roleId": row["role_id"],
            "roleCode": row["role_code"],
            "roleName": row["role_name"],
            "canView": bool(row["can_view"]),
            "canCreate": bool(row["can_create"]),
            "canUpdate": bool(row["can_update"]),
            "canDelete": bool(row["can_delete"]),
            "createdAt": row["created_at"],
            "updatedAt": row["updated_at"],
        }

    def _insert(self, connection: sqlite3.Connection, table_name: str, payload: dict[str, Any]) -> None:
        columns = list(payload.keys())
        placeholders = ", ".join("?" for _ in columns)
        column_sql = ", ".join(columns)
        connection.execute(
            f"INSERT INTO {table_name} ({column_sql}) VALUES ({placeholders})",
            [payload[column] for column in columns],
        )
