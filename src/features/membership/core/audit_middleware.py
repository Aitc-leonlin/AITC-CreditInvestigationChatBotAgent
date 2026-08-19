"""HTTP audit middleware for business and membership mutation endpoints."""

from dataclasses import dataclass
import re
from typing import Pattern

from fastapi import Request

from src.features.membership.core.jwt import decode_jwt
from src.features.membership.services.audit_service import AuditService


@dataclass(frozen=True)
class AuditRoute:
    method: str
    pattern: Pattern[str]
    action: str
    resource_type: str
    module_label: str
    action_label: str
    start_action: str | None = None


def route(method: str, pattern: str, action: str, resource_type: str, module: str, label: str, *, start: str | None = None) -> AuditRoute:
    return AuditRoute(method, re.compile(pattern), action, resource_type, module, label, start)


AUDIT_ROUTES = [
    route("POST", r"^/api/chatbot$", "ai.conversation.create", "ai_conversation", "AI助理", "建立AI對話"),
    route("POST", r"^/api/chatbot-with-external$", "ai.external_search", "ai_conversation", "AI助理", "外部網路搜尋"),
    route("POST", r"^/api/expert-knowledge/generate-(?:anchor|analysis)$", "expert_knowledge.ai_generate", "expert_knowledge", "專家知識庫", "AI產生"),
    route("POST", r"^/api/expert-knowledge$", "expert_knowledge.create", "expert_knowledge", "專家知識庫", "新增"),
    route("(?:PUT|PATCH)", r"^/api/expert-knowledge/(?P<id>[^/]+)$", "expert_knowledge.update", "expert_knowledge", "專家知識庫", "編輯"),
    route("DELETE", r"^/api/expert-knowledge/(?P<id>[^/]+)$", "expert_knowledge.delete", "expert_knowledge", "專家知識庫", "刪除"),
    route("POST", r"^/api/warehouse-data$", "warehouse_data.create", "warehouse_data", "資料倉儲", "新增"),
    route("(?:PUT|PATCH)", r"^/api/warehouse-data/(?P<id>[^/]+)$", "warehouse_data.update", "warehouse_data", "資料倉儲", "編輯"),
    route("DELETE", r"^/api/warehouse-data/(?P<id>[^/]+)$", "warehouse_data.delete", "warehouse_data", "資料倉儲", "刪除"),
    route("POST", r"^/api/report-generator/generate$", "report.generate.completed", "credit_report", "報告產生器", "完成/失敗", start="report.generate.started"),
    # TODO: 歷史報告下載功能尚未完成，待雲端物件儲存串接後恢復稽核路由。
    # route("GET", r"^/api/report-generator/history/(?P<id>[^/]+)/download$", "report.history.download", "credit_report", "歷史報告", "下載報告"),
    route("POST", r"^/api/membership/users$", "membership.user.create", "membership_user", "會員管理", "使用者新增"),
    route("PUT", r"^/api/membership/users/(?P<id>[^/]+)$", "membership.user.update", "membership_user", "會員管理", "使用者編輯"),
    route("DELETE", r"^/api/membership/users/(?P<id>[^/]+)$", "membership.user.delete", "membership_user", "會員管理", "使用者刪除"),
    route("(?:PATCH|POST)", r"^/api/membership/users/(?P<id>[^/]+)/(?:status|activate|deactivate|lock|unlock)$", "membership.user.status", "membership_user", "會員管理", "啟用/停用/鎖定/解鎖"),
    route("PUT", r"^/api/membership/users/(?P<id>[^/]+)/reset-password$", "membership.user.password.reset", "membership_user", "會員管理", "重設密碼"),
    route("POST", r"^/api/membership/rbac/roles$", "membership.role.create", "membership_role", "會員管理", "角色新增"),
    route("PUT", r"^/api/membership/rbac/roles/(?P<id>[^/]+)$", "membership.role.update", "membership_role", "會員管理", "角色編輯"),
    route("DELETE", r"^/api/membership/rbac/roles/(?P<id>[^/]+)$", "membership.role.delete", "membership_role", "會員管理", "角色刪除"),
    route("PUT", r"^/api/membership/rbac/roles/(?P<id>[^/]+)/permissions$", "membership.role.permissions.update", "membership_role", "會員管理", "角色權限修改"),
    route("PUT", r"^/api/membership/rbac/users/(?P<id>[^/]+)/roles$", "membership.user_roles.batch_assign", "membership_user", "會員管理", "批次指派角色"),
    route("(?:POST|PUT|DELETE)", r"^/api/membership/organizations/(?P<section>units|positions|user-departments|manager-relations)(?:/(?P<id>[^/]+))?$", "membership.organization_scope.change", "organization", "會員管理", "組織管理"),
    route("POST", r"^/api/membership/admin/notification-templates$", "membership.notification_template.update", "notification_template", "會員管理", "通知範本修改"),
    route("PUT", r"^/api/membership/admin/audit-retention$", "membership.audit_retention.update", "audit_retention", "會員管理", "Audit Log 保留天數修改"),
]


