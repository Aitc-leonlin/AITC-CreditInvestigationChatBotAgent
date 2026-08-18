#!/usr/bin/env python3
"""Generate PostgreSQL-compatible SQL from TIFRS taxonomy and XBRL instances."""

import argparse
import math
import sys
from datetime import date, datetime
from decimal import Decimal
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

from dotenv import load_dotenv


PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from scripts import build_xbrl_sql as base
from src.shared.database.config import get_database_settings
from src.shared.database.connection import open_database_connection


load_dotenv(PROJECT_ROOT / ".env")

CONFLICT_KEYS: dict[str, tuple[str, ...]] = {
    "taxonomy_entry_point": ("taxonomy_id",),
    "taxonomy_concept": ("concept_id",),
    "taxonomy_presentation": ("id",),
    "taxonomy_calculation": ("id",),
    "report_instance": ("report_id",),
    "xbrl_fact": ("fact_id",),
    "field_dictionary": ("field_id",),
    "financial_metric_value": ("field_id", "fact_id"),
}

FIELD_CONCEPT_MAPPING_IDENTITY = (
    "field_id",
    "concept_id",
    "taxonomy_id",
    "industry_type",
    "effective_from",
    "effective_to",
)

TAXONOMY_PRESENTATION_COLUMNS = (
    "id",
    "taxonomy_id",
    "role_uri",
    "parent_concept_id",
    "child_concept_id",
    "order_no",
    "preferred_label",
    "depth",
)

TAXONOMY_CALCULATION_COLUMNS = (
    "id",
    "taxonomy_id",
    "role_uri",
    "parent_concept_id",
    "child_concept_id",
    "weight",
    "order_no",
)


def sql_literal(value: Any) -> str:
    if value is None:
        return "NULL"
    if isinstance(value, bool):
        return "1" if value else "0"
    if isinstance(value, Decimal):
        return format(value, "f")
    if isinstance(value, float):
        if math.isnan(value):
            return "'NaN'"
        if math.isinf(value):
            return "'Infinity'" if value > 0 else "'-Infinity'"
        return repr(value)
    if isinstance(value, int):
        return str(value)
    if isinstance(value, (date, datetime)):
        return f"'{value.isoformat()}'"
    text = str(value)
    if "\x00" in text:
        raise ValueError("PostgreSQL TEXT values cannot contain NUL bytes.")
    return "'" + text.replace("'", "''") + "'"


def insert_sql(table: str, row: Dict[str, Any]) -> str:
    columns = list(row.keys())
    column_sql = ", ".join(columns)
    values_sql = ", ".join(sql_literal(row[column]) for column in columns)

    if table == "field_concept_mapping":
        predicates = " AND ".join(
            f"{column} IS NOT DISTINCT FROM {sql_literal(row.get(column))}"
            for column in FIELD_CONCEPT_MAPPING_IDENTITY
        )
        return (
            f"INSERT INTO {table} ({column_sql}) "
            f"SELECT {values_sql} "
            f"WHERE NOT EXISTS (SELECT 1 FROM {table} WHERE {predicates});"
        )

    conflict_keys = CONFLICT_KEYS.get(table)
    if not conflict_keys:
        return f"INSERT INTO {table} ({column_sql}) VALUES ({values_sql});"

    update_columns = [column for column in columns if column not in conflict_keys]
    conflict_sql = ", ".join(conflict_keys)
    if not update_columns:
        return (
            f"INSERT INTO {table} ({column_sql}) VALUES ({values_sql}) "
            f"ON CONFLICT ({conflict_sql}) DO NOTHING;"
        )
    assignments = ", ".join(
        f"{column} = EXCLUDED.{column}" for column in update_columns
    )
    return (
        f"INSERT INTO {table} ({column_sql}) VALUES ({values_sql}) "
        f"ON CONFLICT ({conflict_sql}) DO UPDATE SET {assignments};"
    )


def split_pipe_list(value: Optional[str]) -> set[str]:
    if not value:
        return set()
    return {item for item in value.split("|") if item}


