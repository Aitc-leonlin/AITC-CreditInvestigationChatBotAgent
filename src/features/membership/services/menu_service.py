import sqlite3
from typing import Any

from src.features.membership.core.exceptions import ConflictError, ResourceNotFoundError, ValidationFailureError
from src.features.membership.repositories.menu_repository import MenuRepository
from src.features.membership.services.bootstrap_service import apply_membership_migration


class MenuService:
    def __init__(self, repository: MenuRepository | None = None):
        apply_membership_migration()
        self.repository = repository or MenuRepository()

    def list_menus(self, *, status_filter: str = "") -> list[dict[str, Any]]:
        return self._build_tree(self.repository.list_menus(status_filter=status_filter))

    def list_current_menus(self, user_id: str) -> list[dict[str, Any]]:
        return self._build_tree(self.repository.list_current_menus(user_id))

    def get_menu(self, menu_id: str) -> dict[str, Any]:
        menu = self.repository.get_menu(menu_id)
        if menu is None:
            raise ResourceNotFoundError("Menu item not found.", {"id": menu_id})
        return menu

    def create_menu(self, payload: dict[str, Any]) -> dict[str, Any]:
        self._validate_menu_payload(payload)
        self._ensure_unique_code(payload["code"])
        try:
            return self.repository.create_menu(payload)
        except sqlite3.IntegrityError as exc:
            raise ConflictError("Menu code already exists.") from exc

    def update_menu(self, menu_id: str, payload: dict[str, Any]) -> dict[str, Any]:
        self.get_menu(menu_id)
        self._validate_menu_payload(payload, menu_id=menu_id)
        self._ensure_unique_code(payload["code"], exclude_id=menu_id)
        menu = self.repository.update_menu(menu_id, payload)
        if menu is None:
            raise ResourceNotFoundError("Menu item not found.", {"id": menu_id})
        return menu

    def delete_menu(self, menu_id: str) -> None:
        self.get_menu(menu_id)
        if self.repository.has_children(menu_id):
            raise ValidationFailureError("Menu item with child menus cannot be deleted.")
        if not self.repository.delete_menu(menu_id):
            raise ResourceNotFoundError("Menu item not found.", {"id": menu_id})

    def list_menu_permissions(self, menu_id: str) -> list[dict[str, Any]]:
        self.get_menu(menu_id)
        return self.repository.list_menu_permissions(menu_id)

    def set_menu_permission(self, menu_id: str, payload: dict[str, Any]) -> dict[str, Any]:
        # NOTE: role-menu permission 的 canView 目前會影響 current menu 清單。
        # canCreate/canUpdate/canDelete 目前只儲存供前端/後續擴充使用，尚未成為 API 寫入操作的後端 enforcement。
        self.get_menu(menu_id)
        if not self.repository.role_exists(payload["roleId"]):
            raise ValidationFailureError("Role does not exist.", {"roleId": payload["roleId"]})
        permission = self.repository.set_menu_permission(menu_id, payload)
        if permission is None:
            raise ResourceNotFoundError("Menu permission not found.")
        return permission

    def delete_menu_permission(self, menu_id: str, role_id: str) -> None:
        self.get_menu(menu_id)
        if not self.repository.delete_menu_permission(menu_id, role_id):
            raise ResourceNotFoundError("Menu permission not found.")

    def _validate_menu_payload(self, payload: dict[str, Any], menu_id: str | None = None) -> None:
        parent_id = payload.get("parentId")
        if parent_id:
            if parent_id == menu_id:
                raise ValidationFailureError("Menu item cannot be its own parent.")
            self.get_menu(parent_id)
        required_permission_code = payload.get("requiredPermissionCode")
        if not self.repository.permission_code_exists(required_permission_code):
            raise ValidationFailureError(
                "Required permission does not exist.",
                {"requiredPermissionCode": required_permission_code},
            )

    def _ensure_unique_code(self, code: str, exclude_id: str | None = None) -> None:
        if self.repository.code_exists(code, exclude_id=exclude_id):
            raise ConflictError("Menu code already exists.", {"code": code})

    def _build_tree(self, menus: list[dict[str, Any]]) -> list[dict[str, Any]]:
        by_id = {menu["id"]: {**menu, "children": []} for menu in menus}
        roots: list[dict[str, Any]] = []
        for menu in sorted(by_id.values(), key=lambda item: (item["sortOrder"], item["title"])):
            parent_id = menu["parentId"]
            parent = by_id.get(parent_id) if parent_id else None
            if parent is None:
                roots.append(menu)
            else:
                parent["children"].append(menu)
        return roots
