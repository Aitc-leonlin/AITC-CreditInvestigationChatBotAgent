from dataclasses import dataclass


@dataclass(frozen=True)
class PermissionGroupDefinition:
    id: str
    code: str
    name: str
    description: str
    moduleName: str
    status: str = "ACTIVE"
    createdAt: str = ""
    updatedAt: str = ""


@dataclass(frozen=True)
class PermissionDefinition:
    id: str
    code: str
    name: str
    description: str
    action: str
    groupId: str
    groupCode: str
    groupName: str
    status: str = "ACTIVE"
    createdAt: str = ""
    updatedAt: str = ""


PERMISSION_GROUPS: tuple[PermissionGroupDefinition, ...] = (
    PermissionGroupDefinition(
        id="group-membership",
        code="MEMBERSHIP",
        name="會員帳號管理",
        description="使用者、帳號與個人資料權限。",
        moduleName="會員權限管理",
    ),
    PermissionGroupDefinition(
        id="group-rbac",
        code="RBAC",
        name="會員角色管理",
        description="角色、權限、授權關聯管理。",
        moduleName="會員權限管理",
    ),
    PermissionGroupDefinition(
        id="group-org-scope",
        code="ORG_SCOPE",
        name="組織管理",
        description="組織、職位、部門對應與主管關係管理。",
        moduleName="會員權限管理",
    ),
    PermissionGroupDefinition(
        id="group-audit",
        code="AUDIT",
        name="稽核日誌",
        description="安全稽核與操作日誌。",
        moduleName="會員權限管理",
    ),
    PermissionGroupDefinition(
        id="group-notification",
        code="NOTIFICATION",
        name="通知管理",
        description="通知範本與發送佇列。",
        moduleName="會員權限管理",
    ),
    PermissionGroupDefinition(
        id="group-credit-ai",
        code="CREDIT_AI",
        name="授信AI助理",
        description="授信 AI 助理、專家知識庫與資料倉儲作業權限。",
        moduleName="授信 AI 助理",
    ),
    PermissionGroupDefinition(
        id="group-report-generator",
        code="REPORT_GENERATOR",
        name="徵審報告產生器",
        description="徵審報告產生與歷史報告查詢作業權限。",
        moduleName="徵審報告產生器",
    ),
)


def _permission(
    code: str,
    name: str,
    description: str,
    action: str,
    group_id: str,
    group_code: str,
    group_name: str,
) -> PermissionDefinition:
    return PermissionDefinition(
        id=code,
        code=code,
        name=name,
        description=description,
        action=action,
        groupId=group_id,
        groupCode=group_code,
        groupName=group_name,
    )


