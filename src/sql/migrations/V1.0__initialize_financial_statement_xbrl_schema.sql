-- FinancialStatementXBRL.db schema migration
-- Version: V1.0
-- Purpose: Initialize the current XBRL financial statement database schema.
--
-- This migration is based on the schema currently present in
-- FinancialStatementXBRL.db. It intentionally preserves the existing SQLite
-- column types and does not add foreign key constraints that are not present in
-- the current database.
--
-- Currently used by runtime code:
-- - report_instance
-- - taxonomy_concept
-- - field_dictionary
-- - financial_metric_value
-- - xbrl_fact
-- - report_generator_history
--
-- Currently used by import/build scripts and taxonomy data maintenance:
-- - taxonomy_entry_point
-- - taxonomy_presentation
-- - taxonomy_calculation
-- - field_concept_mapping

PRAGMA foreign_keys = OFF;

BEGIN;

CREATE TABLE IF NOT EXISTS schema_migrations (
    version TEXT PRIMARY KEY,
    description TEXT NOT NULL,
    applied_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS report_instance (
    report_id TEXT PRIMARY KEY,

    company_code TEXT,
    year INTEGER,
    quarter TEXT,

    industry_type TEXT,   -- CI / BASI / FH / INS / BD / MIM
    report_scope TEXT,    -- CR / SR

    taxonomy_version TEXT,
    module TEXT,          -- BSCI / SCF / ES / NOTES

    file_name TEXT,
    source_type TEXT,

    period_start DATE,
    period_end DATE
);

CREATE TABLE IF NOT EXISTS taxonomy_entry_point (
    taxonomy_id TEXT PRIMARY KEY,

    taxonomy_version TEXT,
    module TEXT,
    entry_point TEXT,

    xsd_file TEXT,
    presentation_file TEXT,
    label_file TEXT,
    calculation_file TEXT
);

CREATE TABLE IF NOT EXISTS taxonomy_concept (
    concept_id TEXT PRIMARY KEY,

    taxonomy_id TEXT,

    namespace TEXT,
    local_name TEXT,

    zh_label TEXT,
    en_label TEXT,

    terse_code TEXT,

    period_type TEXT,
    balance_type TEXT,

    data_type TEXT,

    is_abstract INTEGER
);

CREATE TABLE IF NOT EXISTS taxonomy_presentation (
    id INTEGER PRIMARY KEY AUTOINCREMENT,

    taxonomy_id TEXT,

    role_uri TEXT,

    parent_concept_id TEXT,
    child_concept_id TEXT,

    order_no REAL,

    preferred_label TEXT,

    depth INTEGER
);

CREATE TABLE IF NOT EXISTS taxonomy_calculation (
    id INTEGER PRIMARY KEY AUTOINCREMENT,

    taxonomy_id TEXT,

    role_uri TEXT,

    parent_concept_id TEXT,
    child_concept_id TEXT,

    weight REAL,
    order_no REAL
);

CREATE TABLE IF NOT EXISTS xbrl_fact (
    fact_id TEXT PRIMARY KEY,

    report_id TEXT,

    concept_id TEXT,

    context_id TEXT,
    unit_id TEXT,

    value_numeric REAL,
    value_text TEXT,

    decimals INTEGER,
    scale INTEGER,

    instant_date DATE,
    period_start DATE,
    period_end DATE,

    segment_json TEXT
);

CREATE TABLE IF NOT EXISTS field_dictionary (
    field_id TEXT PRIMARY KEY,

    canonical_name TEXT,

    zh_name TEXT,
    en_name TEXT,

    module TEXT,

    statement_type TEXT,

    value_type TEXT,

    description TEXT
);

CREATE TABLE IF NOT EXISTS field_concept_mapping (
    id INTEGER PRIMARY KEY AUTOINCREMENT,

    field_id TEXT,

    concept_id TEXT,

    taxonomy_id TEXT,

    industry_type TEXT,

    priority INTEGER,

    effective_from TEXT,
    effective_to TEXT
);

CREATE TABLE IF NOT EXISTS financial_metric_value (
    id INTEGER PRIMARY KEY AUTOINCREMENT,

    company_code TEXT,
    year INTEGER,
    quarter TEXT,

    report_scope TEXT,
    industry_type TEXT,

    field_id TEXT,

    concept_id TEXT,

    value REAL,

    report_id TEXT,
    fact_id TEXT
);

CREATE TABLE IF NOT EXISTS report_generator_history (
    id INTEGER PRIMARY KEY AUTOINCREMENT,

    title TEXT NOT NULL,
    company TEXT NOT NULL,
    company_code TEXT NOT NULL,
    company_label TEXT NOT NULL,
    year TEXT NOT NULL,
    period TEXT NOT NULL,
    report_type TEXT NOT NULL,
    generated_at TEXT NOT NULL,
    generated_at_display TEXT NOT NULL,
    generated_by TEXT NOT NULL,
    status TEXT NOT NULL,
    file_size TEXT NOT NULL,
    file_name TEXT NOT NULL,
    file_path TEXT NOT NULL,
    mime_type TEXT NOT NULL,
    created_at TEXT NOT NULL,

    public_id TEXT
);

CREATE UNIQUE INDEX IF NOT EXISTS idx_report_generator_history_public_id
    ON report_generator_history(public_id);

INSERT OR IGNORE INTO schema_migrations (version, description)
VALUES ('V1.0', 'Initialize FinancialStatementXBRL.db schema');

COMMIT;

PRAGMA foreign_keys = ON;
