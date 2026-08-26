-- PostgreSQL audit-log retention settings.

CREATE TABLE IF NOT EXISTS membership_audit_retention_setting (
    id INTEGER PRIMARY KEY CHECK (id = 1),
    retention_days INTEGER NOT NULL DEFAULT 90 CHECK (retention_days BETWEEN 1 AND 3650),
    last_checked_date TEXT,
    last_run_at TEXT,
    last_archive_at TEXT,
    last_archived_count INTEGER NOT NULL DEFAULT 0,
    last_cutoff_at TEXT,
    last_archive_filename TEXT NOT NULL DEFAULT '',
    last_error TEXT NOT NULL DEFAULT '',
    updated_by_user_id TEXT REFERENCES membership_user(id),
    created_at TEXT NOT NULL DEFAULT (CURRENT_TIMESTAMP::TEXT),
    updated_at TEXT NOT NULL DEFAULT (CURRENT_TIMESTAMP::TEXT)
);

INSERT INTO membership_audit_retention_setting (id, retention_days)
VALUES (1, 90)
ON CONFLICT (id) DO NOTHING;

INSERT INTO membership_schema_migrations (version, description)
VALUES ('V1.2', 'Add daily audit log TXT archive retention settings')
ON CONFLICT (version) DO UPDATE SET description = EXCLUDED.description;