def load_taxonomy_from_postgresql() -> base.TaxonomyParseResult:
    connection = open_database_connection()
    try:
        entry_points: dict[str, Dict[str, Any]] = {}
        versions: set[str] = set()
        for row in connection.execute("SELECT * FROM taxonomy_entry_point").fetchall():
            if row["taxonomy_version"]:
                versions.add(row["taxonomy_version"])
            entry_points[row["taxonomy_id"]] = {
                "taxonomy_id": row["taxonomy_id"],
                "taxonomy_version": row["taxonomy_version"],
                "module": row["module"],
                "entry_points": split_pipe_list(row["entry_point"]),
                "xsd_files": split_pipe_list(row["xsd_file"]),
                "presentation_files": split_pipe_list(row["presentation_file"]),
                "label_files": split_pipe_list(row["label_file"]),
                "calculation_files": split_pipe_list(row["calculation_file"]),
            }

        concepts: dict[str, base.ConceptRecord] = {}
        concept_lookup: dict[Tuple[Optional[str], str], str] = {}
        for row in connection.execute("SELECT * FROM taxonomy_concept").fetchall():
            concept = base.ConceptRecord(
                concept_id=row["concept_id"],
                taxonomy_id=row["taxonomy_id"],
                namespace=row["namespace"],
                local_name=row["local_name"],
                zh_label=row["zh_label"],
                en_label=row["en_label"],
                terse_code=row["terse_code"],
                period_type=row["period_type"],
                balance_type=row["balance_type"],
                data_type=row["data_type"],
                is_abstract=row["is_abstract"],
            )
            concepts[concept.concept_id] = concept
            concept_lookup[(concept.namespace, concept.local_name)] = concept.concept_id

        presentation_rows = [
            dict(row)
            for row in connection.execute("SELECT * FROM taxonomy_presentation").fetchall()
        ]
        calculation_rows = [
            dict(row)
            for row in connection.execute("SELECT * FROM taxonomy_calculation").fetchall()
        ]
        for row in presentation_rows:
            child_concept_id = row.get("child_concept_id")
            if child_concept_id in concepts and row.get("role_uri"):
                concepts[child_concept_id].roles.add(row["role_uri"])

        return base.TaxonomyParseResult(
            version=next(iter(sorted(versions)), None),
            entry_points=entry_points,
            concepts=concepts,
            concept_lookup=concept_lookup,
            presentation_rows=presentation_rows,
            calculation_rows=calculation_rows,
        )
    finally:
        connection.close()


def render_sql(
    taxonomy: base.TaxonomyParseResult,
    report_row: Optional[Dict[str, Any]],
    facts: List[Dict[str, Any]],
    field_rows: List[Dict[str, Any]],
    concept_mapping_rows: List[Dict[str, Any]],
    metric_rows: List[Dict[str, Any]],
    *,
    include_taxonomy: bool = True,
) -> str:
    lines = ["BEGIN;"]

    if include_taxonomy:
        for entry in sorted(
            taxonomy.entry_points.values(), key=lambda item: item["taxonomy_id"]
        ):
            lines.append(
                insert_sql(
                    "taxonomy_entry_point",
                    {
                        "taxonomy_id": entry["taxonomy_id"],
                        "taxonomy_version": entry["taxonomy_version"],
                        "module": entry["module"],
                        "entry_point": "|".join(sorted(entry["entry_points"])) or None,
                        "xsd_file": "|".join(sorted(entry["xsd_files"])) or None,
                        "presentation_file": "|".join(
                            sorted(entry["presentation_files"])
                        )
                        or None,
                        "label_file": "|".join(sorted(entry["label_files"])) or None,
                        "calculation_file": "|".join(
                            sorted(entry["calculation_files"])
                        )
                        or None,
                    },
                )
            )

        for concept in sorted(
            taxonomy.concepts.values(), key=lambda item: item.concept_id
        ):
            lines.append(
                insert_sql(
                    "taxonomy_concept",
                    {
                        "concept_id": concept.concept_id,
                        "taxonomy_id": concept.taxonomy_id,
                        "namespace": concept.namespace,
                        "local_name": concept.local_name,
                        "zh_label": concept.zh_label,
                        "en_label": concept.en_label,
                        "terse_code": concept.terse_code,
                        "period_type": concept.period_type,
                        "balance_type": concept.balance_type,
                        "data_type": concept.data_type,
                        "is_abstract": concept.is_abstract,
                    },
                )
            )

        for row_index, row in enumerate(taxonomy.presentation_rows, start=1):
            row_with_id = {
                **row,
                "id": row.get("id") if row.get("id") is not None else row_index,
            }
            lines.append(
                insert_sql(
                    "taxonomy_presentation",
                    {
                        column: row_with_id.get(column)
                        for column in TAXONOMY_PRESENTATION_COLUMNS
                    },
                )
            )
        for row_index, row in enumerate(taxonomy.calculation_rows, start=1):
            row_with_id = {
                **row,
                "id": row.get("id") if row.get("id") is not None else row_index,
            }
            lines.append(
                insert_sql(
                    "taxonomy_calculation",
                    {
                        column: row_with_id.get(column)
                        for column in TAXONOMY_CALCULATION_COLUMNS
                    },
                )
            )

        lines.extend(
            [
                "SELECT setval(pg_get_serial_sequence('taxonomy_presentation', 'id'), "
                "COALESCE(MAX(id), 1), MAX(id) IS NOT NULL) FROM taxonomy_presentation;",
                "SELECT setval(pg_get_serial_sequence('taxonomy_calculation', 'id'), "
                "COALESCE(MAX(id), 1), MAX(id) IS NOT NULL) FROM taxonomy_calculation;",
            ]
        )

    if report_row is not None:
        lines.append(insert_sql("report_instance", report_row))

    for fact in facts:
        lines.append(
            insert_sql(
                "xbrl_fact",
                {
                    "fact_id": fact["fact_id"],
                    "report_id": fact["report_id"],
                    "concept_id": fact["concept_id"],
                    "context_id": fact["context_id"],
                    "unit_id": fact["unit_id"] or fact["unit_text"],
                    "value_numeric": fact["value_numeric"],
                    "value_text": fact["value_text"],
                    "decimals": fact["decimals"],
                    "scale": fact["scale"],
                    "instant_date": fact["instant_date"],
                    "period_start": fact["period_start"],
                    "period_end": fact["period_end"],
                    "segment_json": fact["segment_json"],
                },
            )
        )

    for row in field_rows:
        lines.append(insert_sql("field_dictionary", row))
    for row in concept_mapping_rows:
        lines.append(insert_sql("field_concept_mapping", row))
    for row in metric_rows:
        lines.append(insert_sql("financial_metric_value", row))

    lines.append("COMMIT;")
    return "\n".join(lines) + "\n"


