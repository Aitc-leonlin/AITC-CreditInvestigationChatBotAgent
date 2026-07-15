-- Enterprise Membership & Authorization Module
-- Version: V1.1
-- Purpose: Initialize the consolidated membership, authentication, RBAC,
-- menu authorization, organization data-permission, audit, and notification
-- schema baseline. This file folds the former V1.1 through V1.9 behavior into
-- a single V1.1 baseline, with V1.9 as the latest conflict-resolution target.

PRAGMA foreign_keys = ON;

BEGIN;

CREATE TABLE IF NOT EXISTS membership_schema_migrations (
    version TEXT PRIMARY KEY,
    description TEXT NOT NULL,
    applied_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS membership_organization_unit (
    id TEXT PRIMARY KEY,
    code TEXT NOT NULL UNIQUE,
    name TEXT NOT NULL,
    parent_id TEXT,
    path TEXT NOT NULL,
    level INTEGER NOT NULL DEFAULT 0,
    unit_type TEXT NOT NULL DEFAULT 'DEPARTMENT',
    company_id TEXT,
    manager_user_id TEXT,
    description TEXT NOT NULL DEFAULT '',
    status TEXT NOT NULL DEFAULT 'ACTIVE',
    sort_order INTEGER NOT NULL DEFAULT 0,
    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    deleted_at TEXT,

    FOREIGN KEY (parent_id) REFERENCES membership_organization_unit(id),
    FOREIGN KEY (manager_user_id) REFERENCES membership_user(id)
);

CREATE TABLE IF NOT EXISTS membership_user (
    id TEXT PRIMARY KEY,
    username TEXT NOT NULL UNIQUE,
    email TEXT NOT NULL UNIQUE,
    display_name TEXT NOT NULL,
    employee_no TEXT NOT NULL DEFAULT '',
    organization_id TEXT,
    status TEXT NOT NULL DEFAULT 'ACTIVE',
    locale TEXT NOT NULL DEFAULT 'zh-TW',
    timezone TEXT NOT NULL DEFAULT 'Asia/Taipei',
    email_verified_at TEXT,
    last_login_at TEXT,
    last_login_ip TEXT NOT NULL DEFAULT '',
    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    deleted_at TEXT,

    FOREIGN KEY (organization_id) REFERENCES membership_organization_unit(id)
);

CREATE TABLE IF NOT EXISTS membership_user_credential (
    id TEXT PRIMARY KEY,
    user_id TEXT NOT NULL UNIQUE,
    password_hash TEXT NOT NULL,
    password_algorithm TEXT NOT NULL DEFAULT 'argon2id',
    password_changed_at TEXT,
    must_change_password INTEGER NOT NULL DEFAULT 0,
    mfa_enabled INTEGER NOT NULL DEFAULT 0,
    failed_login_count INTEGER NOT NULL DEFAULT 0,
    last_failed_login_at TEXT,
    last_failed_login_ip TEXT NOT NULL DEFAULT '',
    locked_until TEXT,
    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    deleted_at TEXT,

    FOREIGN KEY (user_id) REFERENCES membership_user(id)
);

CREATE TABLE IF NOT EXISTS membership_role (
    id TEXT PRIMARY KEY,
    code TEXT NOT NULL UNIQUE,
    name TEXT NOT NULL,
    description TEXT NOT NULL DEFAULT '',
    role_type TEXT NOT NULL DEFAULT 'BUSINESS',
    status TEXT NOT NULL DEFAULT 'ACTIVE',
    is_system INTEGER NOT NULL DEFAULT 0,
    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    deleted_at TEXT
);

CREATE TABLE IF NOT EXISTS membership_permission_group (
    id TEXT PRIMARY KEY,
    code TEXT NOT NULL UNIQUE,
    name TEXT NOT NULL,
    description TEXT NOT NULL DEFAULT '',
    status TEXT NOT NULL DEFAULT 'ACTIVE',
    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    deleted_at TEXT
);

CREATE TABLE IF NOT EXISTS membership_permission (
    id TEXT PRIMARY KEY,
    code TEXT NOT NULL UNIQUE,
    name TEXT NOT NULL,
    description TEXT NOT NULL DEFAULT '',
    action TEXT NOT NULL,
    group_id TEXT,
    status TEXT NOT NULL DEFAULT 'ACTIVE',
    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    deleted_at TEXT,

    FOREIGN KEY (group_id) REFERENCES membership_permission_group(id)
);

CREATE TABLE IF NOT EXISTS membership_user_role (
    id TEXT PRIMARY KEY,
    user_id TEXT NOT NULL,
    role_id TEXT NOT NULL,
    organization_id TEXT,
    effective_from TEXT,
    effective_to TEXT,
    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    deleted_at TEXT,

    UNIQUE (user_id, role_id, organization_id),
    FOREIGN KEY (user_id) REFERENCES membership_user(id),
    FOREIGN KEY (role_id) REFERENCES membership_role(id),
    FOREIGN KEY (organization_id) REFERENCES membership_organization_unit(id)
);

CREATE TABLE IF NOT EXISTS membership_role_permission (
    id TEXT PRIMARY KEY,
    role_id TEXT NOT NULL,
    permission_id TEXT NOT NULL,
    effect TEXT NOT NULL DEFAULT 'ALLOW',
    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    deleted_at TEXT,

    UNIQUE (role_id, permission_id),
    FOREIGN KEY (role_id) REFERENCES membership_role(id),
    FOREIGN KEY (permission_id) REFERENCES membership_permission(id)
);

CREATE TABLE IF NOT EXISTS membership_menu_item (
    id TEXT PRIMARY KEY,
    code TEXT NOT NULL UNIQUE,
    title TEXT NOT NULL,
    parent_id TEXT,
    route_path TEXT NOT NULL DEFAULT '',
    component_key TEXT NOT NULL DEFAULT '',
    icon TEXT NOT NULL DEFAULT '',
    sort_order INTEGER NOT NULL DEFAULT 0,
    status TEXT NOT NULL DEFAULT 'ACTIVE',
    required_permission_code TEXT,
    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    deleted_at TEXT,

    FOREIGN KEY (parent_id) REFERENCES membership_menu_item(id)
);

CREATE TABLE IF NOT EXISTS membership_role_menu_permission (
    id TEXT PRIMARY KEY,
    role_id TEXT NOT NULL,
    menu_item_id TEXT NOT NULL,
    can_view INTEGER NOT NULL DEFAULT 1,
    can_create INTEGER NOT NULL DEFAULT 0,
    can_update INTEGER NOT NULL DEFAULT 0,
    can_delete INTEGER NOT NULL DEFAULT 0,
    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    deleted_at TEXT,

    UNIQUE (role_id, menu_item_id),
    FOREIGN KEY (role_id) REFERENCES membership_role(id),
    FOREIGN KEY (menu_item_id) REFERENCES membership_menu_item(id)
);

CREATE TABLE IF NOT EXISTS membership_data_scope (
    id TEXT PRIMARY KEY,
    role_id TEXT NOT NULL,
    scope_type TEXT NOT NULL,
    organization_id TEXT,
    rule_json TEXT NOT NULL DEFAULT '{}',
    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    deleted_at TEXT,

    FOREIGN KEY (role_id) REFERENCES membership_role(id),
    FOREIGN KEY (organization_id) REFERENCES membership_organization_unit(id)
);

CREATE TABLE IF NOT EXISTS membership_refresh_token (
    id TEXT PRIMARY KEY,
    user_id TEXT NOT NULL,
    token_hash TEXT NOT NULL UNIQUE,
    session_id TEXT,
    device_id TEXT NOT NULL DEFAULT '',
    ip_address TEXT NOT NULL DEFAULT '',
    user_agent TEXT NOT NULL DEFAULT '',
    expires_at TEXT NOT NULL,
    revoked_at TEXT,
    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    deleted_at TEXT,

    FOREIGN KEY (user_id) REFERENCES membership_user(id)
);

CREATE TABLE IF NOT EXISTS membership_session (
    id TEXT PRIMARY KEY,
    user_id TEXT NOT NULL,
    refresh_token_id TEXT,
    device_id TEXT NOT NULL DEFAULT '',
    ip_address TEXT NOT NULL DEFAULT '',
    user_agent TEXT NOT NULL DEFAULT '',
    remember_me INTEGER NOT NULL DEFAULT 0,
    started_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    last_seen_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    expires_at TEXT NOT NULL,
    revoked_at TEXT,
    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    deleted_at TEXT,

    FOREIGN KEY (user_id) REFERENCES membership_user(id),
    FOREIGN KEY (refresh_token_id) REFERENCES membership_refresh_token(id)
);

CREATE TABLE IF NOT EXISTS membership_password_reset_token (
    id TEXT PRIMARY KEY,
    user_id TEXT NOT NULL,
    token_hash TEXT NOT NULL UNIQUE,
    expires_at TEXT NOT NULL,
    used_at TEXT,
    requested_ip_address TEXT NOT NULL DEFAULT '',
    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    deleted_at TEXT,

    FOREIGN KEY (user_id) REFERENCES membership_user(id)
);

CREATE TABLE IF NOT EXISTS membership_email_verification_token (
    id TEXT PRIMARY KEY,
    user_id TEXT NOT NULL,
    token_hash TEXT NOT NULL UNIQUE,
    expires_at TEXT NOT NULL,
    verified_at TEXT,
    requested_ip_address TEXT NOT NULL DEFAULT '',
    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    deleted_at TEXT,

    FOREIGN KEY (user_id) REFERENCES membership_user(id)
);

CREATE TABLE IF NOT EXISTS membership_audit_log (
    id TEXT PRIMARY KEY,
    actor_user_id TEXT,
    action TEXT NOT NULL,
    resource_type TEXT NOT NULL,
    resource_id TEXT NOT NULL DEFAULT '',
    outcome TEXT NOT NULL DEFAULT 'SUCCESS',
    ip_address TEXT NOT NULL DEFAULT '',
    user_agent TEXT NOT NULL DEFAULT '',
    metadata_json TEXT NOT NULL DEFAULT '{}',
    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    deleted_at TEXT,

    FOREIGN KEY (actor_user_id) REFERENCES membership_user(id)
);

CREATE TABLE IF NOT EXISTS membership_notification_template (
    id TEXT PRIMARY KEY,
    code TEXT NOT NULL UNIQUE,
    channel TEXT NOT NULL,
    subject TEXT NOT NULL DEFAULT '',
    body TEXT NOT NULL,
    status TEXT NOT NULL DEFAULT 'ACTIVE',
    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    deleted_at TEXT
);

CREATE TABLE IF NOT EXISTS membership_notification_outbox (
    id TEXT PRIMARY KEY,
    template_code TEXT NOT NULL,
    recipient_user_id TEXT,
    channel TEXT NOT NULL,
    payload_json TEXT NOT NULL DEFAULT '{}',
    status TEXT NOT NULL DEFAULT 'PENDING',
    scheduled_at TEXT,
    sent_at TEXT,
    error_message TEXT NOT NULL DEFAULT '',
    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    deleted_at TEXT,

    FOREIGN KEY (recipient_user_id) REFERENCES membership_user(id)
);

CREATE TABLE IF NOT EXISTS membership_position (
    id TEXT PRIMARY KEY,
    code TEXT NOT NULL UNIQUE,
    name TEXT NOT NULL,
    description TEXT NOT NULL DEFAULT '',
    level INTEGER NOT NULL DEFAULT 0,
    status TEXT NOT NULL DEFAULT 'ACTIVE',
    sort_order INTEGER NOT NULL DEFAULT 0,
    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    deleted_at TEXT
);

CREATE TABLE IF NOT EXISTS membership_user_department_mapping (
    id TEXT PRIMARY KEY,
    user_id TEXT NOT NULL,
    organization_id TEXT NOT NULL,
    position_id TEXT,
    is_primary INTEGER NOT NULL DEFAULT 0,
    effective_from TEXT,
    effective_to TEXT,
    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    deleted_at TEXT,

    UNIQUE (user_id, organization_id, position_id),
    FOREIGN KEY (user_id) REFERENCES membership_user(id),
    FOREIGN KEY (organization_id) REFERENCES membership_organization_unit(id),
    FOREIGN KEY (position_id) REFERENCES membership_position(id)
);

CREATE TABLE IF NOT EXISTS membership_user_manager_relation (
    id TEXT PRIMARY KEY,
    manager_user_id TEXT NOT NULL,
    employee_user_id TEXT NOT NULL,
    organization_id TEXT,
    relation_type TEXT NOT NULL DEFAULT 'DIRECT',
    status TEXT NOT NULL DEFAULT 'ACTIVE',
    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    deleted_at TEXT,

    UNIQUE (manager_user_id, employee_user_id, organization_id),
    FOREIGN KEY (manager_user_id) REFERENCES membership_user(id),
    FOREIGN KEY (employee_user_id) REFERENCES membership_user(id),
    FOREIGN KEY (organization_id) REFERENCES membership_organization_unit(id)
);

CREATE TABLE IF NOT EXISTS membership_data_permission_policy (
    id TEXT PRIMARY KEY,
    subject_type TEXT NOT NULL DEFAULT 'ROLE',
    subject_id TEXT NOT NULL,
    resource_code TEXT NOT NULL,
    data_scope TEXT NOT NULL DEFAULT 'ONLY_MYSELF',
    custom_scope_json TEXT NOT NULL DEFAULT '[]',
    row_rule_json TEXT NOT NULL DEFAULT '{}',
    field_rule_json TEXT NOT NULL DEFAULT '{}',
    masking_rule_json TEXT NOT NULL DEFAULT '{}',
    status TEXT NOT NULL DEFAULT 'ACTIVE',
    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    deleted_at TEXT,

    UNIQUE (subject_type, subject_id, resource_code)
);

CREATE TABLE IF NOT EXISTS membership_row_permission_rule (
    id TEXT PRIMARY KEY,
    policy_id TEXT NOT NULL,
    resource_code TEXT NOT NULL,
    rule_name TEXT NOT NULL,
    expression_json TEXT NOT NULL DEFAULT '{}',
    effect TEXT NOT NULL DEFAULT 'ALLOW',
    status TEXT NOT NULL DEFAULT 'ACTIVE',
    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    deleted_at TEXT,

    FOREIGN KEY (policy_id) REFERENCES membership_data_permission_policy(id)
);

CREATE TABLE IF NOT EXISTS membership_field_permission_rule (
    id TEXT PRIMARY KEY,
    policy_id TEXT NOT NULL,
    resource_code TEXT NOT NULL,
    field_name TEXT NOT NULL,
    can_read INTEGER NOT NULL DEFAULT 1,
    can_write INTEGER NOT NULL DEFAULT 0,
    status TEXT NOT NULL DEFAULT 'ACTIVE',
    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    deleted_at TEXT,

    UNIQUE (policy_id, resource_code, field_name),
    FOREIGN KEY (policy_id) REFERENCES membership_data_permission_policy(id)
);

CREATE TABLE IF NOT EXISTS membership_sensitive_data_masking_rule (
    id TEXT PRIMARY KEY,
    policy_id TEXT NOT NULL,
    resource_code TEXT NOT NULL,
    field_name TEXT NOT NULL,
    masking_type TEXT NOT NULL DEFAULT 'PARTIAL',
    masking_pattern TEXT NOT NULL DEFAULT '',
    status TEXT NOT NULL DEFAULT 'ACTIVE',
    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    deleted_at TEXT,

    UNIQUE (policy_id, resource_code, field_name),
    FOREIGN KEY (policy_id) REFERENCES membership_data_permission_policy(id)
);

CREATE INDEX IF NOT EXISTS idx_membership_user_organization
ON membership_user(organization_id)
WHERE deleted_at IS NULL;

CREATE INDEX IF NOT EXISTS idx_membership_org_parent
ON membership_organization_unit(parent_id, sort_order)
WHERE deleted_at IS NULL;

CREATE INDEX IF NOT EXISTS idx_membership_user_role_user
ON membership_user_role(user_id)
WHERE deleted_at IS NULL;

CREATE INDEX IF NOT EXISTS idx_membership_user_role_role
ON membership_user_role(role_id)
WHERE deleted_at IS NULL;

CREATE INDEX IF NOT EXISTS idx_membership_role_permission_role
ON membership_role_permission(role_id)
WHERE deleted_at IS NULL;

CREATE INDEX IF NOT EXISTS idx_membership_role_permission_permission
ON membership_role_permission(permission_id)
WHERE deleted_at IS NULL;

CREATE INDEX IF NOT EXISTS idx_membership_permission_group
ON membership_permission(group_id)
WHERE deleted_at IS NULL;

CREATE INDEX IF NOT EXISTS idx_membership_menu_parent
ON membership_menu_item(parent_id, sort_order)
WHERE deleted_at IS NULL;

CREATE INDEX IF NOT EXISTS idx_membership_session_user
ON membership_session(user_id, last_seen_at DESC)
WHERE deleted_at IS NULL;

CREATE INDEX IF NOT EXISTS idx_membership_session_refresh
ON membership_session(refresh_token_id)
WHERE deleted_at IS NULL;

CREATE INDEX IF NOT EXISTS idx_membership_password_reset_user
ON membership_password_reset_token(user_id, created_at DESC)
WHERE deleted_at IS NULL;

CREATE INDEX IF NOT EXISTS idx_membership_email_verification_user
ON membership_email_verification_token(user_id, created_at DESC)
WHERE deleted_at IS NULL;

CREATE INDEX IF NOT EXISTS idx_membership_audit_resource
ON membership_audit_log(resource_type, resource_id, created_at DESC)
WHERE deleted_at IS NULL;

CREATE INDEX IF NOT EXISTS idx_membership_outbox_status
ON membership_notification_outbox(status, scheduled_at, created_at)
WHERE deleted_at IS NULL;

CREATE INDEX IF NOT EXISTS idx_membership_user_department_user
ON membership_user_department_mapping(user_id)
WHERE deleted_at IS NULL;

CREATE INDEX IF NOT EXISTS idx_membership_user_manager_employee
ON membership_user_manager_relation(employee_user_id)
WHERE deleted_at IS NULL;

CREATE INDEX IF NOT EXISTS idx_membership_data_policy_subject
ON membership_data_permission_policy(subject_type, subject_id, resource_code)
WHERE deleted_at IS NULL;

INSERT OR REPLACE INTO membership_schema_migrations (version, description)
VALUES ('V1.1', 'Initialize consolidated enterprise membership and authorization schema through former V1.9');

COMMIT;
