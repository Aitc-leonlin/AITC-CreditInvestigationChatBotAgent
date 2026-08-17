-- PostgreSQL: remove discontinued data-scope and masking features.

DROP TABLE IF EXISTS membership_sensitive_data_masking_rule CASCADE;
DROP TABLE IF EXISTS membership_field_permission_rule CASCADE;
DROP TABLE IF EXISTS membership_row_permission_rule CASCADE;
DROP TABLE IF EXISTS membership_data_permission_policy CASCADE;

INSERT INTO membership_schema_migrations (version, description)
VALUES ('V1.6', 'Remove data scope and masking features')
ON CONFLICT (version) DO UPDATE SET description = EXCLUDED.description;
