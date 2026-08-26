import sqlite3
from typing import Any

from src.features.membership.core.exceptions import (
    ConflictError,
    ForbiddenError,
    ResourceNotFoundError,
    ValidationFailureError,
)
from src.features.membership.repositories.group_repository import GroupRepository
from src.features.membership.services.audit_service import AuditService
from src.features.membership.services.bootstrap_service import apply_membership_migration
from src.features.membership.services.rbac_service import RbacService


class GroupService:
    def __init__(
        self,
        repository: GroupRepository | None = None,
        rbac_service: RbacService | None = None,
    ):
        apply_membership_migration()
        self.repository = repository or GroupRepository()
        self.rbac_service = rbac_service or RbacService()
        self.audit = AuditService()

    def list_groups(self, actor_user_id: str, *, keyword: str = "", status_filter: str = "") -> dict[str, Any]:
        is_admin = self._is_admin(actor_user_id)
        groups = self.repository.list_groups(keyword=keyword, status_filter=status_filter)
        return {
            "groups": [self._with_access(group, actor_user_id, is_admin, include_members=False) for group in groups],
            "canCreateGroup": is_admin,
        }

    def get_group(self, group_id: str, actor_user_id: str) -> dict[str, Any]:
        group = self._require_group(group_id)
        return self._with_access(group, actor_user_id, self._is_admin(actor_user_id), include_members=True)

    def create_group(self, payload: dict[str, Any], actor_user_id: str) -> dict[str, Any]:
        self._require_admin(actor_user_id)
        self._ensure_unique_code(payload["code"])
        self._validate_users([payload.get("masterUserId")] if payload.get("masterUserId") else [])
        try:
            group = self.repository.create_group(payload, actor_user_id)
        except sqlite3.IntegrityError as exc:
            if self.repository.group_code_exists(payload["code"]):
                self._raise_code_conflict(payload["code"], exc)
            raise
        self._record(actor_user_id, "membership.group.create", group["id"], {"code": group["code"]})
        return self._with_access(group, actor_user_id, True, include_members=True)

    def update_group(self, group_id: str, payload: dict[str, Any], actor_user_id: str) -> dict[str, Any]:
        self._require_admin(actor_user_id)
        self._require_group(group_id)
        self._ensure_unique_code(payload["code"], exclude_id=group_id)
        self._validate_users([payload.get("masterUserId")] if payload.get("masterUserId") else [])
        try:
            group = self.repository.update_group(group_id, payload, actor_user_id)
        except sqlite3.IntegrityError as exc:
            if self.repository.group_code_exists(payload["code"], exclude_id=group_id):
                self._raise_code_conflict(payload["code"], exc)
            raise
        if group is None:
            raise ResourceNotFoundError("Group not found.", {"id": group_id})
        self._record(
            actor_user_id,
            "membership.group.update",
            group_id,
            {"code": group["code"], "masterUserId": group["masterUserId"]},
        )
        return self._with_access(group, actor_user_id, True, include_members=True)

    def delete_group(self, group_id: str, actor_user_id: str) -> None:
        self._require_admin(actor_user_id)
        group = self._require_group(group_id)
        if not self.repository.delete_group(group_id):
            raise ResourceNotFoundError("Group not found.", {"id": group_id})
        self._record(actor_user_id, "membership.group.delete", group_id, {"code": group["code"]})

    def add_members(self, group_id: str, user_ids: list[str], actor_user_id: str) -> dict[str, Any]:
        self._require_member_manager(group_id, actor_user_id)
        unique_user_ids = list(dict.fromkeys(user_ids))
        self._validate_users(unique_user_ids)
        self.repository.add_members(group_id, unique_user_ids, actor_user_id)
        self._record(actor_user_id, "membership.group.member.add", group_id, {"userIds": unique_user_ids})
        return self.get_group(group_id, actor_user_id)

    def remove_member(self, group_id: str, user_id: str, actor_user_id: str) -> dict[str, Any]:
        group = self._require_group(group_id)
        self._require_member_manager(group_id, actor_user_id)
        if group["masterUserId"] == user_id:
            raise ValidationFailureError(
                "Group master cannot be removed. Assign another master first.",
                {"userId": user_id},
            )
        if not self.repository.remove_member(group_id, user_id):
            raise ResourceNotFoundError("Group member not found.", {"userId": user_id})
        self._record(actor_user_id, "membership.group.member.delete", group_id, {"userId": user_id})
        return self.get_group(group_id, actor_user_id)

    def remove_members(self, group_id: str, user_ids: list[str], actor_user_id: str) -> dict[str, Any]:
        group = self._require_group(group_id)
        self._require_member_manager(group_id, actor_user_id)
        unique_user_ids = list(dict.fromkeys(user_ids))
        if group["masterUserId"] in unique_user_ids:
            raise ValidationFailureError(
                "Group master cannot be removed. Assign another master first.",
                {"userId": group["masterUserId"]},
            )
        if not self.repository.remove_members(group_id, unique_user_ids):
            raise ResourceNotFoundError("One or more group members were not found.", {"userIds": unique_user_ids})
        self._record(
            actor_user_id,
            "membership.group.member.batch_delete",
            group_id,
            {"userIds": unique_user_ids, "count": len(unique_user_ids)},
        )
        return self.get_group(group_id, actor_user_id)

    def list_available_users(self, actor_user_id: str) -> list[dict[str, str]]:
        if not self._is_admin(actor_user_id) and not self.repository.is_any_group_master(actor_user_id):
            raise ForbiddenError("Only administrators or group masters can select group members.")
        return self.repository.list_available_users()

    def _with_access(
        self,
        group: dict[str, Any],
        actor_user_id: str,
        is_admin: bool,
        *,
        include_members: bool,
    ) -> dict[str, Any]:
        members = group.get("members")
        if include_members and members is None:
            members = self.repository.list_members(group["id"])
        return {
            **group,
            "members": members if include_members else [],
            "canEditGroup": is_admin,
            "canManageMembers": is_admin or group["masterUserId"] == actor_user_id,
        }

    def _require_group(self, group_id: str) -> dict[str, Any]:
        group = self.repository.get_group(group_id)
        if group is None:
            raise ResourceNotFoundError("Group not found.", {"id": group_id})
        return group

    def _require_member_manager(self, group_id: str, actor_user_id: str) -> None:
        self._require_group(group_id)
        if not self._is_admin(actor_user_id) and not self.repository.is_master(group_id, actor_user_id):
            raise ForbiddenError("Only administrators or the group master can manage members.")

    def _require_admin(self, actor_user_id: str) -> None:
        if not self._is_admin(actor_user_id):
            raise ForbiddenError("Only administrators can manage groups.")

    def _is_admin(self, actor_user_id: str) -> bool:
        return self.rbac_service.user_has_permission(actor_user_id, "membership.write")

    def _validate_users(self, user_ids: list[str]) -> None:
        if not self.repository.users_exist(user_ids):
            raise ValidationFailureError("One or more users do not exist.", {"userIds": user_ids})

    def _ensure_unique_code(self, code: str, *, exclude_id: str | None = None) -> None:
        if self.repository.group_code_exists(code, exclude_id=exclude_id):
            self._raise_code_conflict(code)

    @staticmethod
    def _raise_code_conflict(code: str, cause: Exception | None = None) -> None:
        error = ConflictError(
            "群組代碼已存在，請使用其他代碼。",
            {"field": "code", "code": code},
        )
        if cause is not None:
            raise error from cause
        raise error

    def _record(self, actor_user_id: str, action: str, group_id: str, metadata: dict[str, Any]) -> None:
        self.audit.record(
            actor_user_id=actor_user_id,
            action=action,
            resource_type="membership_group",
            resource_id=group_id,
            metadata={"module": "群組管理", **metadata},
        )
