from typing import Any

from src.features.membership.core.exceptions import ResourceNotFoundError
from src.features.membership.repositories.notification_repository import NotificationRepository
from src.features.membership.services.bootstrap_service import apply_membership_migration


class NotificationAdminService:
    def __init__(self, repository: NotificationRepository | None = None):
        apply_membership_migration()
        self.repository = repository or NotificationRepository()

    def admin_dashboard(self) -> dict[str, Any]:
        return self.repository.admin_dashboard()

    def list_audit_logs(
        self,
        *,
        page: int,
        page_size: int,
        action: str,
        resource_type: str,
        outcome: str,
        actions: list[str] | None = None,
    ) -> dict[str, Any]:
        return self.repository.list_audit_logs(
            page=page,
            page_size=page_size,
            action=action,
            actions=actions,
            resource_type=resource_type,
            outcome=outcome,
        )

    def get_audit_retention_setting(self) -> dict[str, Any]:
        return self.repository.get_audit_retention_setting()

    def update_audit_retention_setting(
        self,
        *,
        retention_days: int,
        updated_by_user_id: str,
    ) -> dict[str, Any]:
        return self.repository.update_audit_retention_setting(
            retention_days=retention_days,
            updated_by_user_id=updated_by_user_id,
        )

    def list_templates(self) -> list[dict[str, Any]]:
        return self.repository.list_templates()

    def upsert_template(self, payload: dict[str, Any]) -> dict[str, Any]:
        return self.repository.upsert_template(payload)

    def list_outbox(
        self,
        *,
        status: str,
        template_code: str,
        page: int,
        page_size: int,
    ) -> dict[str, Any]:
        return self.repository.list_outbox(
            status=status,
            template_code=template_code,
            page=page,
            page_size=page_size,
        )

    def dispatch_outbox(self, outbox_id: str, payload: dict[str, Any]) -> dict[str, Any]:
        # NOTE: 目前 dispatch 只更新 outbox 狀態為 SENT/FAILED，沒有真的呼叫 SMTP 或第三方寄信服務。
        # 後續若要完成寄信，應由 mail worker 讀取 outbox、送信後再回寫狀態。
        updated = self.repository.mark_outbox(
            outbox_id,
            status=payload.get("status", "SENT"),
            error_message=payload.get("errorMessage", ""),
        )
        if updated is None:
            raise ResourceNotFoundError("Notification outbox item not found.", {"id": outbox_id})
        return updated
