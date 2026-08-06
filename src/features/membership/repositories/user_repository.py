import json
import sqlite3
import uuid
from typing import Any

from src.features.membership.core.database import get_membership_connection, membership_transaction
from src.features.membership.core.time import utc_now_iso
from src.features.membership.repositories.membership_repositories import UserRepository


class MembershipUserRepository(UserRepository):
    def list_users(
        self,
        *,
        page: int,
        page_size: int,
        keyword: str,
        status_filter: str,
        organization_id: str,
        locked: bool | None,
    ) -> dict[str, Any]:
        normalized_page = max(1, page)
        normalized_page_size = max(1, min(page_size, 200))
        offset = (normalized_page - 1) * normalized_page_size
        where_sql, params = self._build_user_filter_clause(
            keyword=keyword,
            status_filter=status_filter,
            organization_id=organization_id,
            locked=locked,
        )
        connection = get_membership_connection()
        try:
            total = connection.execute(
                f"""
                SELECT COUNT(*) AS total
                FROM membership_user u
                LEFT JOIN membership_user_credential c
                    ON c.user_id = u.id AND c.deleted_at IS NULL
                LEFT JOIN membership_organization_unit o
                    ON o.id = u.organization_id AND o.deleted_at IS NULL
                WHERE u.deleted_at IS NULL
                {where_sql}
                """,
                params,
            ).fetchone()["total"]
            rows = connection.execute(
                f"""
                SELECT
                    u.*,
                    o.name AS organization_name,
                    department_mapping.organization_id AS department_id,
                    department.name AS department_name,
                    manager_relation.manager_user_id,
                    manager.display_name AS manager_display_name,
                    c.locked_until,
                    c.failed_login_count,
                    c.must_change_password,
                    c.mfa_enabled
                FROM membership_user u
                LEFT JOIN membership_user_credential c
                    ON c.user_id = u.id AND c.deleted_at IS NULL
                LEFT JOIN membership_organization_unit o
                    ON o.id = u.organization_id AND o.deleted_at IS NULL
                LEFT JOIN membership_user_department_mapping department_mapping
                    ON department_mapping.id = (
                        SELECT dm.id
                        FROM membership_user_department_mapping dm
                        WHERE dm.user_id = u.id
                          AND dm.deleted_at IS NULL
                        ORDER BY dm.is_primary DESC, dm.updated_at DESC, dm.created_at DESC
                        LIMIT 1
                    )
                LEFT JOIN membership_organization_unit department
                    ON department.id = department_mapping.organization_id AND department.deleted_at IS NULL
                LEFT JOIN membership_user_manager_relation manager_relation
                    ON manager_relation.id = (
                        SELECT mr.id
                        FROM membership_user_manager_relation mr
                        WHERE mr.employee_user_id = u.id
                          AND mr.deleted_at IS NULL
                          AND mr.status = 'ACTIVE'
                        ORDER BY mr.updated_at DESC, mr.created_at DESC
                        LIMIT 1
                    )
                LEFT JOIN membership_user manager
                    ON manager.id = manager_relation.manager_user_id AND manager.deleted_at IS NULL
                WHERE u.deleted_at IS NULL
                {where_sql}
                ORDER BY u.created_at DESC, u.id DESC
                LIMIT ? OFFSET ?
                """,
                [*params, normalized_page_size, offset],
            ).fetchall()
        finally:
            connection.close()

        return {
            "users": [self.row_to_user_summary(row) for row in rows],
            "total": total,
            "page": normalized_page,
            "pageSize": normalized_page_size,
            "offset": offset,
        }

    def get_user_detail(self, user_id: str) -> dict[str, Any] | None:
        connection = get_membership_connection()
        try:
            row = connection.execute(
                """
                SELECT
                    u.*,
                    o.name AS organization_name,
                    department_mapping.organization_id AS department_id,
                    department.name AS department_name,
                    manager_relation.manager_user_id,
                    manager.display_name AS manager_display_name,
                    c.locked_until,
                    c.failed_login_count,
                    c.must_change_password,
                    c.mfa_enabled
                FROM membership_user u
                LEFT JOIN membership_user_credential c
                    ON c.user_id = u.id AND c.deleted_at IS NULL
                LEFT JOIN membership_organization_unit o
                    ON o.id = u.organization_id AND o.deleted_at IS NULL
                LEFT JOIN membership_user_department_mapping department_mapping
                    ON department_mapping.id = (
                        SELECT dm.id
                        FROM membership_user_department_mapping dm
                        WHERE dm.user_id = u.id
                          AND dm.deleted_at IS NULL
                        ORDER BY dm.is_primary DESC, dm.updated_at DESC, dm.created_at DESC
                        LIMIT 1
                    )
                LEFT JOIN membership_organization_unit department
                    ON department.id = department_mapping.organization_id AND department.deleted_at IS NULL
                LEFT JOIN membership_user_manager_relation manager_relation
                    ON manager_relation.id = (
                        SELECT mr.id
                        FROM membership_user_manager_relation mr
                        WHERE mr.employee_user_id = u.id
                          AND mr.deleted_at IS NULL
                          AND mr.status = 'ACTIVE'
                        ORDER BY mr.updated_at DESC, mr.created_at DESC
                        LIMIT 1
                    )
                LEFT JOIN membership_user manager
                    ON manager.id = manager_relation.manager_user_id AND manager.deleted_at IS NULL
                WHERE u.id = ? AND u.deleted_at IS NULL
                """,
                [user_id],
            ).fetchone()
        finally:
            connection.close()

        return self.row_to_user_summary(row) if row else None

    def get_credential(self, user_id: str) -> sqlite3.Row | None:
        connection = get_membership_connection()
        try:
            return connection.execute(
                """
                SELECT *
                FROM membership_user_credential
                WHERE user_id = ? AND deleted_at IS NULL
                """,
                [user_id],
            ).fetchone()
        finally:
            connection.close()

    def create_user_with_credential(
        self,
        *,
        user_values: dict[str, Any],
        password_hash: str,
        password_algorithm: str,
        must_change_password: bool,
        role_ids: list[str] | None = None,
    ) -> dict[str, Any]:
        user_id = str(user_values.get("id") or uuid.uuid4())
        now = utc_now_iso()
        user_payload = {
            **user_values,
            "id": user_id,
            "created_at": now,
            "updated_at": now,
            "deleted_at": None,
        }
        credential_payload = {
            "id": str(uuid.uuid4()),
            "user_id": user_id,
            "password_hash": password_hash,
            "password_algorithm": password_algorithm,
            "password_changed_at": now,
            "must_change_password": 1 if must_change_password else 0,
            "mfa_enabled": 0,
            "failed_login_count": 0,
            "locked_until": None,
            "created_at": now,
            "updated_at": now,
            "deleted_at": None,
        }

        with membership_transaction() as connection:
            self._insert(connection, "membership_user", user_payload)
            self._insert(connection, "membership_user_credential", credential_payload)
            for role_id in role_ids or []:
                self._insert(connection, "membership_user_role", {
                    "id": f"user-role-{user_id}-{role_id}",
                    "user_id": user_id,
                    "role_id": role_id,
                    "organization_id": user_values.get("organization_id"),
                    "effective_from": now,
                    "effective_to": None,
                    "created_at": now,
                    "updated_at": now,
                    "deleted_at": None,
                })

        created = self.get_user_detail(user_id)
        if created is None:
            raise RuntimeError("Failed to load created membership user.")
        return created

    def update_user_values(self, user_id: str, values: dict[str, Any]) -> dict[str, Any] | None:
        if not values:
            return self.get_user_detail(user_id)
        payload = {**values, "updated_at": utc_now_iso()}
        assignments = ", ".join(f"{column} = ?" for column in payload.keys())
        with membership_transaction() as connection:
            cursor = connection.execute(
                f"""
                UPDATE membership_user
                SET {assignments}
                WHERE id = ? AND deleted_at IS NULL
                """,
                [*payload.values(), user_id],
            )
            if cursor.rowcount == 0:
                return None
        return self.get_user_detail(user_id)

    def replace_primary_department_mapping(self, user_id: str, organization_id: str | None) -> None:
        now = utc_now_iso()
        with membership_transaction() as connection:
            connection.execute(
                """
                UPDATE membership_user_department_mapping
                SET deleted_at = ?, updated_at = ?
                WHERE user_id = ? AND deleted_at IS NULL
                """,
                [now, now, user_id],
            )
            if organization_id:
                self._insert(connection, "membership_user_department_mapping", {
                    "id": str(uuid.uuid4()),
                    "user_id": user_id,
                    "organization_id": organization_id,
                    "position_id": None,
                    "is_primary": 1,
                    "effective_from": now,
                    "effective_to": None,
                    "created_at": now,
                    "updated_at": now,
                    "deleted_at": None,
                })
            connection.execute(
                """
                UPDATE membership_user
                SET organization_id = ?, updated_at = ?
                WHERE id = ? AND deleted_at IS NULL
                """,
                [organization_id, now, user_id],
            )

    def replace_manager_relation(self, user_id: str, manager_user_id: str | None, organization_id: str | None) -> None:
        now = utc_now_iso()
        with membership_transaction() as connection:
            connection.execute(
                """
                UPDATE membership_user_manager_relation
                SET deleted_at = ?, updated_at = ?
                WHERE employee_user_id = ? AND deleted_at IS NULL
                """,
                [now, now, user_id],
            )
            if manager_user_id:
                connection.execute(
                    """
                    INSERT OR REPLACE INTO membership_user_manager_relation (
                        id, manager_user_id, employee_user_id, organization_id,
                        relation_type, status, created_at, updated_at, deleted_at
                    )
                    VALUES (?, ?, ?, ?, 'DIRECT', 'ACTIVE', ?, ?, NULL)
                    """,
                    [str(uuid.uuid4()), manager_user_id, user_id, organization_id, now, now],
                )

    def replace_user_roles(self, user_id: str, role_ids: list[str], organization_id: str | None) -> None:
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

    def update_credential_values(self, user_id: str, values: dict[str, Any]) -> bool:
        payload = {**values, "updated_at": utc_now_iso()}
        assignments = ", ".join(f"{column} = ?" for column in payload.keys())
        with membership_transaction() as connection:
            cursor = connection.execute(
                f"""
                UPDATE membership_user_credential
                SET {assignments}
                WHERE user_id = ? AND deleted_at IS NULL
                """,
                [*payload.values(), user_id],
            )
            return cursor.rowcount > 0

    def insert_notification(self, user_id: str, template_code: str, payload: dict[str, Any]) -> None:
        now = utc_now_iso()
        with membership_transaction() as connection:
            connection.execute(
                """
                INSERT INTO membership_notification_outbox (
                    id, template_code, recipient_user_id, channel, payload_json,
                    status, created_at, updated_at
                )
                VALUES (?, ?, ?, 'EMAIL', ?, 'PENDING', ?, ?)
                """,
                [
                    str(uuid.uuid4()),
                    template_code,
                    user_id,
                    json.dumps(payload, ensure_ascii=False),
                    now,
                    now,
                ],
            )

    def soft_delete_user(self, user_id: str) -> bool:
        now = utc_now_iso()
        with membership_transaction() as connection:
            cursor = connection.execute(
                """
                UPDATE membership_user
                SET deleted_at = ?,
                    updated_at = ?
                WHERE id = ? AND deleted_at IS NULL
                """,
                [now, now, user_id],
            )
            connection.execute(
                """
                UPDATE membership_user_credential
                SET deleted_at = ?,
                    updated_at = ?
                WHERE user_id = ? AND deleted_at IS NULL
                """,
                [now, now, user_id],
            )
            return cursor.rowcount > 0

    def username_or_email_exists(
        self,
        *,
        username: str,
        email: str,
        exclude_user_id: str | None = None,
    ) -> dict[str, bool]:
        params: list[Any] = [username, email]
        exclude_sql = ""
        if exclude_user_id:
            exclude_sql = "AND id != ?"
            params.append(exclude_user_id)
        connection = get_membership_connection()
        try:
            rows = connection.execute(
                f"""
                SELECT username, email
                FROM membership_user
                WHERE deleted_at IS NULL
                  AND (username = ? OR email = ?)
                  {exclude_sql}
                """,
                params,
            ).fetchall()
        finally:
            connection.close()

        return {
            "username": any(row["username"] == username for row in rows),
            "email": any(row["email"] == email for row in rows),
        }

    def organization_exists(self, organization_id: str | None) -> bool:
        if not organization_id:
            return True
        connection = get_membership_connection()
        try:
            row = connection.execute(
                """
                SELECT id
                FROM membership_organization_unit
                WHERE id = ? AND deleted_at IS NULL AND status = 'ACTIVE'
                """,
                [organization_id],
            ).fetchone()
        finally:
            connection.close()
        return row is not None

    def user_exists(self, user_id: str | None) -> bool:
        if not user_id:
            return True
        connection = get_membership_connection()
        try:
            row = connection.execute(
                """
                SELECT id
                FROM membership_user
                WHERE id = ? AND deleted_at IS NULL AND status = 'ACTIVE'
                """,
                [user_id],
            ).fetchone()
        finally:
            connection.close()
        return row is not None

    def role_ids_exist(self, role_ids: list[str]) -> bool:
        if not role_ids:
            return True
        placeholders = ", ".join("?" for _ in role_ids)
        connection = get_membership_connection()
        try:
            count = connection.execute(
                f"""
                SELECT COUNT(*) AS total
                FROM membership_role
                WHERE id IN ({placeholders})
                  AND deleted_at IS NULL
                  AND status = 'ACTIVE'
                """,
                role_ids,
            ).fetchone()["total"]
        finally:
            connection.close()
        return count == len(set(role_ids))

    def _build_user_filter_clause(
        self,
        *,
        keyword: str,
        status_filter: str,
        organization_id: str,
        locked: bool | None,
    ) -> tuple[str, list[Any]]:
        clauses: list[str] = []
        params: list[Any] = []
        normalized_keyword = " ".join(keyword.split())
        normalized_status = status_filter.strip().upper()
        normalized_organization_id = organization_id.strip()

        if normalized_keyword:
            like_keyword = f"%{normalized_keyword}%"
            clauses.append(
                """
                (
                    u.username LIKE ?
                    OR u.email LIKE ?
                    OR u.display_name LIKE ?
                    OR u.employee_no LIKE ?
                    OR o.name LIKE ?
                )
                """
            )
            params.extend([like_keyword] * 5)

        if normalized_status:
            clauses.append("u.status = ?")
            params.append(normalized_status)

        if normalized_organization_id:
            clauses.append("u.organization_id = ?")
            params.append(normalized_organization_id)

        if locked is True:
            clauses.append("c.locked_until IS NOT NULL")
        elif locked is False:
            clauses.append("c.locked_until IS NULL")

        if not clauses:
            return "", []
        return "AND " + " AND ".join(clauses), params

    def row_to_user_summary(self, row: sqlite3.Row) -> dict[str, Any]:
        return {
            "id": row["id"],
            "username": row["username"],
            "email": row["email"],
            "displayName": row["display_name"],
            "employeeNo": row["employee_no"],
            "organizationId": row["organization_id"],
            "organizationName": row["organization_name"],
            "departmentId": row["department_id"],
            "departmentName": row["department_name"],
            "managerUserId": row["manager_user_id"],
            "managerDisplayName": row["manager_display_name"],
            "status": row["status"],
            "locale": row["locale"],
            "timezone": row["timezone"],
            "lastLoginAt": row["last_login_at"],
            "lockedUntil": row["locked_until"],
            "failedLoginCount": row["failed_login_count"] or 0,
            "mustChangePassword": bool(row["must_change_password"] or 0),
            "mfaEnabled": bool(row["mfa_enabled"] or 0),
            "createdAt": row["created_at"],
            "updatedAt": row["updated_at"],
        }

    def _insert(
        self,
        connection: sqlite3.Connection,
        table_name: str,
        payload: dict[str, Any],
    ) -> None:
        columns = list(payload.keys())
        placeholders = ", ".join("?" for _ in columns)
        column_sql = ", ".join(columns)
        connection.execute(
            f"INSERT INTO {table_name} ({column_sql}) VALUES ({placeholders})",
            [payload[column] for column in columns],
        )