PERMISSIONS: tuple[PermissionDefinition, ...] = (
    _permission("membership.read", "讀取會員權限資料-檢視", "檢視會員帳號與管理總覽。", "VIEW", "group-membership", "MEMBERSHIP", "會員帳號管理"),
    _permission("membership.write", "維護會員權限資料", "新增、編輯與維護會員帳號。", "EDIT", "group-membership", "MEMBERSHIP", "會員帳號管理"),
    _permission("rbac.view", "角色權限-檢視", "檢視角色、權限、角色授權與使用者角色設定。", "VIEW", "group-rbac", "RBAC", "會員角色管理"),
    _permission("rbac.add", "角色權限-新增", "新增角色與 RBAC 設定。", "ADD", "group-rbac", "RBAC", "會員角色管理"),
    _permission("rbac.edit", "角色權限-編輯", "編輯角色、角色權限與使用者角色設定。", "EDIT", "group-rbac", "RBAC", "會員角色管理"),
    _permission("rbac.delete", "角色權限-刪除", "刪除角色與 RBAC 設定。", "DELETE", "group-rbac", "RBAC", "會員角色管理"),
    _permission("membership.user-roles", "批次套用角色", "允許使用 membership/user-roles 批次設定帳號角色。", "ALL", "group-rbac", "RBAC", "會員角色管理"),
    _permission("organization-scope.view", "組織管理-檢視", "檢視組織、職位、部門對應與主管關係。", "VIEW", "group-org-scope", "ORG_SCOPE", "組織管理"),
    _permission("organization-scope.add", "組織管理-新增", "新增組織、職位、部門對應與主管關係。", "ADD", "group-org-scope", "ORG_SCOPE", "組織管理"),
    _permission("organization-scope.edit", "組織管理-編輯", "編輯組織與職位。", "EDIT", "group-org-scope", "ORG_SCOPE", "組織管理"),
    _permission("organization-scope.delete", "組織管理-刪除", "刪除組織、職位、部門對應與主管關係。", "DELETE", "group-org-scope", "ORG_SCOPE", "組織管理"),
    _permission("audit.view", "稽核日誌-檢視", "檢視安全稽核與操作紀錄。", "VIEW", "group-audit", "AUDIT", "稽核日誌"),
    _permission("audit.manage", "稽核日誌-設定", "設定稽核日誌保留與自動封存天數。", "EDIT", "group-audit", "AUDIT", "稽核日誌"),
    _permission("notification.view", "通知管理-檢視", "檢視通知範本、通知 outbox 與發送狀態。", "VIEW", "group-notification", "NOTIFICATION", "通知管理"),
    _permission("credit-ai.chat", "授信 AI 助理", "允許使用授信 AI 助理進行授信風險問答。", "ALL", "group-credit-ai", "CREDIT_AI", "授信 AI 助理"),
    _permission("credit-ai.expert-knowledge.view", "專家知識庫-檢視", "檢視專家知識庫。", "VIEW", "group-credit-ai", "CREDIT_AI", "授信 AI 助理"),
    _permission("credit-ai.expert-knowledge.add", "專家知識庫-新增", "新增專家知識庫。", "ADD", "group-credit-ai", "CREDIT_AI", "授信 AI 助理"),
    _permission("credit-ai.expert-knowledge.edit", "專家知識庫-編輯", "編輯專家知識庫。", "EDIT", "group-credit-ai", "CREDIT_AI", "授信 AI 助理"),
    _permission("credit-ai.expert-knowledge.delete", "專家知識庫-刪除", "刪除專家知識庫。", "DELETE", "group-credit-ai", "CREDIT_AI", "授信 AI 助理"),
    _permission("credit-ai.warehouse-data.view", "資料倉儲-檢視", "檢視資料倉儲。", "VIEW", "group-credit-ai", "CREDIT_AI", "授信 AI 助理"),
    _permission("credit-ai.warehouse-data.add", "資料倉儲-新增", "新增資料倉儲。", "ADD", "group-credit-ai", "CREDIT_AI", "授信 AI 助理"),
    _permission("credit-ai.warehouse-data.edit", "資料倉儲-編輯", "編輯資料倉儲。", "EDIT", "group-credit-ai", "CREDIT_AI", "授信 AI 助理"),
    _permission("credit-ai.warehouse-data.delete", "資料倉儲-刪除", "刪除資料倉儲。", "DELETE", "group-credit-ai", "CREDIT_AI", "授信 AI 助理"),
    _permission("report-generator.create", "產生徵審報告", "允許使用徵審報告產生器。", "ALL", "group-report-generator", "REPORT_GENERATOR", "徵審報告產生器"),
    _permission("report-generator.history", "檢視歷史報告", "允許檢視徵審歷史報告。", "VIEW", "group-report-generator", "REPORT_GENERATOR", "徵審報告產生器"),
)


