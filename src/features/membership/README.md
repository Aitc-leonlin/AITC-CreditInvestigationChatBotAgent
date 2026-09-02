# Enterprise Membership & Authorization Module

This module provides enterprise membership, authorization, organization data scope, notification, and admin dashboard APIs.

## Scope

- Folder structure for api routers, services, repositories, models, schemas, validation, core utilities, and seed data.
- SQLite and PostgreSQL migrations for users, credentials, organizations, roles, permissions, menus, refresh tokens, audit logs, and notification outbox.
- SQLAlchemy-backed connections with lightweight dataclass entities and repository row mapping.
- Base repository and service classes.
- Standard API response envelope and membership error handling.
- Pydantic validation structure.
- Idempotent seed data for root organization, system administrator, roles, permissions, menu items, notification templates, and super-admin grants.

## Phase 8 Admin APIs

```http
GET /api/membership/admin/dashboard
GET /api/membership/admin/audit-logs
GET /api/membership/admin/notification-templates
POST /api/membership/admin/notification-templates
GET /api/membership/admin/notification-outbox
POST /api/membership/admin/notification-outbox/{outbox_id}/dispatch
```

Implemented notification events:

- `AUTH_PASSWORD_RESET`
- `AUTH_EMAIL_VERIFICATION`
- `RBAC_PERMISSION_CHANGED`
- `MEMBERSHIP_ACCOUNT_LOCKED`
- `AUTH_LOGIN_ANOMALY`

Notification delivery currently uses the database outbox pattern. The dispatch endpoint marks an outbox item as `SENT` or `FAILED`; an SMTP worker can later consume the same table without changing the API contract.

## Bootstrap

Migration、功能資料表檢查與預設資料建立會在後端啟動時統一執行。一般 API request
不會再觸發 Migration 或 Schema 檢查；若啟動階段失敗，後端會停止啟動。

## Metadata

Inspect module readiness through:

```http
GET /api/membership/system/metadata
```

## Deployment Settings

Recommended environment variables:

```env
MEMBERSHIP_ACCESS_TOKEN_TTL_SECONDS=900
MEMBERSHIP_REFRESH_TOKEN_TTL_SECONDS=86400
MEMBERSHIP_REMEMBER_ME_REFRESH_TOKEN_TTL_SECONDS=2592000
MEMBERSHIP_PASSWORD_RESET_TTL_SECONDS=1800
MEMBERSHIP_EMAIL_VERIFICATION_TTL_SECONDS=86400
MEMBERSHIP_MAX_FAILED_LOGIN_COUNT=5
MEMBERSHIP_LOGIN_LOCK_MINUTES=15
CORS_ALLOW_ORIGINS=http://localhost:3000
```

## Smoke Test

```bash
env PYTHONPYCACHEPREFIX=/tmp/aitc-backend-pycache venv/bin/python scripts/phase8_smoke_test.py
```

The script writes `output/phase8_test_results.json`.
