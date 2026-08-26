-- SQLite: assign one organization-managed position to each membership user.

ALTER TABLE membership_user
ADD COLUMN position_id TEXT REFERENCES membership_position(id);

CREATE INDEX IF NOT EXISTS idx_membership_user_position
ON membership_user(position_id)
WHERE deleted_at IS NULL;

INSERT INTO membership_schema_migrations (version, description)
VALUES ('V1.11', 'Add organization-managed position to membership user')
ON CONFLICT(version) DO UPDATE SET description = excluded.description;