def load_sql_into_postgresql(sql_text: str) -> None:
    settings = get_database_settings()
    if settings.mode != "postgresql":
        raise RuntimeError(
            "--load-db requires DATABASE_MODE=postgresql and PostgreSQL connection ENV values."
        )
    connection = open_database_connection(settings)
    try:
        connection.execute(sql_text, prepare=False)
        connection.commit()
    except Exception:
        connection.rollback()
        raise
    finally:
        connection.close()


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description=(
            "Parse a TIFRS taxonomy and XBRL/iXBRL instances into "
            "PostgreSQL-compatible SQL."
        )
    )
    parser.add_argument(
        "--taxonomy-root",
        help="Root directory of the XBRL taxonomy, e.g. tifrs-20200630.",
    )
    parser.add_argument(
        "--taxonomy-from-db",
        action="store_true",
        help="Load taxonomy metadata from the PostgreSQL database configured by ENV.",
    )
    parser.add_argument(
        "--taxonomy-sqlite-db",
        help=(
            "Load taxonomy metadata from an existing SQLite XBRL database, "
            "while still generating PostgreSQL-compatible SQL."
        ),
    )
    parser.add_argument("--instance", help="Path to one XBRL instance file.")
    parser.add_argument(
        "--instance-dir",
        help="Recursively parse all XBRL/iXBRL files under this directory.",
    )
    parser.add_argument(
        "--sql-output",
        required=True,
        help="Output path for generated PostgreSQL SQL.",
    )
    parser.add_argument(
        "--load-db",
        action="store_true",
        help="Execute the generated SQL against the PostgreSQL database configured by ENV.",
    )
    parser.add_argument(
        "--field-mode",
        choices=("auto-concept", "custom"),
        default="auto-concept",
        help=(
            "auto-concept creates a 1:1 field/concept mapping; "
            "custom loads field definitions from JSON."
        ),
    )
    parser.add_argument(
        "--field-mapping-json",
        help="With custom mode, load {fields: [...], mappings: [...]} from this JSON file.",
    )
    return parser


