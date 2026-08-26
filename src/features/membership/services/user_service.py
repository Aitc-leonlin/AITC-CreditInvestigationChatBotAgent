import sqlite3
from typing import Any

from src.features.membership.core.exceptions import ConflictError, ResourceNotFoundError, ValidationFailureError
from src.features.membership.core.password import PASSWORD_ALGORITHM, hash_password, verify_password
from src.features.membership.core.time import utc_now_iso
from src.features.membership.repositories.user_repository import MembershipUserRepository
from src.features.membership.services.bootstrap_service import apply_membership_migration


class UserManagementService:
    def __init__(self, repository: MembershipUserRepository | None = None):
        apply_membership_migration()
        self.repository = repository or MembershipUserRepository()

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
        return self.repository.list_users(
            page=page,
            page_size=page_size,
            keyword=keyword,
            status_filter=status_filter,
            organization_id=organization_id,
            locked=locked,
        )

    def get_user(self, user_id: str) -> dict[str, Any]:
        user = self.repository.get_user_detail(user_id)
        if user is None:
            raise ResourceNotFoundError("User not found.", {"id": user_id})
        return user

    def create_user(self, payload: dict[str, Any]) -> dict[str, Any]:
        department_id = payload.get("departmentId") or payload.get("organizationId")
        self._validate_organization(department_id)
        self._validate_position(payload.get("positionId"))
        role_ids = list(dict.fromkeys(payload.get("roleIds") or ["role-default-user"]))
        if not self.repository.role_ids_exist(role_ids):
            raise ValidationFailureError("One or more roles do not exist.", {"roleIds": role_ids})
        self._validate_unique_identity(
            username=payload["username"],
            email=str(payload["email"]),
        )
        try:
            created = self.repository.create_user_with_credential(
                user_values=self._to_user_values(payload),
                password_hash=hash_password(payload["password"]),
                password_algorithm=PASSWORD_ALGORITHM,
                must_change_password=bool(payload.get("mustChangePassword", True)),
                role_ids=role_ids,
            )
            return self.get_user(created["id"])
        except sqlite3.IntegrityError as exc:
            raise ConflictError("User identity already exists.") from exc

    def update_user(self, user_id: str, payload: dict[str, Any]) -> dict[str, Any]:
        
        try:
            self.get_user(user_id)
            department_id = payload.get("departmentId") or payload.get("organizationId")
            self._validate_organization(department_id)
            self._validate_position(payload.get("positionId"))
            role_ids = payload.get("roleIds")
            unique_role_ids: list[str] = []
            if role_ids is not None:
                unique_role_ids = list(dict.fromkeys(role_ids or ["role-default-user"]))
                if not self.repository.role_ids_exist(unique_role_ids):
                    raise ValidationFailureError("One or more roles do not exist.", {"roleIds": unique_role_ids})

            self._validate_unique_identity(
                username=payload["username"],
                email=str(payload["email"]),
                exclude_user_id=user_id,
            )

            user_values = self._to_user_values(payload)
            updated = self.repository.update_user_values(
                user_id,
                user_values,
            )
            if updated is None:
                raise ResourceNotFoundError("User not found.", {"id": user_id})

            if role_ids is not None:
                self.repository.replace_user_roles(
                    user_id,
                    unique_role_ids,
                    department_id,
                )

            return self.get_user(user_id)
        except Exception as exc:
            raise

    def update_profile(self, user_id: str, payload: dict[str, Any]) -> dict[str, Any]:
        self.get_user(user_id)
        self._validate_unique_identity(
            username="",
            email=str(payload["email"]),
            exclude_user_id=user_id,
            check_username=False,
        )
        updated = self.repository.update_user_values(
            user_id,
            {
                "display_name": payload["displayName"],
                "email": str(payload["email"]),
                "locale": payload["locale"],
                "timezone": payload["timezone"],
            },
        )
        if updated is None:
            raise ResourceNotFoundError("User not found.", {"id": user_id})
        return updated

    def delete_user(self, user_id: str) -> None:
        deleted = self.repository.soft_delete_user(user_id)
        if not deleted:
            raise ResourceNotFoundError("User not found.", {"id": user_id})

    def set_status(self, user_id: str, status: str) -> dict[str, Any]:
        self.get_user(user_id)
        updated = self.repository.update_user_values(user_id, {"status": status})
        if updated is None:
            raise ResourceNotFoundError("User not found.", {"id": user_id})
        return updated

    def lock_user(self, user_id: str, locked_until: str | None = None) -> dict[str, Any]:
        self.get_user(user_id)
        effective_locked_until = locked_until or "9999-12-31T23:59:59+00:00"
        self.repository.update_credential_values(
            user_id,
            {
                "locked_until": effective_locked_until,
            },
        )
        self.repository.insert_notification(
            user_id,
            "MEMBERSHIP_ACCOUNT_LOCKED",
            {"lockedUntil": effective_locked_until, "source": "admin"},
        )
        return self.get_user(user_id)

    def unlock_user(self, user_id: str) -> dict[str, Any]:
        self.get_user(user_id)
        self.repository.update_credential_values(
            user_id,
            {
                "locked_until": None,
                "failed_login_count": 0,
            },
        )
        return self.get_user(user_id)

    def change_password(
        self,
        *,
        user_id: str,
        current_password: str,
        new_password: str,
    ) -> dict[str, Any]:
        self.get_user(user_id)
        credential = self.repository.get_credential(user_id)
        if credential is None:
            raise ResourceNotFoundError("User credential not found.", {"id": user_id})
        if not verify_password(current_password, credential["password_hash"]):
            raise ValidationFailureError("Current password is incorrect.")
        self.repository.update_credential_values(
            user_id,
            {
                "password_hash": hash_password(new_password),
                "password_algorithm": PASSWORD_ALGORITHM,
                "password_changed_at": utc_now_iso(),
                "must_change_password": 0,
                "failed_login_count": 0,
                "locked_until": None,
            },
        )
        return self.get_user(user_id)

    def reset_password(
        self,
        *,
        user_id: str,
        new_password: str,
        must_change_password: bool,
    ) -> dict[str, Any]:
        self.get_user(user_id)
        updated = self.repository.update_credential_values(
            user_id,
            {
                "password_hash": hash_password(new_password),
                "password_algorithm": PASSWORD_ALGORITHM,
                "password_changed_at": utc_now_iso(),
                "must_change_password": 1 if must_change_password else 0,
                "failed_login_count": 0,
                "locked_until": None,
            },
        )
        if not updated:
            raise ResourceNotFoundError("User credential not found.", {"id": user_id})
        return self.get_user(user_id)

    def _validate_organization(self, organization_id: str | None) -> None:
        if not self.repository.organization_exists(organization_id):
            raise ValidationFailureError(
                "Organization does not exist or is inactive.",
                {"organizationId": organization_id},
            )

    def _validate_position(self, position_id: str | None) -> None:
        if not self.repository.position_exists(position_id):
            raise ValidationFailureError(
                "Position does not exist or is inactive.",
                {"positionId": position_id},
            )

    def _validate_unique_identity(
        self,
        *,
        username: str,
        email: str,
        exclude_user_id: str | None = None,
        check_username: bool = True,
    ) -> None:
        exists = self.repository.username_or_email_exists(
            username=username,
            email=email,
            exclude_user_id=exclude_user_id,
        )
        details: dict[str, str] = {}
        if check_username and exists["username"]:
            details["username"] = "username already exists"
        if exists["email"]:
            details["email"] = "email already exists"
        if details:
            raise ConflictError("User identity already exists.", details)

    def _to_user_values(self, payload: dict[str, Any]) -> dict[str, Any]:
        return {
            "username": payload["username"],
            "email": str(payload["email"]),
            "display_name": payload["displayName"],
            "employee_no": payload.get("employeeNo", ""),
            "organization_id": payload.get("departmentId") or payload.get("organizationId"),
            "position_id": payload.get("positionId"),
            "status": payload.get("status", "ACTIVE"),
            "locale": payload.get("locale", "zh-TW"),
            "timezone": payload.get("timezone", "Asia/Taipei"),
            "last_login_at": payload.get("lastLoginAt"),
        }
