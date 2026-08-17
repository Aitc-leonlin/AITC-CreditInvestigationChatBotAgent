-- SQLite: remove the discontinued data-scope, row/field permission, and masking features.

PRAGMA foreign_keys = ON;

BEGIN;

DROP TABLE IF EXISTS membership_sensitive_data_masking_rule;
DROP TABLE IF EXISTS membership_field_permission_rule;
DROP TABLE IF EXISTS membership_row_permission_rule;
DROP TABLE IF EXISTS membership_data_permission_policy;

INSERT OR REPLACE INTO membership_schema_migrations (version, description)
VALUES ('V1.6', 'Remove data scope and masking features');

COMMIT;
