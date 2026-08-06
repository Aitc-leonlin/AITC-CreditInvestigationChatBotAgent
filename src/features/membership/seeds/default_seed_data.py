from src.features.membership.core.time import utc_now_iso
from src.features.membership.core.password import PASSWORD_ALGORITHM, hash_password


ROOT_ORG_ID = "org-root"
SUPER_ADMIN_ROLE_ID = "role-super-admin"
DEFAULT_USER_ROLE_ID = "role-default-user"
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
                "id": DEFAULT_USER_ROLE_ID,
                "code": "DEFAULT_USER",
                "name": "預設USER",
                "description": "預設一般使用者角色，可使用授信 AI 助理與徵審報告產生器。",
                "role_type": "USER",
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
        "membership_notification_template": [
            notification_template("template-password-reset", "AUTH_PASSWORD_RESET", "EMAIL", "密碼重設通知", "請使用密碼重設連結完成密碼更新。", now),
            notification_template("template-email-verification", "AUTH_EMAIL_VERIFICATION", "EMAIL", "Email 驗證通知", "請使用驗證連結完成 Email 驗證。", now),
            notification_template("template-permission-changed", "RBAC_PERMISSION_CHANGED", "EMAIL", "權限異動通知", "您的角色或權限設定已異動。", now),
            notification_template("template-account-locked", "MEMBERSHIP_ACCOUNT_LOCKED", "EMAIL", "帳號鎖定通知", "您的帳號已被鎖定，請聯絡系統管理員。", now),
            notification_template("template-login-anomaly", "AUTH_LOGIN_ANOMALY", "EMAIL", "登入異常通知", "系統偵測到登入失敗或異常登入事件。", now),
        ],
        "membership_audit_retention_setting": [
            {
                "id": 1,
                "retention_days": 90,
                "last_checked_date": None,
                "last_run_at": None,
                "last_archive_at": None,
                "last_archived_count": 0,
                "last_cutoff_at": None,
                "last_archive_filename": "",
                "last_error": "",
                "updated_by_user_id": None,
                "created_at": now,
                "updated_at": now,
            }
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
