from typing import Any

from src.features.membership.core.menu_registry import all_menu_rows, current_menu_rows
from src.features.membership.services.bootstrap_service import apply_membership_migration
from src.features.membership.services.rbac_service import RbacService


class MenuService:
    def __init__(self, rbac_service: RbacService | None = None):
        apply_membership_migration()
        self.rbac_service = rbac_service or RbacService()

    def list_menus(self, *, status_filter: str = "") -> list[dict[str, Any]]:
        rows = all_menu_rows()
        if status_filter:
            rows = [menu for menu in rows if menu["status"] == status_filter]
        return self._build_tree(rows)

    def list_current_menus(self, user_id: str) -> list[dict[str, Any]]:
        permission_codes = set(self.rbac_service.list_user_permission_codes(user_id))
        return self._build_tree(current_menu_rows(permission_codes))

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
