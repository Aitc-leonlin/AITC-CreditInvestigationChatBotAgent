from typing import Any

from src.features.membership.core.exceptions import ConflictError, ResourceNotFoundError, ValidationFailureError
from src.features.membership.core.permission_registry import (
    permission_by_code,
    permission_exists,
    permission_group_rows,
    permission_rows,
)
from src.features.membership.repositories.rbac_repository import RbacRepository
from src.shared.database.connection import DatabaseIntegrityError


class RbacService:
    def __init__(self, repository: RbacRepository | None = None):
        self.repository = repository or RbacRepository()

    def list_roles(self, *, keyword: str = "", status_filter: str = "") -> list[dict[str, Any]]:
        return self.repository.list_roles(keyword=keyword, status_filter=status_filter)

    def get_role(self, role_id: str) -> dict[str, Any]:
        role = self.repository.get_role(role_id)
        if role is None:
            raise ResourceNotFoundError("Role not found.", {"id": role_id})
        return role

    def create_role(self, payload: dict[str, Any]) -> dict[str, Any]:
        try:
            return self.repository.create_role(payload)
        except DatabaseIntegrityError as exc:
            raise ConflictError("Role code already exists.") from exc

    def update_role(self, role_id: str, payload: dict[str, Any]) -> dict[str, Any]:
        self.get_role(role_id)
        role = self.repository.update_role(role_id, payload)
        if role is None:
            raise ResourceNotFoundError("Role not found.", {"id": role_id})
        return role

    def delete_role(self, role_id: str) -> None:
        role = self.get_role(role_id)
        if role["isSystem"]:
            raise ValidationFailureError("System role cannot be deleted.")
        if not self.repository.delete_role(role_id):
            raise ResourceNotFoundError("Role not found.", {"id": role_id})

    def list_permission_groups(self) -> list[dict[str, Any]]:
        return permission_group_rows()

    def create_permission_group(self, payload: dict[str, Any]) -> dict[str, Any]:
        raise ValidationFailureError(
            "Permission groups are system-defined and must be managed by code and migrations."
        )

    def update_permission_group(self, group_id: str, payload: dict[str, Any]) -> dict[str, Any]:
        raise ValidationFailureError(
            "Permission groups are system-defined and must be managed by code and migrations.",
            {"id": group_id},
        )

    def delete_permission_group(self, group_id: str) -> None:
        raise ValidationFailureError(
            "Permission groups are system-defined and must be managed by code and migrations.",
            {"id": group_id},
        )

    def list_permissions(
        self,
        *,
        keyword: str = "",
        group_id: str = "",
        status_filter: str = "",
    ) -> list[dict[str, Any]]:
        return permission_rows(
            keyword=keyword,
            group_id=group_id,
            status_filter=status_filter,
        )

    def get_permission(self, permission_id: str) -> dict[str, Any]:
        permission = permission_by_code(permission_id)
        if permission is None:
            raise ResourceNotFoundError("Permission not found.", {"id": permission_id})
        return permission

    def create_permission(self, payload: dict[str, Any]) -> dict[str, Any]:
        raise ValidationFailureError(
            "Permissions are system-defined and must be managed by code and migrations."
        )

    def update_permission(self, permission_id: str, payload: dict[str, Any]) -> dict[str, Any]:
        raise ValidationFailureError(
            "Permissions are system-defined and must be managed by code and migrations.",
            {"id": permission_id},
        )

    def delete_permission(self, permission_id: str) -> None:
        raise ValidationFailureError(
            "Permissions are system-defined and must be managed by code and migrations.",
            {"id": permission_id},
        )

    def get_role_permissions(self, role_id: str) -> dict[str, Any]:
        self.get_role(role_id)
        return {
            "roleId": role_id,
            "permissionIds": self.repository.get_role_permission_codes(role_id),
        }

    def set_role_permissions(self, role_id: str, permission_ids: list[str]) -> dict[str, Any]:
        self.get_role(role_id)
        unique_permission_ids = list(dict.fromkeys(permission_ids))
        if not all(permission_exists(permission_id) for permission_id in unique_permission_ids):
            raise ValidationFailureError("One or more permissions do not exist.")
        return {
            "roleId": role_id,
            "permissionIds": self.repository.set_role_permissions(role_id, unique_permission_ids),
        }

    def get_user_roles(self, user_id: str) -> dict[str, Any]:
        if not self.repository.user_exists(user_id):
            raise ResourceNotFoundError("User not found.", {"id": user_id})
        return {
            "userId": user_id,
            "roleIds": self.repository.get_user_role_ids(user_id),
        }

    def set_user_roles(
        self,
        *,
        user_id: str,
        role_ids: list[str],
        organization_id: str | None = None,
    ) -> dict[str, Any]:
        if not self.repository.user_exists(user_id):
            raise ResourceNotFoundError("User not found.", {"id": user_id})
        unique_role_ids = list(dict.fromkeys(role_ids))
        if not self.repository.role_ids_exist(unique_role_ids):
            raise ValidationFailureError("One or more roles do not exist.")
        return {
            "userId": user_id,
            "roleIds": self.repository.set_user_roles(user_id, unique_role_ids, organization_id),
        }

    def list_user_permission_codes(self, user_id: str) -> list[str]:
        return self.repository.list_user_permissions(user_id)

    def user_has_permission(self, user_id: str, permission_code: str) -> bool:
        return self.repository.has_permission(user_id, permission_code)

    def _ensure_unique_code(
        self,
        table_name: str,
        code: str,
        exclude_id: str | None = None,
    ) -> None:
        if self.repository.code_exists(table_name, code, exclude_id=exclude_id):
            raise ConflictError("Code already exists.", {"code": code})