def _actor_user_id(request: Request) -> str | None:
    authorization = request.headers.get("authorization", "")
    scheme, _, token = authorization.partition(" ")
    if scheme.lower() != "bearer" or not token:
        return None
    try:
        return str(decode_jwt(token).get("sub") or "") or None
    except Exception:
        return None


def _ip_address(request: Request) -> str:
    forwarded_for = request.headers.get("x-forwarded-for", "")
    if forwarded_for:
        return forwarded_for.split(",", 1)[0].strip()
    return request.client.host if request.client else ""


def _matched_route(method: str, path: str) -> tuple[AuditRoute, re.Match[str]] | None:
    for audit_route in AUDIT_ROUTES:
        if re.fullmatch(audit_route.method, method) and (match := audit_route.pattern.fullmatch(path)):
            return audit_route, match
    return None


async def _safe_request_summary(request: Request) -> tuple[str, dict[str, object]]:
    if request.method.upper() not in {"POST", "PUT", "PATCH"}:
        return "", {}
    try:
        payload = await request.json()
    except Exception:
        return "", {}
    if not isinstance(payload, dict):
        return "", {}

    target = next(
        (
            str(payload[key]).strip()
            for key in ("id", "code", "publicId", "userId", "subjectId", "conversationId", "companyCode", "username", "title", "name")
            if payload.get(key) is not None and str(payload[key]).strip()
        ),
        "",
    )
    summary: dict[str, object] = {}
    for key in ("organizationId", "subjectType", "resourceCode", "status", "companyCode", "year", "conversationId", "retentionDays"):
        value = payload.get(key)
        if isinstance(value, (str, int, float, bool)) and str(value).strip():
            summary[key] = value
    for key in ("roleIds", "ids"):
        value = payload.get(key)
        if isinstance(value, list):
            summary[f"{key}Count"] = len(value)
    return target, summary


async def audit_http_middleware(request: Request, call_next):
    matched = _matched_route(request.method.upper(), request.url.path)
    if matched is None:
        return await call_next(request)

    audit_route, match = matched
    actor_user_id = _actor_user_id(request)
    groups = match.groupdict()
    body_target, body_summary = await _safe_request_summary(request)
    resource_id = groups.get("id") or body_target or groups.get("section") or ""
    common = {
        "actor_user_id": actor_user_id,
        "resource_type": audit_route.resource_type,
        "resource_id": resource_id,
        "ip_address": _ip_address(request),
        "user_agent": request.headers.get("user-agent", ""),
    }
    metadata = {
        "module": audit_route.module_label,
        "actionLabel": audit_route.action_label,
        "method": request.method.upper(),
        "path": request.url.path,
        **body_summary,
    }
    audit_service = AuditService()
    if audit_route.start_action:
        audit_service.record(action=audit_route.start_action, metadata={**metadata, "actionLabel": "開始產生報告"}, **common)

    try:
        response = await call_next(request)
    except Exception as exc:
        audit_service.record(
            action=audit_route.action,
            outcome="FAILURE",
            metadata={**metadata, "errorType": type(exc).__name__},
            **common,
        )
        raise

    audit_service.record(
        action=audit_route.action,
        outcome="SUCCESS" if response.status_code < 400 else "FAILURE",
        metadata={**metadata, "statusCode": response.status_code},
        **common,
    )
    if (
        audit_route.resource_type == "expert_knowledge"
        and request.headers.get("x-audit-source", "").lower() == "ai-generated"
        and response.status_code < 400
        and request.method.upper() in {"POST", "PUT", "PATCH"}
    ):
        audit_service.record(
            action="expert_knowledge.ai_generate_and_store",
            metadata={**metadata, "actionLabel": "AI產生並存入DB"},
            **common,
        )
    return response
