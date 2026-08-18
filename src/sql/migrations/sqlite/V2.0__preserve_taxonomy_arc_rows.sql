-- SQLite: preserve taxonomy arcs as independent rows.

PRAGMA foreign_keys = OFF;

BEGIN;

CREATE TABLE taxonomy_presentation_v2 (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    taxonomy_id TEXT,
    role_uri TEXT,
    parent_concept_id TEXT,
    child_concept_id TEXT,
    order_no REAL,
    preferred_label TEXT,
    depth INTEGER
);

INSERT INTO taxonomy_presentation_v2 (
    taxonomy_id, role_uri, parent_concept_id, child_concept_id,
    order_no, preferred_label, depth
)
SELECT
    taxonomy_id, role_uri, parent_concept_id, child_concept_id,
    order_no, preferred_label, depth
FROM taxonomy_presentation;

DROP TABLE taxonomy_presentation;
ALTER TABLE taxonomy_presentation_v2 RENAME TO taxonomy_presentation;

CREATE TABLE taxonomy_calculation_v2 (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    taxonomy_id TEXT,
    role_uri TEXT,
    parent_concept_id TEXT,
    child_concept_id TEXT,
    weight REAL,
    order_no REAL
);

INSERT INTO taxonomy_calculation_v2 (
    taxonomy_id, role_uri, parent_concept_id, child_concept_id, weight, order_no
)
SELECT
    taxonomy_id, role_uri, parent_concept_id, child_concept_id, weight, order_no
FROM taxonomy_calculation;

DROP TABLE taxonomy_calculation;
ALTER TABLE taxonomy_calculation_v2 RENAME TO taxonomy_calculation;

INSERT OR REPLACE INTO schema_migrations (version, description)
VALUES ('V2.0', 'Preserve taxonomy presentation and calculation arc rows by identity');

COMMIT;

PRAGMA foreign_keys = ON;
