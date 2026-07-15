import os
import time
from datetime import datetime, timedelta, timezone
from typing import Any

from src.features.membership.core.exceptions import ForbiddenError, ResourceNotFoundError, UnauthorizedError, ValidationFailureError
from src.features.membership.core.jwt import decode_jwt, encode_jwt
from src.features.membership.core.password import PASSWORD_ALGORITHM, hash_password, verify_password
from src.features.membership.core.tokens import generate_opaque_token, hash_token
from src.features.membership.core.time import utc_now_iso
from src.features.membership.repositories.auth_repository import AuthRepository
from src.features.membership.services.bootstrap_service import apply_membership_migration


ACCESS_TOKEN_TTL_SECONDS = int(os.getenv("MEMBERSHIP_ACCESS_TOKEN_TTL_SECONDS", "900"))
REFRESH_TOKEN_TTL_SECONDS = int(os.getenv("MEMBERSHIP_REFRESH_TOKEN_TTL_SECONDS", "86400"))
REMEMBER_ME_REFRESH_TOKEN_TTL_SECONDS = int(
    os.getenv("MEMBERSHIP_REMEMBER_ME_REFRESH_TOKEN_TTL_SECONDS", str(30 * 86400))
)
PASSWORD_RESET_TTL_SECONDS = int(os.getenv("MEMBERSHIP_PASSWORD_RESET_TTL_SECONDS", "1800"))
EMAIL_VERIFICATION_TTL_SECONDS = int(os.getenv("MEMBERSHIP_EMAIL_VERIFICATION_TTL_SECONDS", "86400"))
MAX_FAILED_LOGIN_COUNT = int(os.getenv("MEMBERSHIP_MAX_FAILED_LOGIN_COUNT", "5"))
LOCK_MINUTES = int(os.getenv("MEMBERSHIP_LOGIN_LOCK_MINUTES", "15"))


