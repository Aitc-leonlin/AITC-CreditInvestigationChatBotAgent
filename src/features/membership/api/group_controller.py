from fastapi import Depends, Query, status

from src.features.membership.api.base import create_membership_router
from src.features.membership.core.auth_middleware import require_authenticated_user
from src.features.membership.core.responses import ok
from src.features.membership.schemas.common import StandardResponse
from src.features.membership.schemas.group import (
    GroupAvailableUserResponse,
    GroupCommand,
    GroupListResponse,
    GroupMemberAddCommand,
    GroupMemberRemoveCommand,
    GroupResponse,
)
from src.features.membership.services.group_service import GroupService


group_router = create_membership_router(
    prefix="/api/membership/groups",
    tags=["membership-groups"],
    dependencies=[Depends(require_authenticated_user)],
)


def group_service() -> GroupService:
    return GroupService()


@group_router.get("", response_model=StandardResponse[GroupListResponse])
async def list_groups(
    keyword: str = Query(default=""),
    statusFilter: str = Query(default=""),
    user: dict = Depends(require_authenticated_user),
):
    return ok(group_service().list_groups(user["id"], keyword=keyword, status_filter=statusFilter))


@group_router.get(
    "/available-users",
    response_model=StandardResponse[list[GroupAvailableUserResponse]],
)
async def list_available_users(user: dict = Depends(require_authenticated_user)):
    return ok(group_service().list_available_users(user["id"]))


@group_router.get("/{group_id}", response_model=StandardResponse[GroupResponse])
async def get_group(group_id: str, user: dict = Depends(require_authenticated_user)):
    return ok(group_service().get_group(group_id, user["id"]))


@group_router.post("", response_model=StandardResponse[GroupResponse], status_code=status.HTTP_201_CREATED)
async def create_group(payload: GroupCommand, user: dict = Depends(require_authenticated_user)):
    return ok(group_service().create_group(payload.model_dump(), user["id"]))


@group_router.put("/{group_id}", response_model=StandardResponse[GroupResponse])
async def update_group(
    group_id: str,
    payload: GroupCommand,
    user: dict = Depends(require_authenticated_user),
):
    return ok(group_service().update_group(group_id, payload.model_dump(), user["id"]))


@group_router.delete("/{group_id}", response_model=StandardResponse[dict[str, bool]])
async def delete_group(group_id: str, user: dict = Depends(require_authenticated_user)):
    group_service().delete_group(group_id, user["id"])
    return ok({"deleted": True})


@group_router.post("/{group_id}/members", response_model=StandardResponse[GroupResponse])
async def add_group_members(
    group_id: str,
    payload: GroupMemberAddCommand,
    user: dict = Depends(require_authenticated_user),
):
    return ok(group_service().add_members(group_id, payload.userIds, user["id"]))


@group_router.delete("/{group_id}/members", response_model=StandardResponse[GroupResponse])
async def remove_group_members(
    group_id: str,
    payload: GroupMemberRemoveCommand,
    user: dict = Depends(require_authenticated_user),
):
    return ok(group_service().remove_members(group_id, payload.userIds, user["id"]))


@group_router.delete(
    "/{group_id}/members/{user_id}",
    response_model=StandardResponse[GroupResponse],
)
async def remove_group_member(
    group_id: str,
    user_id: str,
    user: dict = Depends(require_authenticated_user),
):
    return ok(group_service().remove_member(group_id, user_id, user["id"]))
