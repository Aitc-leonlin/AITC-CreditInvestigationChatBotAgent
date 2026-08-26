"""Membership current menu API.

Menu visibility is derived from RBAC permissions. A menu with a
required_permission_code is visible when the current user has that permission;
menus without a required permission are structural containers.
"""

from fastapi import Depends

from src.features.membership.api.base import create_membership_router
from src.features.membership.core.auth_middleware import require_authenticated_user
from src.features.membership.core.responses import ok
from src.features.membership.schemas.common import StandardResponse
from src.features.membership.schemas.menu import CurrentMenuResponse
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