class AuthService:
    def __init__(self, repository: AuthRepository | None = None):
        apply_membership_migration()
        self.repository = repository or AuthRepository()

    def login(
        self,
        *,
        login: str,
        password: str,
        remember_me: bool,
        ip_address: str,
        user_agent: str,
    ) -> dict[str, Any]:
        user = self.repository.find_user_by_login(login)
        if user is None:
            raise UnauthorizedError("Invalid username/email or password.")
        self._assert_user_can_login(user)

        if not verify_password(password, user["password_hash"]):
            failed_count = int(user.get("failed_login_count") or 0) + 1
            locked_until = None
            if failed_count >= MAX_FAILED_LOGIN_COUNT:
                locked_until = self._future_iso(minutes=LOCK_MINUTES)
            self.repository.record_failed_login(
                user_id=user["id"],
                failed_count=failed_count,
                locked_until=locked_until,
                ip_address=ip_address,
                user_agent=user_agent,
            )
            raise UnauthorizedError("Invalid username/email or password.")

        refresh_token = generate_opaque_token()
        refresh_ttl = (
            REMEMBER_ME_REFRESH_TOKEN_TTL_SECONDS if remember_me else REFRESH_TOKEN_TTL_SECONDS
        )
        refresh_expires_at = self._future_iso(seconds=refresh_ttl)
        session = self.repository.create_session_and_refresh_token(
            user_id=user["id"],
            refresh_token_hash=hash_token(refresh_token),
            expires_at=refresh_expires_at,
            remember_me=remember_me,
            ip_address=ip_address,
            user_agent=user_agent,
        )
        self.repository.record_successful_login(
            user_id=user["id"],
            ip_address=ip_address,
            user_agent=user_agent,
        )
        fresh_user = self.repository.get_user_by_id(user["id"]) or user
        return self._build_token_response(
            user=fresh_user,
            refresh_token=refresh_token,
            session_id=session["sessionId"],
            refresh_expires_at=refresh_expires_at,
        )

    def refresh(self, *, refresh_token: str) -> dict[str, Any]:
        token_row = self.repository.get_refresh_token(hash_token(refresh_token))
        if token_row is None:
            raise UnauthorizedError("Invalid refresh token.")
        if self._is_past(token_row["expires_at"]):
            self.repository.revoke_session(refresh_token_hash=hash_token(refresh_token))
            raise UnauthorizedError("Refresh token expired.")
        user = self.repository.get_user_by_id(token_row["user_id"])
        if user is None:
            raise UnauthorizedError("User not found.")
        self._assert_user_can_login(user)
        if token_row.get("session_id"):
            self.repository.touch_session(token_row["session_id"])
        return self._build_token_response(
            user=user,
            refresh_token=refresh_token,
            session_id=token_row.get("session_id") or "",
            refresh_expires_at=token_row["expires_at"],
        )

    def logout(self, *, refresh_token: str | None, access_token: str | None) -> dict[str, bool]:
        revoked = False
        if refresh_token:
            revoked = self.repository.revoke_session(refresh_token_hash=hash_token(refresh_token))
        elif access_token:
            payload = decode_jwt(access_token)
            session_id = str(payload.get("sid") or "")
            if session_id:
                revoked = self.repository.revoke_session(session_id=session_id)
        return {"loggedOut": True, "revoked": revoked}

    def me(self, access_token: str) -> dict[str, Any]:
        payload = self._decode_and_validate_session(access_token)
        user = self.repository.get_user_by_id(str(payload.get("sub") or ""))
        if user is None:
            raise UnauthorizedError("User not found.")
        return self._auth_user(user)

    def forgot_password(
        self,
        *,
        email: str,
        ip_address: str,
        user_agent: str,
    ) -> dict[str, Any]:
        # NOTE: 目前尚未串接實際寄信服務。這裡只建立 reset token、寫入通知 outbox，
        # 並把 token 回傳給前端供開發測試；正式產品應改由 mail worker 寄出重設連結。
        user = self.repository.find_user_by_login(email)
        if user is None:
            return {"accepted": True, "resetToken": None}
        token = generate_opaque_token()
        self.repository.create_password_reset_token(
            user_id=user["id"],
            token_hash=hash_token(token),
            expires_at=self._future_iso(seconds=PASSWORD_RESET_TTL_SECONDS),
            ip_address=ip_address,
            user_agent=user_agent,
        )
        return {"accepted": True, "resetToken": token}

    def reset_password(self, *, token: str, new_password: str) -> dict[str, bool]:
        token_row = self.repository.get_password_reset_token(hash_token(token))
        if token_row is None:
            raise ValidationFailureError("Invalid password reset token.")
        if self._is_past(token_row["expires_at"]):
            raise ValidationFailureError("Password reset token expired.")
        self.repository.update_password(
            user_id=token_row["user_id"],
            password_hash=hash_password(new_password),
            password_algorithm=PASSWORD_ALGORITHM,
        )
        self.repository.mark_password_reset_used(token_row["id"])
        return {"reset": True}

    def request_email_verification(
        self,
        *,
        access_token: str,
        ip_address: str,
        user_agent: str,
    ) -> dict[str, Any]:
        # NOTE: 目前尚未串接實際寄信服務。這裡只建立 verification token、寫入通知 outbox，
        # 並把 token 回傳給前端供開發測試；正式產品應改由 mail worker 寄出驗證連結。
        payload = decode_jwt(access_token)
        user_id = str(payload.get("sub") or "")
        user = self.repository.get_user_by_id(user_id)
        if user is None:
            raise UnauthorizedError("User not found.")
        token = generate_opaque_token()
        self.repository.create_email_verification_token(
            user_id=user_id,
            token_hash=hash_token(token),
            expires_at=self._future_iso(seconds=EMAIL_VERIFICATION_TTL_SECONDS),
            ip_address=ip_address,
            user_agent=user_agent,
        )
        return {"accepted": True, "verificationToken": token}

    def verify_email(self, *, token: str) -> dict[str, bool]:
        token_row = self.repository.get_email_verification_token(hash_token(token))
        if token_row is None:
            raise ValidationFailureError("Invalid email verification token.")
        if self._is_past(token_row["expires_at"]):
            raise ValidationFailureError("Email verification token expired.")
        self.repository.mark_email_verified(
            token_id=token_row["id"],
            user_id=token_row["user_id"],
        )
        return {"verified": True}

    def list_sessions(self, access_token: str) -> list[dict[str, Any]]:
        payload = self._decode_and_validate_session(access_token)
        user_id = str(payload.get("sub") or "")
        sessions = self.repository.list_sessions(user_id)
        return [
            {
                "id": row["id"],
                "userId": row["user_id"],
                "rememberMe": bool(row["remember_me"]),
                "ipAddress": row["ip_address"],
                "userAgent": row["user_agent"],
                "startedAt": row["started_at"],
                "lastSeenAt": row["last_seen_at"],
                "expiresAt": row["expires_at"],
                "revokedAt": row["revoked_at"],
            }
            for row in sessions
        ]

    def authenticate_access_token(self, access_token: str) -> dict[str, Any]:
        payload = self._decode_and_validate_session(access_token)
        user = self.repository.get_user_by_id(str(payload.get("sub") or ""))
        if user is None:
            raise UnauthorizedError("User not found.")
        self._assert_user_can_login(user)
        return user

    def _decode_and_validate_session(self, access_token: str) -> dict[str, Any]:
        payload = decode_jwt(access_token)
        session_id = str(payload.get("sid") or "")
        if not session_id:
            raise UnauthorizedError("Access token session is missing.")
        session = self.repository.get_active_session(session_id)
        if session is None:
            raise UnauthorizedError("Session is no longer active.")
        if self._is_past(session["expires_at"]):
            self.repository.revoke_session(session_id=session_id)
            raise UnauthorizedError("Session expired.")
        self.repository.touch_session(session_id)
        return payload

    def _build_token_response(
        self,
        *,
        user: dict[str, Any],
        refresh_token: str,
        session_id: str,
        refresh_expires_at: str,
    ) -> dict[str, Any]:
        now = int(time.time())
        access_token = encode_jwt(
            {
                "iss": "aitc-membership",
                "sub": user["id"],
                "username": user["username"],
                "sid": session_id,
                "iat": now,
                "exp": now + ACCESS_TOKEN_TTL_SECONDS,
            }
        )
        return {
            "accessToken": access_token,
            "refreshToken": refresh_token,
            "tokenType": "Bearer",
            "expiresIn": ACCESS_TOKEN_TTL_SECONDS,
            "refreshExpiresAt": refresh_expires_at,
            "sessionId": session_id,
            "user": self._auth_user(user),
        }

    def _auth_user(self, user: dict[str, Any]) -> dict[str, Any]:
        return {
            "id": user["id"],
            "username": user["username"],
            "email": user["email"],
            "displayName": user["display_name"],
            "status": user["status"],
            "emailVerifiedAt": user.get("email_verified_at"),
            "mustChangePassword": bool(user.get("must_change_password") or 0),
        }

    def _assert_user_can_login(self, user: dict[str, Any]) -> None:
        if user.get("status") != "ACTIVE":
            raise ForbiddenError("User account is inactive.")
        locked_until = user.get("locked_until")
        if locked_until and not self._is_past(locked_until):
            raise ForbiddenError("User account is locked.", {"lockedUntil": locked_until})

    def _future_iso(self, *, seconds: int = 0, minutes: int = 0) -> str:
        return (datetime.now(timezone.utc) + timedelta(seconds=seconds, minutes=minutes)).isoformat()

    def _is_past(self, value: str) -> bool:
        try:
            return datetime.fromisoformat(value) <= datetime.now(timezone.utc)
        except Exception:
            return True
