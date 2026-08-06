import json
import sqlite3
import uuid
from typing import Any

from src.features.membership.core.database import get_membership_connection, membership_transaction
from src.features.membership.core.time import utc_now_iso


class AuthRepository:
    def find_user_by_login(self, login: str) -> dict[str, Any] | None:
        normalized_login = login.strip().lower()
        connection = get_membership_connection()
        try:
            row = connection.execute(
                """
                SELECT
                    u.*,
                    c.password_hash,
                    c.password_algorithm,
                    c.password_changed_at,
                    c.must_change_password,
                    c.failed_login_count,
                    c.locked_until,
                    c.last_failed_login_at,
                    c.last_failed_login_ip
                FROM membership_user u
                JOIN membership_user_credential c
                    ON c.user_id = u.id AND c.deleted_at IS NULL
                WHERE u.deleted_at IS NULL
                  AND (LOWER(u.username) = ? OR LOWER(u.email) = ?)
                LIMIT 1
                """,
                [normalized_login, normalized_login],
            ).fetchone()
        finally:
            connection.close()
        return dict(row) if row else None

    def get_user_by_id(self, user_id: str) -> dict[str, Any] | None:
        connection = get_membership_connection()
        try:
            row = connection.execute(
                """
                SELECT
                    u.*,
                    c.must_change_password,
                    c.locked_until,
                    c.failed_login_count
                FROM membership_user u
                LEFT JOIN membership_user_credential c
                    ON c.user_id = u.id AND c.deleted_at IS NULL
                WHERE u.id = ? AND u.deleted_at IS NULL
                """,
                [user_id],
            ).fetchone()
        finally:
            connection.close()
        return dict(row) if row else None

    def record_failed_login(
        self,
        *,
        user_id: str,
        failed_count: int,
        locked_until: str | None,
        ip_address: str,
        user_agent: str,
    ) -> None:
        now = utc_now_iso()
        with membership_transaction() as connection:
            connection.execute(
                """
                UPDATE membership_user_credential
                SET failed_login_count = ?,
                    locked_until = ?,
                    last_failed_login_at = ?,
                    last_failed_login_ip = ?,
                    updated_at = ?
                WHERE user_id = ? AND deleted_at IS NULL
                """,
                [failed_count, locked_until, now, ip_address, now, user_id],
            )
            self._insert_audit(
                connection,
                actor_user_id=user_id,
                action="auth.login.failed",
                resource_type="membership_user",
                resource_id=user_id,
                outcome="FAILURE",
                ip_address=ip_address,
                user_agent=user_agent,
                metadata={
                    "module": "登入與帳號",
                    "actionLabel": "登入失敗",
                    "failedLoginCount": failed_count,
                    "lockedUntil": locked_until,
                },
            )
            self._insert_notification(
                connection,
                template_code="AUTH_LOGIN_ANOMALY",
                recipient_user_id=user_id,
                payload={
                    "failedLoginCount": failed_count,
                    "lockedUntil": locked_until,
                    "ipAddress": ip_address,
                    "userAgent": user_agent,
                },
            )
            if locked_until:
                self._insert_notification(
                    connection,
                    template_code="MEMBERSHIP_ACCOUNT_LOCKED",
                    recipient_user_id=user_id,
                    payload={
                        "lockedUntil": locked_until,
                        "ipAddress": ip_address,
                        "userAgent": user_agent,
                    },
                )

    def record_successful_login(
        self,
        *,
        user_id: str,
        ip_address: str,
        user_agent: str,
    ) -> None:
        now = utc_now_iso()
        with membership_transaction() as connection:
            connection.execute(
                """
                UPDATE membership_user
                SET last_login_at = ?,
                    last_login_ip = ?,
                    updated_at = ?
                WHERE id = ? AND deleted_at IS NULL
                """,
                [now, ip_address, now, user_id],
            )
            connection.execute(
                """
                UPDATE membership_user_credential
                SET failed_login_count = 0,
                    locked_until = NULL,
                    updated_at = ?
                WHERE user_id = ? AND deleted_at IS NULL
                """,
                [now, user_id],
            )
            self._insert_audit(
                connection,
                actor_user_id=user_id,
                action="auth.login.success",
                resource_type="membership_user",
                resource_id=user_id,
                outcome="SUCCESS",
                ip_address=ip_address,
                user_agent=user_agent,
                metadata={"module": "登入與帳號", "actionLabel": "登入成功"},
            )

    def create_session_and_refresh_token(
        self,
        *,
        user_id: str,
        refresh_token_hash: str,
        expires_at: str,
        remember_me: bool,
        ip_address: str,
        user_agent: str,
    ) -> dict[str, str]:
        now = utc_now_iso()
        session_id = str(uuid.uuid4())
        refresh_token_id = str(uuid.uuid4())
        with membership_transaction() as connection:
            connection.execute(
                """
                INSERT INTO membership_refresh_token (
                    id, user_id, token_hash, device_id, ip_address, user_agent,
                    expires_at, session_id, created_at, updated_at
                )
                VALUES (?, ?, ?, '', ?, ?, ?, ?, ?, ?)
                """,
                [
                    refresh_token_id,
                    user_id,
                    refresh_token_hash,
                    ip_address,
                    user_agent,
                    expires_at,
                    session_id,
                    now,
                    now,
                ],
            )
            connection.execute(
                """
                INSERT INTO membership_session (
                    id, user_id, refresh_token_id, device_id, ip_address, user_agent,
                    remember_me, started_at, last_seen_at, expires_at, created_at, updated_at
                )
                VALUES (?, ?, ?, '', ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                [
                    session_id,
                    user_id,
                    refresh_token_id,
                    ip_address,
                    user_agent,
                    1 if remember_me else 0,
                    now,
                    now,
                    expires_at,
                    now,
                    now,
                ],
            )
        return {"sessionId": session_id, "refreshTokenId": refresh_token_id}

    def get_refresh_token(self, refresh_token_hash: str) -> dict[str, Any] | None:
        connection = get_membership_connection()
        try:
            row = connection.execute(
                """
                SELECT *
                FROM membership_refresh_token
                WHERE token_hash = ?
                  AND revoked_at IS NULL
                  AND deleted_at IS NULL
                """,
                [refresh_token_hash],
            ).fetchone()
        finally:
            connection.close()
        return dict(row) if row else None

    def revoke_session(self, *, refresh_token_hash: str | None = None, session_id: str | None = None) -> bool:
        now = utc_now_iso()
        with membership_transaction() as connection:
            if refresh_token_hash:
                token_row = connection.execute(
                    "SELECT id, session_id FROM membership_refresh_token WHERE token_hash = ?",
                    [refresh_token_hash],
                ).fetchone()
            elif session_id:
                token_row = connection.execute(
                    "SELECT id, session_id FROM membership_refresh_token WHERE session_id = ?",
                    [session_id],
                ).fetchone()
            else:
                token_row = None
            if not token_row:
                return False
            connection.execute(
                """
                UPDATE membership_refresh_token
                SET revoked_at = ?,
                    updated_at = ?
                WHERE id = ? AND revoked_at IS NULL
                """,
                [now, now, token_row["id"]],
            )
            connection.execute(
                """
                UPDATE membership_session
                SET revoked_at = ?,
                    updated_at = ?
                WHERE id = ? AND revoked_at IS NULL
                """,
                [now, now, token_row["session_id"]],
            )
            return True

    def touch_session(self, session_id: str) -> None:
        now = utc_now_iso()
        with membership_transaction() as connection:
            connection.execute(
                """
                UPDATE membership_session
                SET last_seen_at = ?,
                    updated_at = ?
                WHERE id = ? AND revoked_at IS NULL AND deleted_at IS NULL
                """,
                [now, now, session_id],
            )

    def create_password_reset_token(
        self,
        *,
        user_id: str,
        token_hash: str,
        expires_at: str,
        ip_address: str,
        user_agent: str,
    ) -> None:
        now = utc_now_iso()
        with membership_transaction() as connection:
            connection.execute(
                """
                INSERT INTO membership_password_reset_token (
                    id, user_id, token_hash, expires_at, requested_ip_address, created_at, updated_at
                )
                VALUES (?, ?, ?, ?, ?, ?, ?)
                """,
                [str(uuid.uuid4()), user_id, token_hash, expires_at, ip_address, now, now],
            )
            self._insert_notification(
                connection,
                template_code="AUTH_PASSWORD_RESET",
                recipient_user_id=user_id,
                payload={"tokenHash": token_hash, "userAgent": user_agent},
            )

    def get_password_reset_token(self, token_hash: str) -> dict[str, Any] | None:
        connection = get_membership_connection()
        try:
            row = connection.execute(
                """
                SELECT *
                FROM membership_password_reset_token
                WHERE token_hash = ?
                  AND used_at IS NULL
                  AND deleted_at IS NULL
                """,
                [token_hash],
            ).fetchone()
        finally:
            connection.close()
        return dict(row) if row else None

    def mark_password_reset_used(self, token_id: str) -> None:
        now = utc_now_iso()
        with membership_transaction() as connection:
            connection.execute(
                """
                UPDATE membership_password_reset_token
                SET used_at = ?,
                    updated_at = ?
                WHERE id = ?
                """,
                [now, now, token_id],
            )

    def update_password(self, *, user_id: str, password_hash: str, password_algorithm: str) -> None:
        now = utc_now_iso()
        with membership_transaction() as connection:
            connection.execute(
                """
                UPDATE membership_user_credential
                SET password_hash = ?,
                    password_algorithm = ?,
                    password_changed_at = ?,
                    must_change_password = 0,
                    failed_login_count = 0,
                    locked_until = NULL,
                    updated_at = ?
                WHERE user_id = ? AND deleted_at IS NULL
                """,
                [password_hash, password_algorithm, now, now, user_id],
            )

    def create_email_verification_token(
        self,
        *,
        user_id: str,
        token_hash: str,
        expires_at: str,
        ip_address: str,
        user_agent: str,
    ) -> None:
        now = utc_now_iso()
        with membership_transaction() as connection:
            connection.execute(
                """
                INSERT INTO membership_email_verification_token (
                    id, user_id, token_hash, expires_at, requested_ip_address, created_at, updated_at
                )
                VALUES (?, ?, ?, ?, ?, ?, ?)
                """,
                [str(uuid.uuid4()), user_id, token_hash, expires_at, ip_address, now, now],
            )
            self._insert_notification(
                connection,
                template_code="AUTH_EMAIL_VERIFICATION",
                recipient_user_id=user_id,
                payload={"tokenHash": token_hash, "userAgent": user_agent},
            )

    def get_email_verification_token(self, token_hash: str) -> dict[str, Any] | None:
        connection = get_membership_connection()
        try:
            row = connection.execute(
                """
                SELECT *
                FROM membership_email_verification_token
                WHERE token_hash = ?
                  AND verified_at IS NULL
                  AND deleted_at IS NULL
                """,
                [token_hash],
            ).fetchone()
        finally:
            connection.close()
        return dict(row) if row else None

    def mark_email_verified(self, *, token_id: str, user_id: str) -> None:
        now = utc_now_iso()
        with membership_transaction() as connection:
            connection.execute(
                """
                UPDATE membership_email_verification_token
                SET verified_at = ?,
                    updated_at = ?
                WHERE id = ?
                """,
                [now, now, token_id],
            )
            connection.execute(
                """
                UPDATE membership_user
                SET email_verified_at = ?,
                    updated_at = ?
                WHERE id = ? AND deleted_at IS NULL
                """,
                [now, now, user_id],
            )

    def list_sessions(self, user_id: str) -> list[dict[str, Any]]:
        connection = get_membership_connection()
        try:
            rows = connection.execute(
                """
                SELECT *
                FROM membership_session
                WHERE user_id = ?
                  AND deleted_at IS NULL
                ORDER BY last_seen_at DESC
                """,
                [user_id],
            ).fetchall()
        finally:
            connection.close()
        return [dict(row) for row in rows]

    def get_active_session(self, session_id: str) -> dict[str, Any] | None:
        connection = get_membership_connection()
        try:
            row = connection.execute(
                """
                SELECT *
                FROM membership_session
                WHERE id = ?
                  AND revoked_at IS NULL
                  AND deleted_at IS NULL
                """,
                [session_id],
            ).fetchone()
        finally:
            connection.close()
        return dict(row) if row else None

    def _insert_audit(
        self,
        connection: sqlite3.Connection,
        *,
        actor_user_id: str | None,
        action: str,
        resource_type: str,
        resource_id: str,
        outcome: str,
        ip_address: str,
        user_agent: str,
        metadata: dict[str, Any],
    ) -> None:
        now = utc_now_iso()
        connection.execute(
            """
            INSERT INTO membership_audit_log (
                id, actor_user_id, action, resource_type, resource_id, outcome,
                ip_address, user_agent, metadata_json, created_at, updated_at
            )
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            [
                str(uuid.uuid4()),
                actor_user_id,
                action,
                resource_type,
                resource_id,
                outcome,
                ip_address,
                user_agent,
                json.dumps(metadata, ensure_ascii=False),
                now,
                now,
            ],
        )

    def _insert_notification(
        self,
        connection: sqlite3.Connection,
        *,
        template_code: str,
        recipient_user_id: str,
        payload: dict[str, Any],
    ) -> None:
        now = utc_now_iso()
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
                recipient_user_id,
                json.dumps(payload, ensure_ascii=False),
                now,
                now,
            ],
        )
