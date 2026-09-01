# Database Migrations

This folder contains dialect-specific SQL migrations for the SQLite and
PostgreSQL schemas. Runtime database access is handled through SQLAlchemy 2.x.

## Naming

Use this format:

```text
migrations/V{major}.{minor}__{description}.sql
```

Example:

```text
migrations/sqlite/V1.0__initialize_financial_statement_xbrl_schema.sql
```

## Current Schema

`V1.0` initializes the current `FinancialStatementXBRL.db` schema.

Runtime query code currently uses:

- `report_instance`
- `taxonomy_concept`
- `field_dictionary`
- `financial_metric_value`
- `xbrl_fact`
- `report_generator_history`
- `expert_knowledge_entry`
- `warehouse_data_entry`
- `company_profile`

XBRL import/build scripts and taxonomy maintenance currently use:

- `taxonomy_entry_point`
- `taxonomy_presentation`
- `taxonomy_calculation`
- `field_concept_mapping`

## Current Row Counts

These counts were observed when `V1.0` was created:

| Table | Rows |
| --- | ---: |
| `field_concept_mapping` | 26321 |
| `field_dictionary` | 1207 |
| `financial_metric_value` | 532662 |
| `company_profile` | 1089 |
| `report_generator_history` | 3 |
| `report_instance` | 283 |
| `taxonomy_calculation` | 5145 |
| `taxonomy_concept` | 10351 |
| `taxonomy_entry_point` | 7 |
| `taxonomy_presentation` | 7099 |
| `xbrl_fact` | 532662 |

## Notes

- The V1.0 SQL is the single project-maintained schema baseline.
- Expert knowledge, warehouse data, and listed company profile schema changes are folded into V1.0.
- It does not add foreign keys because the current database does not define them.
- It includes a `schema_migrations` table for future migration tracking.
- The report generator currently stores history in `FinancialStatementXBRL.db`, while report source data is read from `FinancialStatements.db` unless `REPORT_GENERATOR_DB_PATH` is set.

## Database-specific migrations

Migration files are separated by database engine:

```text
migrations/
├── sqlite/
│   ├── V1.0__initialize_financial_statement_xbrl_schema.sql
│   └── V1.1__... through V1.7__...
└── postgresql/
    ├── V1.0__initialize_financial_statement_xbrl_schema.sql
    └── V1.1__... through V1.7__...
```

`DATABASE_MODE=sqlite` selects `migrations/sqlite`; `DATABASE_MODE=postgresql`
selects `migrations/postgresql`. Backend startup automatically applies the
XBRL/report migrations V1.0 and V2.0 followed by membership migrations V1.1 through V1.11,
then inserts missing default membership seed records.

The shared XBRL builder entry point also follows `DATABASE_MODE`:

```bash
venv/bin/python scripts/build_xbrl_sql.py --help
```

- `sqlite`: uses SQLite `INSERT OR REPLACE`, `--db-path`, and SQLite loading.
- `postgresql`: delegates to `build_xbrl_sql_postgresql.py`, uses PostgreSQL
  `ON CONFLICT`, and accepts `--load-db` to load through the PostgreSQL ENV
  connection.
