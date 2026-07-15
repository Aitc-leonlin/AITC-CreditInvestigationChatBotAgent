# Enterprise Membership & Authorization Module

This module provides enterprise membership, authorization, organization data scope, notification, and admin dashboard APIs.

## Scope

- Folder structure for api routers, services, repositories, models, schemas, validation, core utilities, and seed data.
- SQLite migration for users, credentials, organizations, roles, permissions, menus, data scopes, refresh tokens, audit logs, and notification outbox.
- Lightweight ORM-style dataclass entities with repository row mapping.
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

Run the migration and seed data through:

```http
POST /api/membership/system/bootstrap
```

The endpoint is idempotent and returns inserted row counts for each seeded table.

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
