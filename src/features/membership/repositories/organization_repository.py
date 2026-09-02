import uuid
from typing import Any

from src.features.membership.core.database import get_membership_connection, membership_transaction
from src.features.membership.core.time import utc_now_iso
from src.shared.database.connection import DatabaseRow, SQLAlchemyConnectionAdapter


class OrganizationRepository:
    def list_units(self, *, keyword: str = "", unit_type: str = "", status_filter: str = "") -> list[dict[str, Any]]:
        where_sql, params = self._unit_filter(keyword, unit_type, status_filter)
        with get_membership_connection() as connection:
            rows = connection.execute(
                f"""
                SELECT o.*, manager.display_name AS manager_display_name
                FROM membership_organization_unit o
                LEFT JOIN membership_user manager
                    ON manager.id = o.manager_user_id AND manager.deleted_at IS NULL
                WHERE o.deleted_at IS NULL
                {where_sql}
                ORDER BY o.path ASC, o.code ASC
                """,
                params,
            ).fetchall()
        return [self.unit_row(row) for row in rows]

    def get_unit(self, unit_id: str) -> dict[str, Any] | None:
        with get_membership_connection() as connection:
            row = connection.execute(
                """
                SELECT o.*, manager.display_name AS manager_display_name
                FROM membership_organization_unit o
                LEFT JOIN membership_user manager
                    ON manager.id = o.manager_user_id AND manager.deleted_at IS NULL
                WHERE o.id = ? AND o.deleted_at IS NULL
                """,
                [unit_id],
            ).fetchone()
        return self.unit_row(row) if row else None

    def create_unit(self, values: dict[str, Any]) -> dict[str, Any]:
        unit_id = str(uuid.uuid4())
        now = utc_now_iso()
        parent = self.get_unit(values.get("parentId") or "") if values.get("parentId") else None
        code = values["code"]
        path = f"{parent['path'] if parent else ''}/{code}".replace("//", "/")
        unit_type = values.get("unitType", "DEPARTMENT")
        payload = {
            "id": unit_id,
            "code": code,
            "name": values["name"],
            "parent_id": values.get("parentId"),
            "path": path,
            "level": (parent["level"] + 1) if parent else 0,
            "status": values.get("status", "ACTIVE"),
            "unit_type": unit_type,
            "company_id": self._resolve_company_id(unit_id, unit_type, parent),
            "manager_user_id": values.get("managerUserId"),
            "description": values.get("description", ""),
            "created_at": now,
            "updated_at": now,
            "deleted_at": None,
        }
        with membership_transaction() as connection:
            self._insert(connection, "membership_organization_unit", payload)
        return self.get_unit(unit_id) or payload

    def update_unit(self, unit_id: str, values: dict[str, Any]) -> dict[str, Any] | None:
        current = self.get_unit(unit_id)
        if current is None:
            return None
        parent = self.get_unit(values.get("parentId") or "") if values.get("parentId") else None
        code = values["code"]
        path = f"{parent['path'] if parent else ''}/{code}".replace("//", "/")
        level = (parent["level"] + 1) if parent else 0
        unit_type = values.get("unitType", "DEPARTMENT")
        company_id = self._resolve_company_id(unit_id, unit_type, parent)
        now = utc_now_iso()
        payload = {
            "code": code,
            "name": values["name"],
            "parent_id": values.get("parentId"),
            "path": path,
            "level": level,
            "status": values.get("status", "ACTIVE"),
            "unit_type": unit_type,
            "company_id": company_id,
            "manager_user_id": values.get("managerUserId"),
            "description": values.get("description", ""),
            "updated_at": now,
        }
        assignments = ", ".join(f"{column} = ?" for column in payload)
        with membership_transaction() as connection:
            subtree_rows = connection.execute(
                """
                WITH RECURSIVE organization_tree AS (
                    SELECT id, code, parent_id, path, level, unit_type
                    FROM membership_organization_unit
                    WHERE id = ? AND deleted_at IS NULL

                    UNION ALL

                    SELECT child.id, child.code, child.parent_id, child.path, child.level, child.unit_type
                    FROM membership_organization_unit child
                    JOIN organization_tree parent ON child.parent_id = parent.id
                    WHERE child.deleted_at IS NULL
                )
                SELECT id, code, parent_id, path, level, unit_type
                FROM organization_tree
                ORDER BY level ASC, id ASC
                """,
                [unit_id],
            ).fetchall()
            cursor = connection.execute(
                f"UPDATE membership_organization_unit SET {assignments} WHERE id = ? AND deleted_at IS NULL",
                [*payload.values(), unit_id],
            )
            if cursor.rowcount == 0:
                return None
            subtree_paths = {unit_id: path}
            subtree_levels = {unit_id: level}
            subtree_company_ids: dict[str, str | None] = {unit_id: company_id}
            descendant_updates: list[list[Any]] = []
            for row in subtree_rows:
                descendant_id = row["id"]
                if descendant_id == unit_id:
                    continue
                descendant_parent_id = row["parent_id"]
                parent_path = subtree_paths[descendant_parent_id]
                descendant_path = f"{parent_path}/{row['code']}"
                descendant_level = subtree_levels[descendant_parent_id] + 1
                descendant_company_id = (
                    descendant_id
                    if row["unit_type"] == "COMPANY"
                    else subtree_company_ids[descendant_parent_id]
                )
                subtree_paths[descendant_id] = descendant_path
                subtree_levels[descendant_id] = descendant_level
                subtree_company_ids[descendant_id] = descendant_company_id
                descendant_updates.append(
                    [descendant_path, descendant_level, descendant_company_id, now, descendant_id]
                )
            if descendant_updates:
                connection.executemany(
                    """
                    UPDATE membership_organization_unit
                    SET path = ?, level = ?, company_id = ?, updated_at = ?
                    WHERE id = ? AND deleted_at IS NULL
                    """,
                    descendant_updates,
                )
        return self.get_unit(unit_id)

    @staticmethod
    def _resolve_company_id(
        unit_id: str,
        unit_type: str,
        parent: dict[str, Any] | None,
    ) -> str | None:
        if unit_type == "COMPANY":
            return unit_id
        if parent is None:
            return None
        if parent["unitType"] == "COMPANY":
            return parent["id"]
        return parent["companyId"]

    def delete_unit_tree(self, unit_id: str) -> dict[str, int]:
        now = utc_now_iso()
        with membership_transaction() as connection:
            rows = connection.execute(
                """
                WITH RECURSIVE organization_tree(id) AS (
                    SELECT id
                    FROM membership_organization_unit
                    WHERE id = ? AND deleted_at IS NULL

                    UNION ALL

                    SELECT child.id
                    FROM membership_organization_unit child
                    JOIN organization_tree parent ON child.parent_id = parent.id
                    WHERE child.deleted_at IS NULL
                )
                SELECT id FROM organization_tree
                """,
                [unit_id],
            ).fetchall()
            unit_ids = [row["id"] for row in rows]
            if not unit_ids:
                return {"deletedCount": 0, "detachedUserCount": 0}

            placeholders = ", ".join("?" for _ in unit_ids)
            detached_users = connection.execute(
                f"""
                UPDATE membership_user
                SET organization_id = NULL, updated_at = ?
                WHERE organization_id IN ({placeholders}) AND deleted_at IS NULL
                """,
                [now, *unit_ids],
            ).rowcount
            connection.execute(
                f"""
                UPDATE membership_user_role
                SET deleted_at = ?, updated_at = ?
                WHERE organization_id IN ({placeholders}) AND deleted_at IS NULL
                """,
                [now, now, *unit_ids],
            )
            connection.execute(
                f"""
                UPDATE membership_user_department_mapping
                SET deleted_at = ?, updated_at = ?
                WHERE organization_id IN ({placeholders}) AND deleted_at IS NULL
                """,
                [now, now, *unit_ids],
            )
            connection.execute(
                f"""
                UPDATE membership_user_manager_relation
                SET deleted_at = ?, updated_at = ?
                WHERE organization_id IN ({placeholders}) AND deleted_at IS NULL
                """,
                [now, now, *unit_ids],
            )
            connection.execute(
                f"""
                UPDATE membership_data_scope
                SET deleted_at = ?, updated_at = ?
                WHERE organization_id IN ({placeholders}) AND deleted_at IS NULL
                """,
                [now, now, *unit_ids],
            )
            connection.execute(
                f"""
                UPDATE membership_organization_unit
                SET company_id = NULL, updated_at = ?
                WHERE company_id IN ({placeholders})
                  AND id NOT IN ({placeholders})
                  AND deleted_at IS NULL
                """,
                [now, *unit_ids, *unit_ids],
            )
            deleted_count = connection.execute(
                f"""
                UPDATE membership_organization_unit
                SET deleted_at = ?, updated_at = ?
                WHERE id IN ({placeholders}) AND deleted_at IS NULL
                """,
                [now, now, *unit_ids],
            ).rowcount
            return {
                "deletedCount": deleted_count,
                "detachedUserCount": detached_users,
            }

    def list_positions(self, *, keyword: str = "", status_filter: str = "") -> list[dict[str, Any]]:
        where_sql, params = self._position_filter(keyword, status_filter)
        with get_membership_connection() as connection:
            rows = connection.execute(
                f"""
                SELECT p.*
                FROM membership_position p
                WHERE p.deleted_at IS NULL
                {where_sql}
                ORDER BY p.level DESC, p.name ASC
                """,
                params,
            ).fetchall()
        return [self.position_row(row) for row in rows]

    def get_position(self, position_id: str) -> dict[str, Any] | None:
        with get_membership_connection() as connection:
            row = connection.execute(
                """
                SELECT p.*
                FROM membership_position p
                WHERE p.id = ? AND p.deleted_at IS NULL
                """,
                [position_id],
            ).fetchone()
        return self.position_row(row) if row else None

    def create_position(self, values: dict[str, Any]) -> dict[str, Any]:
        position_id = str(uuid.uuid4())
        now = utc_now_iso()
        payload = {
            "id": position_id,
            "name": values["name"],
            "description": values.get("description", ""),
            "level": values.get("level", 0),
            "status": values.get("status", "ACTIVE"),
            "created_at": now,
            "updated_at": now,
            "deleted_at": None,
        }
        with membership_transaction() as connection:
            self._insert(connection, "membership_position", payload)
        return self.get_position(position_id) or payload

    def update_position(self, position_id: str, values: dict[str, Any]) -> dict[str, Any] | None:
        payload = {
            "name": values["name"],
            "description": values.get("description", ""),
            "level": values.get("level", 0),
            "status": values.get("status", "ACTIVE"),
            "updated_at": utc_now_iso(),
        }
        assignments = ", ".join(f"{column} = ?" for column in payload)
        with membership_transaction() as connection:
            cursor = connection.execute(
                f"UPDATE membership_position SET {assignments} WHERE id = ? AND deleted_at IS NULL",
                [*payload.values(), position_id],
            )
            if cursor.rowcount == 0:
                return None
        return self.get_position(position_id)

    def delete_position(self, position_id: str) -> bool:
        now = utc_now_iso()
        with membership_transaction() as connection:
            connection.execute(
                """
                UPDATE membership_user
                SET position_id = NULL, updated_at = ?
                WHERE position_id = ? AND deleted_at IS NULL
                """,
                [now, position_id],
            )
            cursor = connection.execute(
                """
                UPDATE membership_position
                SET deleted_at = ?, updated_at = ?
                WHERE id = ? AND deleted_at IS NULL
                """,
                [now, now, position_id],
            )
            return cursor.rowcount > 0

    def code_exists(self, table_name: str, code: str, exclude_id: str | None = None) -> bool:
        params: list[Any] = [code]
        exclude_sql = ""
        if exclude_id:
            exclude_sql = "AND id != ?"
            params.append(exclude_id)
        with get_membership_connection() as connection:
            row = connection.execute(
                f"SELECT id FROM {table_name} WHERE code = ? AND deleted_at IS NULL {exclude_sql} LIMIT 1",
                params,
            ).fetchone()
        return row is not None

    def entity_exists(self, table_name: str, entity_id: str | None) -> bool:
        if not entity_id:
            return True
        with get_membership_connection() as connection:
            row = connection.execute(
                f"SELECT id FROM {table_name} WHERE id = ? AND deleted_at IS NULL LIMIT 1",
                [entity_id],
            ).fetchone()
        return row is not None

    def unit_row(self, row: DatabaseRow) -> dict[str, Any]:
        return {
            "id": row["id"],
            "code": row["code"],
            "name": row["name"],
            "unitType": row["unit_type"],
            "parentId": row["parent_id"],
            "companyId": row["company_id"],
            "managerUserId": row["manager_user_id"],
            "managerDisplayName": row["manager_display_name"],
            "description": row["description"],
            "path": row["path"],
            "level": row["level"],
            "status": row["status"],
            "children": [],
            "createdAt": row["created_at"],
            "updatedAt": row["updated_at"],
        }

    def position_row(self, row: DatabaseRow) -> dict[str, Any]:
        return {
            "id": row["id"],
            "name": row["name"],
            "description": row["description"],
            "level": row["level"],
            "status": row["status"],
            "createdAt": row["created_at"],
            "updatedAt": row["updated_at"],
        }

    def _soft_delete(self, table_name: str, entity_id: str) -> bool:
        now = utc_now_iso()
        with membership_transaction() as connection:
            cursor = connection.execute(
                f"UPDATE {table_name} SET deleted_at = ?, updated_at = ? WHERE id = ? AND deleted_at IS NULL",
                [now, now, entity_id],
            )
            return cursor.rowcount > 0

    def _unit_filter(self, keyword: str, unit_type: str, status_filter: str) -> tuple[str, list[Any]]:
        clauses: list[str] = []
        params: list[Any] = []
        if keyword.strip():
            like_keyword = f"%{' '.join(keyword.split())}%"
            clauses.append("(o.code LIKE ? OR o.name LIKE ? OR o.description LIKE ?)")
            params.extend([like_keyword] * 3)
        if unit_type.strip():
            clauses.append("o.unit_type = ?")
            params.append(unit_type.strip().upper())
        if status_filter.strip():
            clauses.append("o.status = ?")
            params.append(status_filter.strip().upper())
        return ("AND " + " AND ".join(clauses), params) if clauses else ("", [])

    def _position_filter(self, keyword: str, status_filter: str) -> tuple[str, list[Any]]:
        clauses: list[str] = []
        params: list[Any] = []
        if keyword.strip():
            like_keyword = f"%{' '.join(keyword.split())}%"
            clauses.append("(p.name LIKE ? OR p.description LIKE ?)")
            params.extend([like_keyword] * 2)
        if status_filter.strip():
            clauses.append("p.status = ?")
            params.append(status_filter.strip().upper())
        return ("AND " + " AND ".join(clauses), params) if clauses else ("", [])


    def _insert(self, connection: SQLAlchemyConnectionAdapter, table_name: str, payload: dict[str, Any]) -> None:
        columns = list(payload.keys())
        placeholders = ", ".join("?" for _ in columns)
        connection.execute(
            f"INSERT INTO {table_name} ({', '.join(columns)}) VALUES ({placeholders})",
            [payload[column] for column in columns],
        )
