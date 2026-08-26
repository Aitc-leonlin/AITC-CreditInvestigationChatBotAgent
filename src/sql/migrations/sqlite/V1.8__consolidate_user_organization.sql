-- SQLite: consolidate the legacy multi-department mapping into the user master record.

PRAGMA foreign_keys = ON;

BEGIN;

UPDATE membership_user
SET organization_id = (
        SELECT mapping.organization_id
        FROM membership_user_department_mapping mapping
        WHERE mapping.user_id = membership_user.id
          AND mapping.deleted_at IS NULL
        ORDER BY mapping.is_primary DESC, mapping.updated_at DESC, mapping.created_at DESC
        LIMIT 1
    ),
    updated_at = CURRENT_TIMESTAMP
WHERE deleted_at IS NULL
  AND EXISTS (
      SELECT 1
      FROM membership_user_department_mapping mapping
      WHERE mapping.user_id = membership_user.id
        AND mapping.deleted_at IS NULL
  );

INSERT OR REPLACE INTO membership_schema_migrations (version, description)
VALUES ('V1.8', 'Consolidate user organization into membership_user');

COMMIT;