LEGACY_PERMISSION_ID_TO_CODE = {
    "perm-membership-read": "membership.read",
    "perm-membership-write": "membership.write",
    "perm-rbac-read": "rbac.view",
    "perm-rbac-manage": "rbac.edit",
    "perm-rbac-view": "rbac.view",
    "perm-rbac-add": "rbac.add",
    "perm-rbac-edit": "rbac.edit",
    "perm-rbac-delete": "rbac.delete",
    "perm-org-scope-manage": "organization-scope.edit",
    "perm-org-scope-view": "organization-scope.view",
    "perm-org-scope-add": "organization-scope.add",
    "perm-org-scope-edit": "organization-scope.edit",
    "perm-org-scope-delete": "organization-scope.delete",
    "perm-audit-read": "audit.view",
    "perm-notification-manage": "notification.view",
    "perm-credit-ai-chat": "credit-ai.chat",
    "perm-credit-ai-expert-knowledge": "credit-ai.expert-knowledge.view",
    "perm-credit-ai-expert-knowledge-view": "credit-ai.expert-knowledge.view",
    "perm-credit-ai-expert-knowledge-add": "credit-ai.expert-knowledge.add",
    "perm-credit-ai-expert-knowledge-edit": "credit-ai.expert-knowledge.edit",
    "perm-credit-ai-expert-knowledge-delete": "credit-ai.expert-knowledge.delete",
    "perm-credit-ai-warehouse-data": "credit-ai.warehouse-data.view",
    "perm-credit-ai-warehouse-data-view": "credit-ai.warehouse-data.view",
    "perm-credit-ai-warehouse-data-add": "credit-ai.warehouse-data.add",
    "perm-credit-ai-warehouse-data-edit": "credit-ai.warehouse-data.edit",
    "perm-credit-ai-warehouse-data-delete": "credit-ai.warehouse-data.delete",
    "perm-report-generator-create": "report-generator.create",
    "perm-report-generator-history": "report-generator.history",
}


PERMISSION_CODE_TO_LEGACY_ID = {
    "membership.read": "perm-membership-read",
    "membership.write": "perm-membership-write",
    "rbac.view": "perm-rbac-view",
    "rbac.add": "perm-rbac-add",
    "rbac.edit": "perm-rbac-edit",
    "rbac.delete": "perm-rbac-delete",
    "membership.user-roles": "perm-membership-user-roles",
    "organization-scope.view": "perm-org-scope-view",
    "organization-scope.add": "perm-org-scope-add",
    "organization-scope.edit": "perm-org-scope-edit",
    "organization-scope.delete": "perm-org-scope-delete",
    "audit.view": "perm-audit-read",
    "notification.view": "perm-notification-manage",
    "credit-ai.chat": "perm-credit-ai-chat",
    "credit-ai.expert-knowledge.view": "perm-credit-ai-expert-knowledge-view",
    "credit-ai.expert-knowledge.add": "perm-credit-ai-expert-knowledge-add",
    "credit-ai.expert-knowledge.edit": "perm-credit-ai-expert-knowledge-edit",
    "credit-ai.expert-knowledge.delete": "perm-credit-ai-expert-knowledge-delete",
    "credit-ai.warehouse-data.view": "perm-credit-ai-warehouse-data-view",
    "credit-ai.warehouse-data.add": "perm-credit-ai-warehouse-data-add",
    "credit-ai.warehouse-data.edit": "perm-credit-ai-warehouse-data-edit",
    "credit-ai.warehouse-data.delete": "perm-credit-ai-warehouse-data-delete",
    "report-generator.create": "perm-report-generator-create",
    "report-generator.history": "perm-report-generator-history",
}


def permission_group_rows() -> list[dict[str, object]]:
    permissions_by_group = {group.id: 0 for group in PERMISSION_GROUPS}
    for permission in PERMISSIONS:
        permissions_by_group[permission.groupId] = permissions_by_group.get(permission.groupId, 0) + 1
    return [
        {
            **group.__dict__,
            "permissionCount": permissions_by_group.get(group.id, 0),
        }
        for group in PERMISSION_GROUPS
    ]


def permission_rows(
    *,
    keyword: str = "",
    group_id: str = "",
    status_filter: str = "",
) -> list[dict[str, object]]:
    keyword = keyword.strip().lower()
    rows: list[dict[str, object]] = []
    for permission in PERMISSIONS:
        if group_id and permission.groupId != group_id:
            continue
        if status_filter and permission.status != status_filter:
            continue
        haystack = " ".join([permission.code, permission.name, permission.description]).lower()
        if keyword and keyword not in haystack:
            continue
        rows.append(permission.__dict__)
    return rows


def permission_codes() -> set[str]:
    return {permission.code for permission in PERMISSIONS}


def all_permission_codes() -> list[str]:
    return [permission.code for permission in PERMISSIONS]


def permission_exists(permission_code: str) -> bool:
    return permission_code in permission_codes()


def permission_by_code(permission_code: str) -> dict[str, object] | None:
    for permission in PERMISSIONS:
        if permission.code == permission_code:
            return permission.__dict__
    return None
