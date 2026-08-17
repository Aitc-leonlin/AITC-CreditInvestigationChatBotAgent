-- PostgreSQL general-purpose membership groups and members.

CREATE TABLE IF NOT EXISTS membership_group (
    id TEXT PRIMARY KEY,
    code TEXT NOT NULL,
    name TEXT NOT NULL,
    category TEXT NOT NULL DEFAULT 'GENERAL',
    description TEXT NOT NULL DEFAULT '',
    master_user_id TEXT REFERENCES membership_user(id) ON DELETE SET NULL,
    status TEXT NOT NULL DEFAULT 'ACTIVE',
    created_by_user_id TEXT REFERENCES membership_user(id) ON DELETE SET NULL,
    created_at TEXT NOT NULL DEFAULT (CURRENT_TIMESTAMP::TEXT),
    updated_at TEXT NOT NULL DEFAULT (CURRENT_TIMESTAMP::TEXT),
    deleted_at TEXT
);

CREATE UNIQUE INDEX IF NOT EXISTS idx_membership_group_code
ON membership_group(LOWER(code))
WHERE deleted_at IS NULL;

CREATE INDEX IF NOT EXISTS idx_membership_group_status_name
ON membership_group(status, name)
WHERE deleted_at IS NULL;

CREATE TABLE IF NOT EXISTS membership_group_member (
    id TEXT PRIMARY KEY,
    group_id TEXT NOT NULL REFERENCES membership_group(id) ON DELETE CASCADE,
    user_id TEXT NOT NULL REFERENCES membership_user(id) ON DELETE CASCADE,
    added_by_user_id TEXT REFERENCES membership_user(id) ON DELETE SET NULL,
    created_at TEXT NOT NULL DEFAULT (CURRENT_TIMESTAMP::TEXT),
    updated_at TEXT NOT NULL DEFAULT (CURRENT_TIMESTAMP::TEXT),
    deleted_at TEXT
);

CREATE UNIQUE INDEX IF NOT EXISTS idx_membership_group_member_active
ON membership_group_member(group_id, user_id)
WHERE deleted_at IS NULL;

CREATE INDEX IF NOT EXISTS idx_membership_group_member_user
ON membership_group_member(user_id, group_id)
WHERE deleted_at IS NULL;

INSERT INTO membership_schema_migrations (version, description)
VALUES ('V1.5', 'Add general-purpose membership groups and members')
ON CONFLICT (version) DO UPDATE SET description = EXCLUDED.description;
