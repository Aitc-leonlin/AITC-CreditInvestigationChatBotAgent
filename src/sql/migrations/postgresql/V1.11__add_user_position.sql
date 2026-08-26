-- PostgreSQL: assign one organization-managed position to each membership user.

ALTER TABLE membership_user
ADD COLUMN IF NOT EXISTS position_id TEXT;

DO $$
BEGIN
    IF NOT EXISTS (
        SELECT 1
        FROM pg_constraint
        WHERE conname = 'fk_membership_user_position'
          AND conrelid = 'membership_user'::regclass
    ) THEN
        ALTER TABLE membership_user
        ADD CONSTRAINT fk_membership_user_position
        FOREIGN KEY (position_id) REFERENCES membership_position(id);
    END IF;
END $$;

CREATE INDEX IF NOT EXISTS idx_membership_user_position
ON membership_user(position_id)
WHERE deleted_at IS NULL;

INSERT INTO membership_schema_migrations (version, description)
VALUES ('V1.11', 'Add organization-managed position to membership user')
ON CONFLICT (version) DO UPDATE SET description = EXCLUDED.description;
