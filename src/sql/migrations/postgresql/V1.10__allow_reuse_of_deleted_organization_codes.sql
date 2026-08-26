-- PostgreSQL: keep organization codes unique only among active records.

DO $$
DECLARE
    unique_constraint_name TEXT;
BEGIN
    FOR unique_constraint_name IN
        SELECT constraint_record.conname
        FROM pg_constraint constraint_record
        JOIN pg_class table_record ON table_record.oid = constraint_record.conrelid
        JOIN pg_namespace schema_record ON schema_record.oid = table_record.relnamespace
        WHERE schema_record.nspname = current_schema()
          AND table_record.relname = 'membership_organization_unit'
          AND constraint_record.contype = 'u'
          AND (
              SELECT ARRAY_AGG(attribute_record.attname ORDER BY key_record.ordinality)
              FROM UNNEST(constraint_record.conkey) WITH ORDINALITY AS key_record(attnum, ordinality)
              JOIN pg_attribute attribute_record
                ON attribute_record.attrelid = table_record.oid
               AND attribute_record.attnum = key_record.attnum
          ) = ARRAY['code']::NAME[]
    LOOP
        EXECUTE FORMAT(
            'ALTER TABLE membership_organization_unit DROP CONSTRAINT %I',
            unique_constraint_name
        );
    END LOOP;
END $$;

CREATE UNIQUE INDEX IF NOT EXISTS uq_membership_org_active_code
ON membership_organization_unit(code)
WHERE deleted_at IS NULL;

INSERT INTO membership_schema_migrations (version, description)
VALUES ('V1.10', 'Allow reuse of organization codes after soft deletion')
ON CONFLICT (version) DO UPDATE SET description = EXCLUDED.description;
