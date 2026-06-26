# Database Migrations

This folder documents SQL migrations for project-maintained SQLite schemas.

## Naming

Use this format:

```text
migrations/V{major}.{minor}__{description}.sql
```

Example:

```text
migrations/V1.0__initialize_financial_statement_xbrl_schema.sql
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
| `report_generator_history` | 3 |
| `report_instance` | 283 |
| `taxonomy_calculation` | 5145 |
| `taxonomy_concept` | 10351 |
| `taxonomy_entry_point` | 7 |
| `taxonomy_presentation` | 7099 |
| `xbrl_fact` | 532662 |

## Notes

- The V1.0 SQL preserves the current SQLite schema and column types.
- It does not add foreign keys because the current database does not define them.
- It includes a `schema_migrations` table for future migration tracking.
- The report generator currently stores history in `FinancialStatementXBRL.db`, while report source data is read from `FinancialStatements.db` unless `REPORT_GENERATOR_DB_PATH` is set.
