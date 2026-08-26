-- SQLite: keep organization codes unique only among active records.

PRAGMA foreign_keys = OFF;

BEGIN;

DROP INDEX IF EXISTS idx_membership_org_parent;
DROP INDEX IF EXISTS uq_membership_org_active_code;

CREATE TABLE membership_organization_unit_v110 (
    id TEXT PRIMARY KEY,
    code TEXT NOT NULL,
    name TEXT NOT NULL,
    parent_id TEXT,
    path TEXT NOT NULL,
    level INTEGER NOT NULL DEFAULT 0,
    unit_type TEXT NOT NULL DEFAULT 'DEPARTMENT',
    company_id TEXT,
    manager_user_id TEXT,
    description TEXT NOT NULL DEFAULT '',
    status TEXT NOT NULL DEFAULT 'ACTIVE',
    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    deleted_at TEXT,
    FOREIGN KEY (parent_id) REFERENCES membership_organization_unit_v110(id),
    FOREIGN KEY (manager_user_id) REFERENCES membership_user(id)
);

INSERT INTO membership_organization_unit_v110 (
    id, code, name, parent_id, path, level, unit_type, company_id,
    manager_user_id, description, status, created_at, updated_at, deleted_at
)
SELECT
    id, code, name, parent_id, path, level, unit_type, company_id,
    manager_user_id, description, status, created_at, updated_at, deleted_at
FROM membership_organization_unit;

DROP TABLE membership_organization_unit;
ALTER TABLE membership_organization_unit_v110 RENAME TO membership_organization_unit;

CREATE UNIQUE INDEX uq_membership_org_active_code
ON membership_organization_unit(code)
WHERE deleted_at IS NULL;

CREATE INDEX idx_membership_org_parent
ON membership_organization_unit(parent_id)
WHERE deleted_at IS NULL;

INSERT INTO membership_schema_migrations (version, description)
VALUES ('V1.10', 'Allow reuse of organization codes after soft deletion')
ON CONFLICT(version) DO UPDATE SET description = excluded.description;

COMMIT;

PRAGMA foreign_keys = ON;
