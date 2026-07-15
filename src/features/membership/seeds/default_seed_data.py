from src.features.membership.core.time import utc_now_iso
from src.features.membership.core.password import PASSWORD_ALGORITHM, hash_password


ROOT_ORG_ID = "org-root"
SUPER_ADMIN_ROLE_ID = "role-super-admin"
SYSTEM_ADMIN_USER_ID = "user-system-admin"


def default_seed_data() -> dict[str, list[dict[str, object]]]:
    now = utc_now_iso()
    return {
        "membership_organization_unit": [
            {
                "id": ROOT_ORG_ID,
                "code": "ROOT",
                "name": "企業總部",
                "parent_id": None,
                "path": "/ROOT",
                "level": 0,
                "status": "ACTIVE",
                "sort_order": 0,
                "created_at": now,
                "updated_at": now,
                "deleted_at": None,
            }
        ],
        "membership_user": [
            {
                "id": SYSTEM_ADMIN_USER_ID,
                "username": "system.admin",
                "email": "system.admin@example.local",
                "display_name": "System Administrator",
                "employee_no": "SYS-0001",
                "organization_id": ROOT_ORG_ID,
                "status": "ACTIVE",
                "locale": "zh-TW",
                "timezone": "Asia/Taipei",
                "last_login_at": None,
                "created_at": now,
                "updated_at": now,
                "deleted_at": None,
            }
        ],
        "membership_user_credential": [
            {
                "id": "credential-system-admin",
                "user_id": SYSTEM_ADMIN_USER_ID,
                "password_hash": hash_password("Admin123!"),
                "password_algorithm": PASSWORD_ALGORITHM,
                "password_changed_at": now,
                "must_change_password": 1,
                "mfa_enabled": 0,
                "failed_login_count": 0,
                "locked_until": None,
                "created_at": now,
                "updated_at": now,
                "deleted_at": None,
            }
        ],
        "membership_role": [
            {
                "id": SUPER_ADMIN_ROLE_ID,
                "code": "SUPER_ADMIN",
                "name": "系統超級管理員",
                "description": "擁有會員與權限模組全部管理權限。",
                "role_type": "SYSTEM",
                "status": "ACTIVE",
                "is_system": 1,
                "created_at": now,
                "updated_at": now,
                "deleted_at": None,
            },
            {
                "id": "role-membership-admin",
                "code": "MEMBERSHIP_ADMIN",
                "name": "會員權限管理員",
                "description": "管理使用者、角色、權限與組織授權設定。",
                "role_type": "SYSTEM",
                "status": "ACTIVE",
                "is_system": 1,
                "created_at": now,
                "updated_at": now,
                "deleted_at": None,
            },
            {
                "id": "role-auditor",
                "code": "AUDITOR",
                "name": "稽核人員",
                "description": "檢視權限設定、日誌與安全事件。",
                "role_type": "BUSINESS",
                "status": "ACTIVE",
                "is_system": 1,
                "created_at": now,
                "updated_at": now,
                "deleted_at": None,
            },
        ],
        "membership_permission_group": [
            permission_group("perm-group-membership", "MEMBERSHIP", "會員管理", "使用者、帳號與個人資料權限。", now),
            permission_group("perm-group-rbac", "RBAC", "角色權限", "角色、權限、授權關聯管理。", now),
            permission_group("perm-group-menu", "MENU", "選單權限", "選單與功能入口授權。", now),
            permission_group("perm-group-org-scope", "ORG_SCOPE", "組織資料權限", "組織與資料可視範圍。", now),
            permission_group("perm-group-audit", "AUDIT", "稽核日誌", "安全稽核與操作日誌。", now),
            permission_group("perm-group-notification", "NOTIFICATION", "通知管理", "通知範本與發送佇列。", now),
            permission_group("perm-group-credit-ai", "CREDIT_AI", "授信 AI 助理", "授信 AI 助理、專家知識庫與資料倉儲作業權限。", now),
            permission_group("perm-group-report-generator", "REPORT_GENERATOR", "徵審報告產生器", "徵審報告產生與歷史報告查詢作業權限。", now),
        ],
        "membership_permission": [
            permission("perm-membership-read", "membership.read", "讀取會員權限資料", "VIEW", "perm-group-membership", now),
            permission("perm-membership-write", "membership.write", "維護會員權限資料", "write", "perm-group-membership", now),
            permission("perm-rbac-view", "rbac.view", "角色權限", "VIEW", "perm-group-rbac", now),
            permission("perm-rbac-add", "rbac.add", "角色權限", "ADD", "perm-group-rbac", now),
            permission("perm-rbac-edit", "rbac.edit", "角色權限", "EDIT", "perm-group-rbac", now),
            permission("perm-rbac-delete", "rbac.delete", "角色權限", "DELETE", "perm-group-rbac", now),
            permission("perm-menu-read", "menu.read", "讀取選單設定", "VIEW", "perm-group-menu", now),
            permission("perm-menu-manage", "menu.manage", "管理選單權限", "manage", "perm-group-menu", now),
            permission("perm-org-scope-view", "organization-scope.view", "組織資料權限", "VIEW", "perm-group-org-scope", now),
            permission("perm-org-scope-add", "organization-scope.add", "組織資料權限", "ADD", "perm-group-org-scope", now),
            permission("perm-org-scope-edit", "organization-scope.edit", "組織資料權限", "EDIT", "perm-group-org-scope", now),
            permission("perm-org-scope-delete", "organization-scope.delete", "組織資料權限", "DELETE", "perm-group-org-scope", now),
            permission("perm-audit-read", "audit.read", "讀取安全與操作日誌", "VIEW", "perm-group-audit", now),
            permission("perm-notification-manage", "notification.manage", "管理通知範本與發送佇列", "manage", "perm-group-notification", now),
            permission("perm-credit-ai-chat", "credit-ai.chat", "使用授信 AI 助理", "ALL", "perm-group-credit-ai", now),
            permission("perm-credit-ai-expert-knowledge-view", "credit-ai.expert-knowledge.view", "專家知識庫", "VIEW", "perm-group-credit-ai", now),
            permission("perm-credit-ai-expert-knowledge-add", "credit-ai.expert-knowledge.add", "專家知識庫", "ADD", "perm-group-credit-ai", now),
            permission("perm-credit-ai-expert-knowledge-edit", "credit-ai.expert-knowledge.edit", "專家知識庫", "EDIT", "perm-group-credit-ai", now),
            permission("perm-credit-ai-expert-knowledge-delete", "credit-ai.expert-knowledge.delete", "專家知識庫", "DELETE", "perm-group-credit-ai", now),
            permission("perm-credit-ai-warehouse-data-view", "credit-ai.warehouse-data.view", "資料倉儲", "VIEW", "perm-group-credit-ai", now),
            permission("perm-credit-ai-warehouse-data-add", "credit-ai.warehouse-data.add", "資料倉儲", "ADD", "perm-group-credit-ai", now),
            permission("perm-credit-ai-warehouse-data-edit", "credit-ai.warehouse-data.edit", "資料倉儲", "EDIT", "perm-group-credit-ai", now),
            permission("perm-credit-ai-warehouse-data-delete", "credit-ai.warehouse-data.delete", "資料倉儲", "DELETE", "perm-group-credit-ai", now),
            permission("perm-report-generator-create", "report-generator.create", "產生徵審報告", "ALL", "perm-group-report-generator", now),
            permission("perm-report-generator-history", "report-generator.history", "檢視歷史報告", "ALL", "perm-group-report-generator", now),
        ],
        "membership_menu_item": [
            menu("menu-membership", "MEMBERSHIP", "會員權限管理", None, "/membership", "MembershipLayout", "Security", 10, None, now),
            menu("menu-membership-dashboard", "MEMBERSHIP_DASHBOARD", "管理總覽", "menu-membership", "/membership/dashboard", "MembershipDashboardPage", "LayoutDashboard", 10, "membership.read", now),
            menu("menu-users", "MEMBERSHIP_USERS", "會員帳號", "menu-membership", "/membership/users", "MembershipUsersPage", "Users", 20, "membership.read", now),
            menu("menu-roles", "MEMBERSHIP_ROLES", "角色管理", "menu-membership", "/membership/roles", "MembershipRolesPage", "KeyRound", 30, "rbac.view", now),
            menu("menu-permissions", "MEMBERSHIP_PERMISSIONS", "權限管理", "menu-membership", "/membership/permissions", "MembershipPermissionsPage", "ShieldCheck", 40, "rbac.view", now),
            menu("menu-user-roles", "MEMBERSHIP_USER_ROLES", "使用者角色", "menu-membership", "/membership/user-roles", "MembershipUserRolesPage", "UserCog", 50, "rbac.view", now),
            menu("menu-menu-management", "MEMBERSHIP_MENUS", "選單管理", "menu-membership", "/membership/menus", "MembershipMenusPage", "PanelLeft", 60, "menu.read", now),
            menu("menu-organizations", "MEMBERSHIP_ORGS", "組織資料權限", "menu-membership", "/membership/organizations", "MembershipOrganizationsPage", "Building2", 70, "organization-scope.view", now),
            menu("menu-audit", "MEMBERSHIP_AUDIT", "日誌安全", "menu-membership", "/membership/audit", "MembershipAuditPage", "FileSearch", 80, "audit.read", now),
            menu("menu-notifications", "MEMBERSHIP_NOTIFICATIONS", "通知管理", "menu-membership", "/membership/notifications", "MembershipNotificationsPage", "FileSearch", 90, "notification.manage", now),
        ],
        "membership_notification_template": [
            notification_template("template-password-reset", "AUTH_PASSWORD_RESET", "EMAIL", "密碼重設通知", "請使用密碼重設連結完成密碼更新。", now),
            notification_template("template-email-verification", "AUTH_EMAIL_VERIFICATION", "EMAIL", "Email 驗證通知", "請使用驗證連結完成 Email 驗證。", now),
            notification_template("template-permission-changed", "RBAC_PERMISSION_CHANGED", "EMAIL", "權限異動通知", "您的角色或權限設定已異動。", now),
            notification_template("template-account-locked", "MEMBERSHIP_ACCOUNT_LOCKED", "EMAIL", "帳號鎖定通知", "您的帳號已被鎖定，請聯絡系統管理員。", now),
            notification_template("template-login-anomaly", "AUTH_LOGIN_ANOMALY", "EMAIL", "登入異常通知", "系統偵測到登入失敗或異常登入事件。", now),
        ],
        "membership_user_role": [
            {
                "id": "user-role-system-admin-super-admin",
                "user_id": SYSTEM_ADMIN_USER_ID,
                "role_id": SUPER_ADMIN_ROLE_ID,
                "organization_id": ROOT_ORG_ID,
                "effective_from": now,
                "effective_to": None,
                "created_at": now,
                "updated_at": now,
                "deleted_at": None,
            }
        ],
    }


