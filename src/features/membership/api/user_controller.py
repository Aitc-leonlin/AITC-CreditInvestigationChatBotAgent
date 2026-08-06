"""Membership 使用者管理 API。

提供使用者清單、搜尋/篩選、新增、查詢、更新、刪除、啟用/停用、鎖定/解鎖、
個人資料更新、密碼變更與管理員重設密碼等後台帳號維護功能。
"""

from fastapi import Depends, Query, status

from src.features.membership.core.auth_middleware import require_any_permission, require_authenticated_user, require_permission
from src.features.membership.api.base import create_membership_router
from src.features.membership.core.responses import ok
from src.features.membership.schemas.common import StandardResponse
from src.features.membership.schemas.user import (
    AdminResetPasswordCommand,
    UserChangePasswordCommand,
    UserCreateCommand,
    UserListResponse,
    UserLockCommand,
    UserProfileUpdateCommand,
    UserResponse,
    UserStatusCommand,
    UserUpdateCommand,
)
from src.features.membership.services.user_service import UserManagementService


membership_user_router = create_membership_router(
    prefix="/api/membership/users",
    tags=["membership-users"],
    dependencies=[Depends(require_authenticated_user)],
)


def user_service() -> UserManagementService:
    return UserManagementService()


@membership_user_router.get(
    "",
    response_model=StandardResponse[UserListResponse],
)
async def list_users(
    page: int = Query(default=1, ge=1),
    pageSize: int = Query(default=20, ge=1, le=200),
    keyword: str = Query(default=""),
    status: str = Query(default=""),
    organizationId: str = Query(default=""),
    locked: bool | None = Query(default=None),
    _: dict = Depends(require_any_permission(["membership.read", "membership.user-roles"])),
):
    return ok(
        user_service().list_users(
            page=page,
            page_size=pageSize,
            keyword=keyword,
            status_filter=status,
            organization_id=organizationId,
            locked=locked,
        )
    )


@membership_user_router.post(
    "",
    response_model=StandardResponse[UserResponse],
    status_code=status.HTTP_201_CREATED,
)
async def create_user(
    payload: UserCreateCommand,
    _: dict = Depends(require_permission("membership.write")),
):
    return ok(user_service().create_user(payload.model_dump()))


@membership_user_router.get(
    "/{user_id}",
    response_model=StandardResponse[UserResponse],
)
async def get_user(user_id: str, _: dict = Depends(require_permission("membership.read"))):
    return ok(user_service().get_user(user_id))


@membership_user_router.put(
    "/{user_id}",
    response_model=StandardResponse[UserResponse],
)
async def update_user(
    user_id: str,
    payload: UserUpdateCommand,
    _: dict = Depends(require_permission("membership.write")),
):
    return ok(user_service().update_user(user_id, payload.model_dump()))


@membership_user_router.delete(
    "/{user_id}",
    response_model=StandardResponse[dict[str, bool]],
)
async def delete_user(user_id: str, _: dict = Depends(require_permission("membership.write"))):
    user_service().delete_user(user_id)
    return ok({"deleted": True})


@membership_user_router.patch(
    "/{user_id}/status",
    response_model=StandardResponse[UserResponse],
)
async def update_user_status(
    user_id: str,
    payload: UserStatusCommand,
    _: dict = Depends(require_permission("membership.write")),
):
    return ok(user_service().set_status(user_id, payload.status))


@membership_user_router.post(
    "/{user_id}/activate",
    response_model=StandardResponse[UserResponse],
)
async def activate_user(user_id: str, _: dict = Depends(require_permission("membership.write"))):
    return ok(user_service().set_status(user_id, "ACTIVE"))


@membership_user_router.post(
    "/{user_id}/deactivate",
    response_model=StandardResponse[UserResponse],
)
async def deactivate_user(user_id: str, _: dict = Depends(require_permission("membership.write"))):
    return ok(user_service().set_status(user_id, "INACTIVE"))


@membership_user_router.post(
    "/{user_id}/lock",
    response_model=StandardResponse[UserResponse],
)
async def lock_user(
    user_id: str,
    payload: UserLockCommand | None = None,
    _: dict = Depends(require_permission("membership.write")),
):
    locked_until = payload.lockedUntil if payload else None
    return ok(user_service().lock_user(user_id, locked_until))


@membership_user_router.post(
    "/{user_id}/unlock",
    response_model=StandardResponse[UserResponse],
)
async def unlock_user(user_id: str, _: dict = Depends(require_permission("membership.write"))):
    return ok(user_service().unlock_user(user_id))


@membership_user_router.put(
    "/{user_id}/profile",
    response_model=StandardResponse[UserResponse],
)
async def update_user_profile(
    user_id: str,
    payload: UserProfileUpdateCommand,
    _: dict = Depends(require_permission("membership.write")),
):
    return ok(user_service().update_profile(user_id, payload.model_dump()))


@membership_user_router.put(
    "/{user_id}/password",
    response_model=StandardResponse[UserResponse],
)
async def change_user_password(
    user_id: str,
    payload: UserChangePasswordCommand,
    _: dict = Depends(require_permission("membership.write")),
):
    return ok(
        user_service().change_password(
            user_id=user_id,
            current_password=payload.currentPassword,
            new_password=payload.newPassword,
        )
    )


@membership_user_router.put(
    "/{user_id}/reset-password",
    response_model=StandardResponse[UserResponse],
)
async def reset_user_password(
    user_id: str,
    payload: AdminResetPasswordCommand,
    _: dict = Depends(require_permission("membership.write")),
):
    return ok(
        user_service().reset_password(
            user_id=user_id,
            new_password=payload.newPassword,
            must_change_password=payload.mustChangePassword,
        )
    )
