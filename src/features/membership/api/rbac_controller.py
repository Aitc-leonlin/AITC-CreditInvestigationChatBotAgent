"""Membership RBAC 權限管理 API。

負責目前使用者權限查詢、角色 CRUD、權限分組查詢、權限查詢，以及角色-權限、
使用者-角色 mapping 設定。
"""

from fastapi import Depends, Query

from src.features.membership.api.base import create_membership_router
from src.features.membership.core.auth_middleware import require_authenticated_user, require_permission
from src.features.membership.core.responses import ok
from src.features.membership.schemas.common import StandardResponse
from src.features.membership.schemas.rbac import (
    CurrentPermissionsResponse,
    IdsCommand,
    PermissionGroupResponse,
    PermissionResponse,
    RoleCommand,
    RolePermissionsResponse,
    RoleResponse,
    UserRolesCommand,
    UserRolesResponse,
)
from src.features.membership.services.rbac_service import RbacService


rbac_router = create_membership_router(
    prefix="/api/membership/rbac",
    tags=["membership-rbac"],
)


def rbac_service() -> RbacService:
    return RbacService()


RBAC_VIEW = "rbac.view"
RBAC_ADD = "rbac.add"
RBAC_EDIT = "rbac.edit"
RBAC_DELETE = "rbac.delete"


@rbac_router.get(
    "/me/permissions",
    response_model=StandardResponse[CurrentPermissionsResponse],
)
async def get_my_permissions(user: dict = Depends(require_authenticated_user)):
    return ok({"permissions": rbac_service().list_user_permission_codes(user["id"])})


@rbac_router.get(
    "/roles",
    response_model=StandardResponse[list[RoleResponse]],
)
async def list_roles(
    keyword: str = Query(default=""),
    status: str = Query(default=""),
    _: dict = Depends(require_permission(RBAC_VIEW)),
):
    return ok(rbac_service().list_roles(keyword=keyword, status_filter=status))


@rbac_router.post(
    "/roles",
    response_model=StandardResponse[RoleResponse],
)
async def create_role(
    payload: RoleCommand,
    _: dict = Depends(require_permission(RBAC_ADD)),
):
    return ok(rbac_service().create_role(payload.model_dump()))


@rbac_router.put(
    "/roles/{role_id}",
    response_model=StandardResponse[RoleResponse],
)
async def update_role(
    role_id: str,
    payload: RoleCommand,
    _: dict = Depends(require_permission(RBAC_EDIT)),
):
    return ok(rbac_service().update_role(role_id, payload.model_dump()))


@rbac_router.delete(
    "/roles/{role_id}",
    response_model=StandardResponse[dict[str, bool]],
)
async def delete_role(
    role_id: str,
    _: dict = Depends(require_permission(RBAC_DELETE)),
):
    rbac_service().delete_role(role_id)
    return ok({"deleted": True})


@rbac_router.get(
    "/permission-groups",
    response_model=StandardResponse[list[PermissionGroupResponse]],
)
async def list_permission_groups(_: dict = Depends(require_permission(RBAC_VIEW))):
    return ok(rbac_service().list_permission_groups())


@rbac_router.get(
    "/permissions",
    response_model=StandardResponse[list[PermissionResponse]],
)
async def list_permissions(
    keyword: str = Query(default=""),
    groupId: str = Query(default=""),
    status: str = Query(default=""),
    _: dict = Depends(require_permission(RBAC_VIEW)),
):
    return ok(
        rbac_service().list_permissions(
            keyword=keyword,
            group_id=groupId,
            status_filter=status,
        )
    )


@rbac_router.get(
    "/roles/{role_id}/permissions",
    response_model=StandardResponse[RolePermissionsResponse],
)
async def get_role_permissions(
    role_id: str,
    _: dict = Depends(require_permission(RBAC_VIEW)),
):
    return ok(rbac_service().get_role_permissions(role_id))


@rbac_router.put(
    "/roles/{role_id}/permissions",
    response_model=StandardResponse[RolePermissionsResponse],
)
async def set_role_permissions(
    role_id: str,
    payload: IdsCommand,
    _: dict = Depends(require_permission(RBAC_EDIT)),
):
    return ok(rbac_service().set_role_permissions(role_id, payload.ids))


@rbac_router.get(
    "/users/{user_id}/roles",
    response_model=StandardResponse[UserRolesResponse],
)
async def get_user_roles(
    user_id: str,
    _: dict = Depends(require_permission(RBAC_VIEW)),
):
    return ok(rbac_service().get_user_roles(user_id))


@rbac_router.put(
    "/users/{user_id}/roles",
    response_model=StandardResponse[UserRolesResponse],
)
async def set_user_roles(
    user_id: str,
    payload: UserRolesCommand,
    _: dict = Depends(require_permission(RBAC_EDIT)),
):
    return ok(
        rbac_service().set_user_roles(
            user_id=user_id,
            role_ids=payload.roleIds,
            organization_id=payload.organizationId,
        )
    )