def permission(
    entity_id: str,
    code: str,
    name: str,
    action: str,
    group_id: str,
    now: str,
) -> dict[str, object]:
    return {
        "id": entity_id,
        "code": code,
        "name": name,
        "description": name,
        "action": action,
        "group_id": group_id,
        "status": "ACTIVE",
        "created_at": now,
        "updated_at": now,
        "deleted_at": None,
    }


def permission_group(
    entity_id: str,
    code: str,
    name: str,
    description: str,
    now: str,
) -> dict[str, object]:
    return {
        "id": entity_id,
        "code": code,
        "name": name,
        "description": description,
        "status": "ACTIVE",
        "created_at": now,
        "updated_at": now,
        "deleted_at": None,
    }


def menu(
    entity_id: str,
    code: str,
    title: str,
    parent_id: str | None,
    route_path: str,
    component_key: str,
    icon: str,
    sort_order: int,
    required_permission_code: str | None,
    now: str,
) -> dict[str, object]:
    return {
        "id": entity_id,
        "code": code,
        "title": title,
        "parent_id": parent_id,
        "route_path": route_path,
        "component_key": component_key,
        "icon": icon,
        "sort_order": sort_order,
        "status": "ACTIVE",
        "required_permission_code": required_permission_code,
        "created_at": now,
        "updated_at": now,
        "deleted_at": None,
    }


def notification_template(
    entity_id: str,
    code: str,
    channel: str,
    subject: str,
    body: str,
    now: str,
) -> dict[str, object]:
    return {
        "id": entity_id,
        "code": code,
        "channel": channel,
        "subject": subject,
        "body": body,
        "status": "ACTIVE",
        "created_at": now,
        "updated_at": now,
        "deleted_at": None,
    }
