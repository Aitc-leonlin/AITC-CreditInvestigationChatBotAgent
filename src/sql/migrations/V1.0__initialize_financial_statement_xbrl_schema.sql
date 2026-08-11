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
-- - expert_knowledge_entry
-- - warehouse_data_entry
-- - company_profile
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
    taxonomy_id TEXT,

    role_uri TEXT,

    parent_concept_id TEXT,
    child_concept_id TEXT,

    order_no REAL,

    preferred_label TEXT,

    depth INTEGER,
    PRIMARY KEY (taxonomy_id, parent_concept_id, child_concept_id)
);




CREATE TABLE IF NOT EXISTS taxonomy_calculation (
    taxonomy_id TEXT,

    role_uri TEXT,

    parent_concept_id TEXT,
    child_concept_id TEXT,

    weight REAL,
    order_no REAL,
    PRIMARY KEY (taxonomy_id, parent_concept_id, child_concept_id)
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
    company_code TEXT,
    year INTEGER,
    quarter TEXT,

    report_scope TEXT,
    industry_type TEXT,

    field_id TEXT,

    concept_id TEXT,

    value REAL,

    report_id TEXT,
    fact_id TEXT,
    period_start TEXT,
    period_end TEXT,
    PRIMARY KEY (field_id, fact_id)
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

CREATE TABLE IF NOT EXISTS report_generator_dashboard (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    history_id INTEGER NOT NULL,
    summary_items_json TEXT NOT NULL,
    progress_items_json TEXT NOT NULL,
    progress_percent INTEGER NOT NULL,
    metrics_title TEXT NOT NULL,
    metrics_json TEXT NOT NULL,
    financial_trends_json TEXT NOT NULL DEFAULT '[]',
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL,

    FOREIGN KEY (history_id) REFERENCES report_generator_history(id) ON DELETE CASCADE
);

CREATE UNIQUE INDEX IF NOT EXISTS idx_report_generator_dashboard_history_id
    ON report_generator_dashboard(history_id);

CREATE TABLE IF NOT EXISTS expert_knowledge_entry (
    id TEXT PRIMARY KEY,

    title TEXT NOT NULL,
    data_source TEXT NOT NULL,
    industry TEXT NOT NULL,
    company_label TEXT NOT NULL,
    company_prompt_value TEXT NOT NULL DEFAULT '',
    source_schema_key TEXT NOT NULL,
    anchor_description TEXT NOT NULL,
    system_prompt TEXT NOT NULL,

    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    deleted_at TEXT
);

CREATE INDEX IF NOT EXISTS idx_expert_knowledge_entry_updated_at
    ON expert_knowledge_entry(updated_at DESC)
    WHERE deleted_at IS NULL;

CREATE INDEX IF NOT EXISTS idx_expert_knowledge_entry_created_at
    ON expert_knowledge_entry(created_at DESC)
    WHERE deleted_at IS NULL;

CREATE INDEX IF NOT EXISTS idx_expert_knowledge_entry_industry
    ON expert_knowledge_entry(industry)
    WHERE deleted_at IS NULL;

CREATE INDEX IF NOT EXISTS idx_expert_knowledge_entry_company_label
    ON expert_knowledge_entry(company_label)
    WHERE deleted_at IS NULL;

CREATE INDEX IF NOT EXISTS idx_expert_knowledge_entry_source_schema_key
    ON expert_knowledge_entry(source_schema_key)
    WHERE deleted_at IS NULL;

CREATE INDEX IF NOT EXISTS idx_expert_knowledge_entry_lookup
    ON expert_knowledge_entry(data_source, industry, company_label, company_prompt_value)
    WHERE deleted_at IS NULL;

CREATE TABLE IF NOT EXISTS warehouse_data_entry (
    id TEXT PRIMARY KEY,

    category TEXT NOT NULL,
    title TEXT NOT NULL,
    industry TEXT NOT NULL,
    company_label TEXT NOT NULL,
    company_prompt_value TEXT NOT NULL DEFAULT '',
    summary TEXT NOT NULL,
    source TEXT NOT NULL,
    url TEXT NOT NULL DEFAULT '',
    record_updated_at TEXT NOT NULL DEFAULT '',

    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    deleted_at TEXT
);

CREATE INDEX IF NOT EXISTS idx_warehouse_data_entry_updated_at
    ON warehouse_data_entry(updated_at DESC)
    WHERE deleted_at IS NULL;

CREATE INDEX IF NOT EXISTS idx_warehouse_data_entry_created_at
    ON warehouse_data_entry(created_at DESC)
    WHERE deleted_at IS NULL;

CREATE INDEX IF NOT EXISTS idx_warehouse_data_entry_category
    ON warehouse_data_entry(category)
    WHERE deleted_at IS NULL;

CREATE INDEX IF NOT EXISTS idx_warehouse_data_entry_industry
    ON warehouse_data_entry(industry)
    WHERE deleted_at IS NULL;

CREATE INDEX IF NOT EXISTS idx_warehouse_data_entry_company_label
    ON warehouse_data_entry(company_label)
    WHERE deleted_at IS NULL;

CREATE INDEX IF NOT EXISTS idx_warehouse_data_entry_lookup
    ON warehouse_data_entry(category, industry, company_label, company_prompt_value)
    WHERE deleted_at IS NULL;

CREATE TABLE IF NOT EXISTS company_profile (
    publication_date TEXT NOT NULL,
    company_code TEXT PRIMARY KEY,
    company_name TEXT NOT NULL,
    company_short_name TEXT NOT NULL,
    foreign_registration_country TEXT NOT NULL DEFAULT '',
    industry_code TEXT NOT NULL DEFAULT '',
    address TEXT NOT NULL DEFAULT '',
    tax_id TEXT NOT NULL DEFAULT '',
    chairman TEXT NOT NULL DEFAULT '',
    general_manager TEXT NOT NULL DEFAULT '',
    spokesperson TEXT NOT NULL DEFAULT '',
    spokesperson_title TEXT NOT NULL DEFAULT '',
    acting_spokesperson TEXT NOT NULL DEFAULT '',
    telephone TEXT NOT NULL DEFAULT '',
    incorporation_date TEXT NOT NULL DEFAULT '',
    listing_date TEXT NOT NULL DEFAULT '',
    par_value TEXT NOT NULL DEFAULT '',
    paid_in_capital TEXT NOT NULL DEFAULT '',
    private_placement_shares TEXT NOT NULL DEFAULT '',
    preferred_shares TEXT NOT NULL DEFAULT '',
    financial_statement_type TEXT NOT NULL DEFAULT '',
    stock_transfer_agent TEXT NOT NULL DEFAULT '',
    transfer_agent_phone TEXT NOT NULL DEFAULT '',
    transfer_agent_address TEXT NOT NULL DEFAULT '',
    cpa_firm TEXT NOT NULL DEFAULT '',
    cpa_1 TEXT NOT NULL DEFAULT '',
    cpa_2 TEXT NOT NULL DEFAULT '',
    english_short_name TEXT NOT NULL DEFAULT '',
    english_mailing_address TEXT NOT NULL DEFAULT '',
    fax TEXT NOT NULL DEFAULT '',
    email TEXT NOT NULL DEFAULT '',
    website TEXT NOT NULL DEFAULT '',
    issued_common_shares_or_tdr_shares TEXT NOT NULL DEFAULT '',
    source_json TEXT NOT NULL DEFAULT '',
    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
);

CREATE INDEX IF NOT EXISTS idx_company_profile_company_name
    ON company_profile(company_name);

CREATE INDEX IF NOT EXISTS idx_company_profile_tax_id
    ON company_profile(tax_id);

INSERT OR IGNORE INTO schema_migrations (version, description)
VALUES ('V1.0', 'Initialize FinancialStatementXBRL.db schema');

COMMIT;

PRAGMA foreign_keys = ON;
