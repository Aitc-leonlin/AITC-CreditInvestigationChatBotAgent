-- SQLite: remove discontinued organization/position sorting and position code fields.

PRAGMA foreign_keys = OFF;

BEGIN;

DROP INDEX IF EXISTS idx_membership_org_parent;

CREATE TABLE membership_organization_unit_v19 (
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
    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    deleted_at TEXT,
    FOREIGN KEY (parent_id) REFERENCES membership_organization_unit_v19(id),
    FOREIGN KEY (manager_user_id) REFERENCES membership_user(id)
);

INSERT INTO membership_organization_unit_v19 (
    id, code, name, parent_id, path, level, unit_type, company_id,
    manager_user_id, description, status, created_at, updated_at, deleted_at
)
SELECT
    id, code, name, parent_id, path, level, unit_type, company_id,
    manager_user_id, description, status, created_at, updated_at, deleted_at
FROM membership_organization_unit;

DROP TABLE membership_organization_unit;
ALTER TABLE membership_organization_unit_v19 RENAME TO membership_organization_unit;

CREATE INDEX idx_membership_org_parent
ON membership_organization_unit(parent_id)
WHERE deleted_at IS NULL;

CREATE TABLE membership_position_v19 (
    id TEXT PRIMARY KEY,
    name TEXT NOT NULL,
    description TEXT NOT NULL DEFAULT '',
    level INTEGER NOT NULL DEFAULT 0,
    status TEXT NOT NULL DEFAULT 'ACTIVE',
    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    deleted_at TEXT
);

INSERT INTO membership_position_v19 (
    id, name, description, level, status, created_at, updated_at, deleted_at
)
SELECT id, name, description, level, status, created_at, updated_at, deleted_at
FROM membership_position;

DROP TABLE membership_position;
ALTER TABLE membership_position_v19 RENAME TO membership_position;

INSERT OR REPLACE INTO membership_schema_migrations (version, description)
VALUES ('V1.9', 'Remove organization and position legacy fields');

COMMIT;

PRAGMA foreign_keys = ON;