def main() -> None:
    args = build_parser().parse_args()
    sql_output = Path(args.sql_output).resolve()

    if args.taxonomy_from_db and args.taxonomy_sqlite_db:
        raise SystemExit(
            "Use only one taxonomy source: --taxonomy-from-db or --taxonomy-sqlite-db."
        )
    if args.taxonomy_from_db:
        taxonomy = load_taxonomy_from_postgresql()
    elif args.taxonomy_sqlite_db:
        taxonomy = base.load_taxonomy_from_db(
            Path(args.taxonomy_sqlite_db).resolve()
        )
    else:
        if not args.taxonomy_root:
            raise SystemExit(
                "--taxonomy-root is required unless --taxonomy-from-db or "
                "--taxonomy-sqlite-db is used."
            )
        taxonomy = base.parse_taxonomy(Path(args.taxonomy_root).resolve())

    report_rows: List[Dict[str, Any]] = []
    all_facts: List[Dict[str, Any]] = []
    all_field_rows: List[Dict[str, Any]] = []
    all_concept_mapping_rows: List[Dict[str, Any]] = []
    all_metric_rows: List[Dict[str, Any]] = []

    instance_paths: List[Path] = []
    if args.instance:
        instance_paths.append(Path(args.instance).resolve())
    if args.instance_dir:
        instance_paths.extend(
            base.discover_instance_files(Path(args.instance_dir).resolve())
        )
    instance_paths = sorted(dict.fromkeys(instance_paths))
    instance_paths, skipped_instance_paths = base.dedupe_instance_paths(instance_paths)

    raw_mapping_rows: List[Dict[str, Any]] = []
    if args.field_mode == "custom":
        if not args.field_mapping_json:
            raise SystemExit(
                "--field-mapping-json is required when --field-mode custom is used."
            )
        field_rows, raw_mapping_rows = base.load_custom_field_mapping(
            Path(args.field_mapping_json).resolve()
        )
        all_field_rows.extend(field_rows)

    for instance_path in instance_paths:
        report_row, facts = base.parse_instance(instance_path, taxonomy)
        report_rows.append(report_row)
        all_facts.extend(facts)

        if args.field_mode == "custom":
            for mapping in raw_mapping_rows:
                concept_ids = mapping.get("concept_ids")
                if concept_ids is None and mapping.get("concept_id"):
                    concept_ids = [mapping["concept_id"]]
                for concept_id in concept_ids or []:
                    all_concept_mapping_rows.append(
                        {
                            "field_id": mapping["field_id"],
                            "concept_id": concept_id,
                            "taxonomy_id": mapping.get("taxonomy_id"),
                            "industry_type": mapping.get("industry_type"),
                            "priority": mapping.get("priority", 1),
                            "effective_from": mapping.get("effective_from"),
                            "effective_to": mapping.get("effective_to"),
                        }
                    )
            all_metric_rows.extend(
                base.build_custom_metric_rows(report_row, facts, raw_mapping_rows)
            )
        else:
            field_rows, mapping_rows, metric_rows = base.build_auto_field_rows(
                report_row, facts, taxonomy.concepts
            )
            all_field_rows.extend(field_rows)
            all_concept_mapping_rows.extend(mapping_rows)
            all_metric_rows.extend(metric_rows)

    all_field_rows = base.dedupe_rows(all_field_rows, ["field_id"])
    all_concept_mapping_rows = base.dedupe_rows(
        all_concept_mapping_rows,
        [
            "field_id",
            "concept_id",
            "taxonomy_id",
            "industry_type",
            "effective_from",
            "effective_to",
        ],
    )

    sql_blocks: list[str] = []
    if not args.taxonomy_from_db:
        sql_blocks.append(
            render_sql(taxonomy, None, [], [], [], [], include_taxonomy=True)
        )
    for report_row in report_rows:
        report_facts = [
            fact
            for fact in all_facts
            if fact["report_id"] == report_row["report_id"]
        ]
        report_metrics = [
            row
            for row in all_metric_rows
            if row["report_id"] == report_row["report_id"]
        ]
        sql_blocks.append(
            render_sql(
                taxonomy,
                report_row,
                report_facts,
                [],
                [],
                report_metrics,
                include_taxonomy=False,
            )
        )

    if all_field_rows or all_concept_mapping_rows:
        lines = ["BEGIN;"]
        for row in all_field_rows:
            lines.append(insert_sql("field_dictionary", row))
        for row in all_concept_mapping_rows:
            lines.append(insert_sql("field_concept_mapping", row))
        lines.append("COMMIT;")
        sql_blocks.append("\n".join(lines) + "\n")

    header = (
        "-- PostgreSQL XBRL import generated by build_xbrl_sql_postgresql.py.\n"
        "-- Apply the PostgreSQL V1.0 schema migration before importing this file.\n\n"
    )
    sql_text = header + "".join(sql_blocks)
    sql_output.parent.mkdir(parents=True, exist_ok=True)
    sql_output.write_text(sql_text, encoding="utf-8")

    if args.load_db:
        load_sql_into_postgresql(sql_text)

    print(f"taxonomy_version={taxonomy.version}")
    print(f"taxonomy_entry_points={len(taxonomy.entry_points)}")
    print(f"taxonomy_concepts={len(taxonomy.concepts)}")
    print(f"taxonomy_presentation_rows={len(taxonomy.presentation_rows)}")
    print(f"taxonomy_calculation_rows={len(taxonomy.calculation_rows)}")
    print(f"reports={len(report_rows)}")
    print(f"skipped_duplicate_reports={len(skipped_instance_paths)}")
    print(f"facts={len(all_facts)}")
    print(f"field_dictionary_rows={len(all_field_rows)}")
    print(f"field_concept_mapping_rows={len(all_concept_mapping_rows)}")
    print(f"financial_metric_value_rows={len(all_metric_rows)}")
    print(f"sql_output={sql_output}")
    print(f"loaded_to_postgresql={bool(args.load_db)}")


if __name__ == "__main__":
    main()
