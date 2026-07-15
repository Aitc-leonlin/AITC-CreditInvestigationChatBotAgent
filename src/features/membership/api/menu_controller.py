"""Membership 選單授權 API。

提供目前使用者可見選單、後台選單 CRUD，以及角色對選單的可視/新增/修改/刪除權限設定。
canView 已用於目前使用者選單查詢，其餘操作旗標目前主要供設定與後續權限 enforcement 擴充。
"""

from fastapi import Depends, Query

from src.features.membership.api.base import create_membership_router
from src.features.membership.core.auth_middleware import require_authenticated_user, require_permission
from src.features.membership.core.responses import ok
from src.features.membership.schemas.common import StandardResponse
from src.features.membership.schemas.menu import (
    CurrentMenuResponse,
    MenuCommand,
    MenuPermissionCommand,
    MenuPermissionResponse,
    MenuResponse,
)
from src.features.membership.services.menu_service import MenuService


menu_router = create_membership_router(
    prefix="/api/membership/menus",
    tags=["membership-menus"],
)


def menu_service() -> MenuService:
    return MenuService()


@menu_router.get(
    "/current",
    response_model=StandardResponse[CurrentMenuResponse],
)
async def get_current_menus(user: dict = Depends(require_authenticated_user)):
    return ok({"menus": menu_service().list_current_menus(user["id"])})


@menu_router.get(
    "",
    response_model=StandardResponse[list[MenuResponse]],
)
async def list_menus(
    status: str = Query(default=""),
    _: dict = Depends(require_permission("menu.read")),
):
    return ok(menu_service().list_menus(status_filter=status))


@menu_router.post(
    "",
    response_model=StandardResponse[MenuResponse],
)
async def create_menu(
    payload: MenuCommand,
    _: dict = Depends(require_permission("menu.manage")),
):
    return ok(menu_service().create_menu(payload.model_dump()))


@menu_router.put(
    "/{menu_id}",
    response_model=StandardResponse[MenuResponse],
)
async def update_menu(
    menu_id: str,
    payload: MenuCommand,
    _: dict = Depends(require_permission("menu.manage")),
):
    return ok(menu_service().update_menu(menu_id, payload.model_dump()))


@menu_router.delete(
    "/{menu_id}",
    response_model=StandardResponse[dict[str, bool]],
)
async def delete_menu(
    menu_id: str,
    _: dict = Depends(require_permission("menu.manage")),
):
    menu_service().delete_menu(menu_id)
    return ok({"deleted": True})


@menu_router.get(
    "/{menu_id}/permissions",
    response_model=StandardResponse[list[MenuPermissionResponse]],
)
async def list_menu_permissions(
    menu_id: str,
    _: dict = Depends(require_permission("menu.read")),
):
    return ok(menu_service().list_menu_permissions(menu_id))


@menu_router.put(
    "/{menu_id}/permissions",
    response_model=StandardResponse[MenuPermissionResponse],
)
async def set_menu_permission(
    menu_id: str,
    payload: MenuPermissionCommand,
    _: dict = Depends(require_permission("menu.manage")),
):
    return ok(menu_service().set_menu_permission(menu_id, payload.model_dump()))


@menu_router.delete(
    "/{menu_id}/permissions/{role_id}",
    response_model=StandardResponse[dict[str, bool]],
)
async def delete_menu_permission(
    menu_id: str,
    role_id: str,
    _: dict = Depends(require_permission("menu.manage")),
):
    menu_service().delete_menu_permission(menu_id, role_id)
    return ok({"deleted": True})
