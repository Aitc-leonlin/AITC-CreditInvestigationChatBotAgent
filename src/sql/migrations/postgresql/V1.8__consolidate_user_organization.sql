-- PostgreSQL: consolidate the legacy multi-department mapping into the user master record.

UPDATE membership_user AS user_record
SET organization_id = preferred_mapping.organization_id,
    updated_at = CURRENT_TIMESTAMP::TEXT
FROM (
    SELECT DISTINCT ON (mapping.user_id)
        mapping.user_id,
        mapping.organization_id
    FROM membership_user_department_mapping mapping
    WHERE mapping.deleted_at IS NULL
    ORDER BY
        mapping.user_id,
        mapping.is_primary DESC,
        mapping.updated_at DESC,
        mapping.created_at DESC
) AS preferred_mapping
WHERE user_record.id = preferred_mapping.user_id
  AND user_record.deleted_at IS NULL;

INSERT INTO membership_schema_migrations (version, description)
VALUES ('V1.8', 'Consolidate user organization into membership_user')
ON CONFLICT (version) DO UPDATE SET description = EXCLUDED.description;
