"""Membership 後台管理、稽核與通知 API。

提供管理 dashboard、audit log 查詢、通知模板維護、notification outbox 查詢與 dispatch
狀態更新。dispatch 目前只標記 outbox 狀態，實際寄信 worker 尚未串接。
"""

from fastapi import Depends, Query

from src.features.membership.api.base import create_membership_router
from src.features.membership.core.auth_middleware import require_permission
from src.features.membership.core.responses import ok
from src.features.membership.schemas.common import StandardResponse
from src.features.membership.schemas.notification import (
    AdminDashboardResponse,
    AuditRetentionResponse,
    AuditRetentionUpdateCommand,
    AuditLogListResponse,
    NotificationDispatchCommand,
    NotificationOutboxResponse,
    NotificationTemplateCommand,
    NotificationTemplateResponse,
)
from src.features.membership.services.bootstrap_service import reset_membership_seed_data
from src.features.membership.services.notification_service import NotificationAdminService


membership_admin_router = create_membership_router(
    prefix="/api/membership/admin",
    tags=["membership-admin"],
)


def notification_admin_service() -> NotificationAdminService:
    return NotificationAdminService()


@membership_admin_router.get(
    "/dashboard",
    response_model=StandardResponse[AdminDashboardResponse],
)
async def get_admin_dashboard(_: dict = Depends(require_permission("membership.read"))):
    return ok(notification_admin_service().admin_dashboard())


@membership_admin_router.post(
    "/reset-seed",
    response_model=StandardResponse[dict],
)
async def reset_membership_seed(_: dict = Depends(require_permission("rbac.delete"))):
    return ok(reset_membership_seed_data())


@membership_admin_router.get(
    "/audit-logs",
    response_model=StandardResponse[AuditLogListResponse],
)
async def list_audit_logs(
    page: int = Query(default=1, ge=1),
    pageSize: int = Query(default=50, ge=1, le=200),
    action: str = Query(default=""),
    actions: list[str] = Query(default=[]),
    resourceType: str = Query(default=""),
    outcome: str = Query(default=""),
    _: dict = Depends(require_permission("audit.view")),
):
    return ok(
        notification_admin_service().list_audit_logs(
            page=page,
            page_size=pageSize,
            action=action,
            actions=actions,
            resource_type=resourceType,
            outcome=outcome,
        )
    )


@membership_admin_router.get(
    "/audit-retention",
    response_model=StandardResponse[AuditRetentionResponse],
)
async def get_audit_retention(_: dict = Depends(require_permission("audit.view"))):
    return ok(notification_admin_service().get_audit_retention_setting())


@membership_admin_router.put(
    "/audit-retention",
    response_model=StandardResponse[AuditRetentionResponse],
)
async def update_audit_retention(
    payload: AuditRetentionUpdateCommand,
    user: dict = Depends(require_permission("audit.manage")),
):
    return ok(
        notification_admin_service().update_audit_retention_setting(
            retention_days=payload.retentionDays,
            updated_by_user_id=user["id"],
        )
    )


@membership_admin_router.get(
    "/notification-templates",
    response_model=StandardResponse[list[NotificationTemplateResponse]],
)
async def list_notification_templates(_: dict = Depends(require_permission("notification.view"))):
    return ok(notification_admin_service().list_templates())


@membership_admin_router.post(
    "/notification-templates",
    response_model=StandardResponse[NotificationTemplateResponse],
)
async def upsert_notification_template(
    payload: NotificationTemplateCommand,
    _: dict = Depends(require_permission("notification.view")),
):
    return ok(notification_admin_service().upsert_template(payload.model_dump()))


@membership_admin_router.get(
    "/notification-outbox",
    response_model=StandardResponse[dict],
)
async def list_notification_outbox(
    page: int = Query(default=1, ge=1),
    pageSize: int = Query(default=50, ge=1, le=200),
    status: str = Query(default=""),
    templateCode: str = Query(default=""),
    _: dict = Depends(require_permission("notification.view")),
):
    return ok(
        notification_admin_service().list_outbox(
            status=status,
            template_code=templateCode,
            page=page,
            page_size=pageSize,
        )
    )


@membership_admin_router.post(
    "/notification-outbox/{outbox_id}/dispatch",
    response_model=StandardResponse[NotificationOutboxResponse],
)
async def dispatch_notification_outbox(
    outbox_id: str,
    payload: NotificationDispatchCommand,
    _: dict = Depends(require_permission("notification.view")),
):
    return ok(notification_admin_service().dispatch_outbox(outbox_id, payload.model_dump()))
