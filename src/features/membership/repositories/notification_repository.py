import json
import uuid
from typing import Any

from src.features.membership.core.database import get_membership_connection, membership_transaction
from src.features.membership.core.permission_registry import all_permission_codes
from src.features.membership.core.time import utc_now_iso
from src.shared.database.connection import DatabaseRow, SQLAlchemyConnectionAdapter


class NotificationRepository:
    def get_audit_retention_setting(self) -> dict[str, Any]:
        with get_membership_connection() as connection:
            row = connection.execute(
                "SELECT * FROM membership_audit_retention_setting WHERE id = 1"
            ).fetchone()
        if row is None:
            raise RuntimeError("Audit retention setting is not initialized.")
        return self.audit_retention_row(row)

    def update_audit_retention_setting(
        self,
        *,
        retention_days: int,
        updated_by_user_id: str,
    ) -> dict[str, Any]:
        now = utc_now_iso()
        with membership_transaction() as connection:
            connection.execute(
                """
                UPDATE membership_audit_retention_setting
                SET retention_days = ?, updated_by_user_id = ?, updated_at = ?
                WHERE id = 1
                """,
                [retention_days, updated_by_user_id, now],
            )
        return self.get_audit_retention_setting()

    def list_templates(self) -> list[dict[str, Any]]:
        with get_membership_connection() as connection:
            rows = connection.execute(
                """
                SELECT *
                FROM membership_notification_template
                WHERE deleted_at IS NULL
                ORDER BY channel ASC, code ASC
                """
            ).fetchall()
        return [self.template_row(row) for row in rows]

    def upsert_template(self, values: dict[str, Any]) -> dict[str, Any]:
        now = utc_now_iso()
        existing = self._find_template(values["code"])
        payload = {
            "code": values["code"].strip().upper(),
            "channel": values.get("channel", "EMAIL").strip().upper(),
            "subject": values.get("subject", ""),
            "body": values["body"],
            "status": values.get("status", "ACTIVE"),
            "updated_at": now,
        }
        with membership_transaction() as connection:
            if existing:
                assignments = ", ".join(f"{column} = ?" for column in payload)
                connection.execute(
                    f"UPDATE membership_notification_template SET {assignments} WHERE id = ?",
                    [*payload.values(), existing["id"]],
                )
                template_id = existing["id"]
            else:
                template_id = str(uuid.uuid4())
                self._insert(
                    connection,
                    "membership_notification_template",
                    {"id": template_id, **payload, "created_at": now, "deleted_at": None},
                )
        return self.get_template(template_id) or {"id": template_id, **payload}

    def get_template(self, template_id: str) -> dict[str, Any] | None:
        with get_membership_connection() as connection:
            row = connection.execute(
                "SELECT * FROM membership_notification_template WHERE id = ? AND deleted_at IS NULL",
                [template_id],
            ).fetchone()
        return self.template_row(row) if row else None

    def list_outbox(self, *, status: str = "", template_code: str = "", page: int = 1, page_size: int = 50) -> dict[str, Any]:
        normalized_page = max(1, page)
        normalized_page_size = max(1, min(page_size, 200))
        offset = (normalized_page - 1) * normalized_page_size
        clauses: list[str] = []
        params: list[Any] = []
        if status:
            clauses.append("o.status = ?")
            params.append(status.upper())
        if template_code:
            clauses.append("o.template_code = ?")
            params.append(template_code.upper())
        where_sql = "AND " + " AND ".join(clauses) if clauses else ""
        with get_membership_connection() as connection:
            total = connection.execute(
                f"""
                SELECT COUNT(*) AS total
                FROM membership_notification_outbox o
                WHERE o.deleted_at IS NULL
                {where_sql}
                """,
                params,
            ).fetchone()["total"]
            rows = connection.execute(
                f"""
                SELECT o.*, u.email AS recipient_email, u.display_name AS recipient_display_name
                FROM membership_notification_outbox o
                LEFT JOIN membership_user u ON u.id = o.recipient_user_id AND u.deleted_at IS NULL
                WHERE o.deleted_at IS NULL
                {where_sql}
                ORDER BY o.created_at DESC
                LIMIT ? OFFSET ?
                """,
                [*params, normalized_page_size, offset],
            ).fetchall()
        return {
            "items": [self.outbox_row(row) for row in rows],
            "total": total,
            "page": normalized_page,
            "pageSize": normalized_page_size,
            "offset": offset,
        }

    def mark_outbox(self, outbox_id: str, *, status: str, error_message: str = "") -> dict[str, Any] | None:
        now = utc_now_iso()
        sent_at = now if status == "SENT" else None
        with membership_transaction() as connection:
            cursor = connection.execute(
                """
                UPDATE membership_notification_outbox
                SET status = ?,
                    sent_at = COALESCE(?, sent_at),
                    error_message = ?,
                    updated_at = ?
                WHERE id = ? AND deleted_at IS NULL
                """,
                [status, sent_at, error_message, now, outbox_id],
            )
            if cursor.rowcount == 0:
                return None
        return self.get_outbox(outbox_id)

    def get_outbox(self, outbox_id: str) -> dict[str, Any] | None:
        with get_membership_connection() as connection:
            row = connection.execute(
                """
                SELECT o.*, u.email AS recipient_email, u.display_name AS recipient_display_name
                FROM membership_notification_outbox o
                LEFT JOIN membership_user u ON u.id = o.recipient_user_id AND u.deleted_at IS NULL
                WHERE o.id = ? AND o.deleted_at IS NULL
                """,
                [outbox_id],
            ).fetchone()
        return self.outbox_row(row) if row else None

    def list_audit_logs(
        self,
        *,
        page: int,
        page_size: int,
        action: str = "",
        actions: list[str] | None = None,
        resource_type: str = "",
        outcome: str = "",
    ) -> dict[str, Any]:
        normalized_page = max(1, page)
        normalized_page_size = max(1, min(page_size, 200))
        offset = (normalized_page - 1) * normalized_page_size
        clauses: list[str] = []
        params: list[Any] = []
        if action:
            clauses.append("a.action LIKE ?")
            params.append(f"%{action}%")
        selected_actions = list(dict.fromkeys(item.strip() for item in (actions or []) if item.strip()))
        if selected_actions:
            placeholders = ", ".join("?" for _ in selected_actions)
            clauses.append(f"a.action IN ({placeholders})")
            params.extend(selected_actions)
        if resource_type:
            clauses.append("a.resource_type = ?")
            params.append(resource_type)
        if outcome:
            clauses.append("a.outcome = ?")
            params.append(outcome.upper())
        where_sql = "AND " + " AND ".join(clauses) if clauses else ""
        with get_membership_connection() as connection:
            total = connection.execute(
                f"""
                SELECT COUNT(*) AS total
                FROM membership_audit_log a
                WHERE a.deleted_at IS NULL
                {where_sql}
                """,
                params,
            ).fetchone()["total"]
            rows = connection.execute(
                f"""
                SELECT a.*,
                       u.display_name AS actor_display_name,
                       u.email AS actor_email
                FROM membership_audit_log a
                LEFT JOIN membership_user u ON u.id = a.actor_user_id AND u.deleted_at IS NULL
                WHERE a.deleted_at IS NULL
                {where_sql}
                ORDER BY a.created_at DESC
                LIMIT ? OFFSET ?
                """,
                [*params, normalized_page_size, offset],
            ).fetchall()
        return {
            "logs": [self.audit_row(row) for row in rows],
            "total": total,
            "page": normalized_page,
            "pageSize": normalized_page_size,
            "offset": offset,
        }

    def admin_dashboard(self) -> dict[str, Any]:
        with get_membership_connection() as connection:
            user_stats = dict(connection.execute(
                """
                SELECT
                    COUNT(*) AS "totalUsers",
                    SUM(CASE WHEN status = 'ACTIVE' THEN 1 ELSE 0 END) AS "activeUsers",
                    SUM(CASE WHEN status = 'INACTIVE' THEN 1 ELSE 0 END) AS "inactiveUsers"
                FROM membership_user
                WHERE deleted_at IS NULL
                """
            ).fetchone())
            locked_users = connection.execute(
                """
                SELECT COUNT(*) AS total
                FROM membership_user_credential
                WHERE deleted_at IS NULL AND locked_until IS NOT NULL
                """
            ).fetchone()["total"]
            permission_overview = dict(connection.execute(
                """
                SELECT
                    (SELECT COUNT(*) FROM membership_role WHERE deleted_at IS NULL) AS roles,
                    (SELECT COUNT(*) FROM membership_role_permission WHERE deleted_at IS NULL) AS "rolePermissions",
                    (SELECT COUNT(*) FROM membership_user_role WHERE deleted_at IS NULL) AS "userRoles"
                """
            ).fetchone())
            permission_overview["permissions"] = len(all_permission_codes())
            login_stats = dict(connection.execute(
                """
                SELECT
                    SUM(CASE WHEN action = 'auth.login.success' THEN 1 ELSE 0 END) AS "successfulLogins",
                    SUM(CASE WHEN action = 'auth.login.failed' THEN 1 ELSE 0 END) AS "failedLogins",
                    COUNT(*) AS "totalLoginEvents"
                FROM membership_audit_log
                WHERE deleted_at IS NULL AND action LIKE ?
                """,
                ["auth.login.%"],
            ).fetchone())
            notification_stats = dict(connection.execute(
                """
                SELECT
                    COUNT(*) AS "totalNotifications",
                    SUM(CASE WHEN status = 'PENDING' THEN 1 ELSE 0 END) AS "pendingNotifications",
                    SUM(CASE WHEN status = 'SENT' THEN 1 ELSE 0 END) AS "sentNotifications",
                    SUM(CASE WHEN status = 'FAILED' THEN 1 ELSE 0 END) AS "failedNotifications"
                FROM membership_notification_outbox
                WHERE deleted_at IS NULL
                """
            ).fetchone())
        audit = self.list_audit_logs(page=1, page_size=8)
        user_stats["lockedUsers"] = locked_users
        return {
            "userStats": self._zero_none(user_stats),
            "permissionOverview": self._zero_none(permission_overview),
            "loginStats": self._zero_none(login_stats),
            "notificationStats": self._zero_none(notification_stats),
            "recentAuditLogs": audit["logs"],
        }

    def template_row(self, row: DatabaseRow) -> dict[str, Any]:
        return {
            "id": row["id"],
            "code": row["code"],
            "channel": row["channel"],
            "subject": row["subject"],
            "body": row["body"],
            "status": row["status"],
            "createdAt": row["created_at"],
            "updatedAt": row["updated_at"],
        }

    def outbox_row(self, row: DatabaseRow) -> dict[str, Any]:
        return {
            "id": row["id"],
            "templateCode": row["template_code"],
            "recipientUserId": row["recipient_user_id"],
            "recipientEmail": row["recipient_email"],
            "recipientDisplayName": row["recipient_display_name"],
            "channel": row["channel"],
            "payload": self._json(row["payload_json"], {}),
            "status": row["status"],
            "scheduledAt": row["scheduled_at"],
            "sentAt": row["sent_at"],
            "errorMessage": row["error_message"],
            "createdAt": row["created_at"],
            "updatedAt": row["updated_at"],
        }

    def audit_row(self, row: DatabaseRow) -> dict[str, Any]:
        return {
            "id": row["id"],
            "actorUserId": row["actor_user_id"],
            "actorDisplayName": row["actor_display_name"],
            "actorEmail": row["actor_email"],
            "action": row["action"],
            "resourceType": row["resource_type"],
            "resourceId": row["resource_id"],
            "outcome": row["outcome"],
            "ipAddress": row["ip_address"],
            "userAgent": row["user_agent"],
            "metadata": self._json(row["metadata_json"], {}),
            "createdAt": row["created_at"],
        }

    def audit_retention_row(self, row: DatabaseRow) -> dict[str, Any]:
        return {
            "retentionDays": row["retention_days"],
            "scheduleTimeZone": "Asia/Taipei",
            "lastRunAt": row["last_run_at"],
            "lastArchiveAt": row["last_archive_at"],
            "lastArchivedCount": row["last_archived_count"],
            "lastCutoffAt": row["last_cutoff_at"],
            "lastArchiveFilename": row["last_archive_filename"],
            "lastError": row["last_error"],
            "updatedAt": row["updated_at"],
        }

    def _find_template(self, code: str) -> dict[str, Any] | None:
        with get_membership_connection() as connection:
            row = connection.execute(
                "SELECT * FROM membership_notification_template WHERE code = ? AND deleted_at IS NULL",
                [code.strip().upper()],
            ).fetchone()
        return self.template_row(row) if row else None

    def _json(self, raw: str | None, default: Any) -> Any:
        if not raw:
            return default
        try:
            return json.loads(raw)
        except json.JSONDecodeError:
            return default

    def _zero_none(self, values: dict[str, Any]) -> dict[str, Any]:
        return {key: (0 if value is None else value) for key, value in values.items()}

    def _insert(self, connection: SQLAlchemyConnectionAdapter, table_name: str, payload: dict[str, Any]) -> None:
        columns = list(payload.keys())
        placeholders = ", ".join("?" for _ in columns)
        connection.execute(
            f"INSERT INTO {table_name} ({', '.join(columns)}) VALUES ({placeholders})",
            [payload[column] for column in columns],
        )
