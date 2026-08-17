import sqlite3
import uuid
from typing import Any

from src.features.membership.core.database import get_membership_connection, membership_transaction
from src.features.membership.core.time import utc_now_iso


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
                ORDER BY o.path ASC, o.sort_order ASC, o.code ASC
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
        payload = {
            "id": unit_id,
            "code": code,
            "name": values["name"],
            "parent_id": values.get("parentId"),
            "path": path,
            "level": (parent["level"] + 1) if parent else 0,
            "status": values.get("status", "ACTIVE"),
            "sort_order": values.get("sortOrder", 0),
            "unit_type": values.get("unitType", "DEPARTMENT"),
            "company_id": values.get("companyId"),
            "manager_user_id": values.get("managerUserId"),
            "description": values.get("description", ""),
            "created_at": now,
            "updated_at": now,
            "deleted_at": None,
        }
        if not payload["company_id"] and payload["unit_type"] == "COMPANY":
            payload["company_id"] = unit_id
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
        payload = {
            "code": code,
            "name": values["name"],
            "parent_id": values.get("parentId"),
            "path": path,
            "level": (parent["level"] + 1) if parent else 0,
            "status": values.get("status", "ACTIVE"),
            "sort_order": values.get("sortOrder", 0),
            "unit_type": values.get("unitType", "DEPARTMENT"),
            "company_id": values.get("companyId") or (unit_id if values.get("unitType") == "COMPANY" else None),
            "manager_user_id": values.get("managerUserId"),
            "description": values.get("description", ""),
            "updated_at": utc_now_iso(),
        }
        assignments = ", ".join(f"{column} = ?" for column in payload)
        with membership_transaction() as connection:
            cursor = connection.execute(
                f"UPDATE membership_organization_unit SET {assignments} WHERE id = ? AND deleted_at IS NULL",
                [*payload.values(), unit_id],
            )
            if cursor.rowcount == 0:
                return None
        return self.get_unit(unit_id)

    def delete_unit(self, unit_id: str) -> bool:
        now = utc_now_iso()
        with membership_transaction() as connection:
            cursor = connection.execute(
                """
                UPDATE membership_organization_unit
                SET deleted_at = ?, updated_at = ?
                WHERE id = ? AND deleted_at IS NULL
                """,
                [now, now, unit_id],
            )
            return cursor.rowcount > 0

    def list_positions(self, *, keyword: str = "", status_filter: str = "") -> list[dict[str, Any]]:
        where_sql, params = self._position_filter(keyword, status_filter)
        with get_membership_connection() as connection:
            rows = connection.execute(
                f"""
                SELECT p.*, COUNT(m.id) AS user_count
                FROM membership_position p
                LEFT JOIN membership_user_department_mapping m
                    ON m.position_id = p.id AND m.deleted_at IS NULL
                WHERE p.deleted_at IS NULL
                {where_sql}
                GROUP BY p.id
                ORDER BY p.level DESC, p.sort_order ASC, p.code ASC
                """,
                params,
            ).fetchall()
        return [self.position_row(row) for row in rows]

    def get_position(self, position_id: str) -> dict[str, Any] | None:
        with get_membership_connection() as connection:
            row = connection.execute(
                """
                SELECT p.*, COUNT(m.id) AS user_count
                FROM membership_position p
                LEFT JOIN membership_user_department_mapping m
                    ON m.position_id = p.id AND m.deleted_at IS NULL
                WHERE p.id = ? AND p.deleted_at IS NULL
                GROUP BY p.id
                """,
                [position_id],
            ).fetchone()
        return self.position_row(row) if row else None

    def create_position(self, values: dict[str, Any]) -> dict[str, Any]:
        position_id = str(uuid.uuid4())
        now = utc_now_iso()
        payload = {
            "id": position_id,
            "code": values["code"],
            "name": values["name"],
            "description": values.get("description", ""),
            "level": values.get("level", 0),
            "sort_order": values.get("sortOrder", 0),
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
            "code": values["code"],
            "name": values["name"],
            "description": values.get("description", ""),
            "level": values.get("level", 0),
            "sort_order": values.get("sortOrder", 0),
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
            cursor = connection.execute(
                """
                UPDATE membership_position
                SET deleted_at = ?, updated_at = ?
                WHERE id = ? AND deleted_at IS NULL
                """,
                [now, now, position_id],
            )
            return cursor.rowcount > 0

    def list_user_department_mappings(self, *, user_id: str = "", organization_id: str = "") -> list[dict[str, Any]]:
        clauses: list[str] = []
        params: list[Any] = []
        if user_id:
            clauses.append("m.user_id = ?")
            params.append(user_id)
        if organization_id:
            clauses.append("m.organization_id = ?")
            params.append(organization_id)
        where_sql = "AND " + " AND ".join(clauses) if clauses else ""
        with get_membership_connection() as connection:
            rows = connection.execute(
                f"""
                SELECT m.*,
                       u.username,
                       u.display_name,
                       o.name AS organization_name,
                       p.name AS position_name
                FROM membership_user_department_mapping m
                LEFT JOIN membership_user u ON u.id = m.user_id AND u.deleted_at IS NULL
                LEFT JOIN membership_organization_unit o ON o.id = m.organization_id AND o.deleted_at IS NULL
                LEFT JOIN membership_position p ON p.id = m.position_id AND p.deleted_at IS NULL
                WHERE m.deleted_at IS NULL
                {where_sql}
                ORDER BY m.is_primary DESC, o.path ASC, u.display_name ASC
                """,
                params,
            ).fetchall()
        return [self.mapping_row(row) for row in rows]

    def upsert_user_department_mapping(self, values: dict[str, Any]) -> dict[str, Any]:
        mapping_id = str(uuid.uuid4())
        now = utc_now_iso()
        payload = {
            "id": mapping_id,
            "user_id": values["userId"],
            "organization_id": values["organizationId"],
            "position_id": values.get("positionId"),
            "is_primary": 1 if values.get("isPrimary") else 0,
            "effective_from": values.get("effectiveFrom"),
            "effective_to": values.get("effectiveTo"),
            "created_at": now,
            "updated_at": now,
            "deleted_at": None,
        }
        with membership_transaction() as connection:
            if payload["is_primary"]:
                connection.execute(
                    """
                    UPDATE membership_user_department_mapping
                    SET is_primary = 0, updated_at = ?
                    WHERE user_id = ? AND deleted_at IS NULL
                    """,
                    [now, payload["user_id"]],
                )
            self._insert(connection, "membership_user_department_mapping", payload)
            connection.execute(
                """
                UPDATE membership_user
                SET organization_id = ?, updated_at = ?
                WHERE id = ? AND deleted_at IS NULL
                """,
                [payload["organization_id"], now, payload["user_id"]],
            )
        return self.list_user_department_mappings(user_id=payload["user_id"], organization_id=payload["organization_id"])[0]

    def delete_user_department_mapping(self, mapping_id: str) -> bool:
        return self._soft_delete("membership_user_department_mapping", mapping_id)

    def list_manager_relations(self, *, manager_user_id: str = "", employee_user_id: str = "") -> list[dict[str, Any]]:
        clauses: list[str] = []
        params: list[Any] = []
        if manager_user_id:
            clauses.append("r.manager_user_id = ?")
            params.append(manager_user_id)
        if employee_user_id:
            clauses.append("r.employee_user_id = ?")
            params.append(employee_user_id)
        where_sql = "AND " + " AND ".join(clauses) if clauses else ""
        with get_membership_connection() as connection:
            rows = connection.execute(
                f"""
                SELECT r.*,
                       manager.display_name AS manager_display_name,
                       employee.display_name AS employee_display_name,
                       o.name AS organization_name
                FROM membership_user_manager_relation r
                LEFT JOIN membership_user manager ON manager.id = r.manager_user_id AND manager.deleted_at IS NULL
                LEFT JOIN membership_user employee ON employee.id = r.employee_user_id AND employee.deleted_at IS NULL
                LEFT JOIN membership_organization_unit o ON o.id = r.organization_id AND o.deleted_at IS NULL
                WHERE r.deleted_at IS NULL
                {where_sql}
                ORDER BY manager.display_name ASC, employee.display_name ASC
                """,
                params,
            ).fetchall()
        return [self.manager_relation_row(row) for row in rows]

    def create_manager_relation(self, values: dict[str, Any]) -> dict[str, Any]:
        relation_id = str(uuid.uuid4())
        now = utc_now_iso()
        payload = {
            "id": relation_id,
            "manager_user_id": values["managerUserId"],
            "employee_user_id": values["employeeUserId"],
            "organization_id": values.get("organizationId"),
            "relation_type": values.get("relationType", "DIRECT"),
            "status": values.get("status", "ACTIVE"),
            "created_at": now,
            "updated_at": now,
            "deleted_at": None,
        }
        with membership_transaction() as connection:
            self._insert(connection, "membership_user_manager_relation", payload)
        return self.list_manager_relations(employee_user_id=payload["employee_user_id"])[0]

    def delete_manager_relation(self, relation_id: str) -> bool:
        return self._soft_delete("membership_user_manager_relation", relation_id)

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

    def unit_row(self, row: sqlite3.Row) -> dict[str, Any]:
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
            "sortOrder": row["sort_order"],
            "status": row["status"],
            "children": [],
            "createdAt": row["created_at"],
            "updatedAt": row["updated_at"],
        }

    def position_row(self, row: sqlite3.Row) -> dict[str, Any]:
        return {
            "id": row["id"],
            "code": row["code"],
            "name": row["name"],
            "description": row["description"],
            "level": row["level"],
            "sortOrder": row["sort_order"],
            "status": row["status"],
            "userCount": row["user_count"],
            "createdAt": row["created_at"],
            "updatedAt": row["updated_at"],
        }

    def mapping_row(self, row: sqlite3.Row) -> dict[str, Any]:
        return {
            "id": row["id"],
            "userId": row["user_id"],
            "username": row["username"],
            "displayName": row["display_name"],
            "organizationId": row["organization_id"],
            "organizationName": row["organization_name"],
            "positionId": row["position_id"],
            "positionName": row["position_name"],
            "isPrimary": bool(row["is_primary"]),
            "effectiveFrom": row["effective_from"],
            "effectiveTo": row["effective_to"],
            "createdAt": row["created_at"],
            "updatedAt": row["updated_at"],
        }

    def manager_relation_row(self, row: sqlite3.Row) -> dict[str, Any]:
        return {
            "id": row["id"],
            "managerUserId": row["manager_user_id"],
            "managerDisplayName": row["manager_display_name"],
            "employeeUserId": row["employee_user_id"],
            "employeeDisplayName": row["employee_display_name"],
            "organizationId": row["organization_id"],
            "organizationName": row["organization_name"],
            "relationType": row["relation_type"],
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
            clauses.append("(p.code LIKE ? OR p.name LIKE ? OR p.description LIKE ?)")
            params.extend([like_keyword] * 3)
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
