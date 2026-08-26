-- PostgreSQL: remove discontinued organization/position sorting and position code fields.

DROP INDEX IF EXISTS idx_membership_org_parent;

ALTER TABLE membership_organization_unit
    DROP COLUMN IF EXISTS sort_order;

CREATE INDEX IF NOT EXISTS idx_membership_org_parent
ON membership_organization_unit(parent_id)
WHERE deleted_at IS NULL;

ALTER TABLE membership_position
    DROP COLUMN IF EXISTS code,
    DROP COLUMN IF EXISTS sort_order;

INSERT INTO membership_schema_migrations (version, description)
VALUES ('V1.9', 'Remove organization and position legacy fields')
ON CONFLICT (version) DO UPDATE SET description = EXCLUDED.description;
