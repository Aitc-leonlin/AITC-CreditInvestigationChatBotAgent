import sqlite3
import uuid
from datetime import datetime, timezone
from typing import Any

from src.services.db_path import resolve_sqlite_db_path


def utc_now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def compact_text(value: Any) -> str:
    return " ".join(str(value or "").split())


def preserve_text(value: Any) -> str:
    return str(value or "").strip()


def get_connection() -> sqlite3.Connection:
    connection = sqlite3.connect(resolve_sqlite_db_path())
    connection.row_factory = sqlite3.Row
    return connection


def ensure_warehouse_data_schema() -> None:
    now = utc_now_iso()
    with get_connection() as connection:
        connection.execute(
            """
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
            )
            """
        )
        columns = {
            row["name"]
            for row in connection.execute("PRAGMA table_info(warehouse_data_entry)")
        }
        if "record_updated_at" not in columns:
            connection.execute(
                "ALTER TABLE warehouse_data_entry ADD COLUMN record_updated_at TEXT NOT NULL DEFAULT ''"
            )
        if "created_at" not in columns:
            connection.execute(
                "ALTER TABLE warehouse_data_entry ADD COLUMN created_at TEXT NOT NULL DEFAULT ''"
            )
        if "updated_at" not in columns:
            connection.execute(
                "ALTER TABLE warehouse_data_entry ADD COLUMN updated_at TEXT NOT NULL DEFAULT ''"
            )
        connection.execute(
            """
            UPDATE warehouse_data_entry
            SET created_at = ?
            WHERE created_at = ''
                OR created_at IS NULL
            """,
            [now],
        )
        connection.execute(
            """
            UPDATE warehouse_data_entry
            SET updated_at = ?
            WHERE updated_at = ''
                OR updated_at IS NULL
            """,
            [now],
        )
        connection.execute(
            """
            UPDATE warehouse_data_entry
            SET record_updated_at = updated_at
            WHERE record_updated_at = ''
                AND updated_at IS NOT NULL
                AND updated_at != ''
            """
        )
        connection.execute(
            """
            CREATE INDEX IF NOT EXISTS idx_warehouse_data_entry_updated_at
            ON warehouse_data_entry(updated_at DESC)
            WHERE deleted_at IS NULL
            """
        )
        connection.execute(
            """
            CREATE INDEX IF NOT EXISTS idx_warehouse_data_entry_created_at
            ON warehouse_data_entry(created_at DESC)
            WHERE deleted_at IS NULL
            """
        )
        connection.execute(
            """
            CREATE INDEX IF NOT EXISTS idx_warehouse_data_entry_lookup
            ON warehouse_data_entry(category, industry, company_label, company_prompt_value)
            WHERE deleted_at IS NULL
            """
        )


def row_to_entry(row: sqlite3.Row) -> dict[str, str]:
    return {
        "id": row["id"],
        "category": row["category"],
        "title": row["title"],
        "industry": row["industry"],
        "companyLabel": row["company_label"],
        "companyPromptValue": row["company_prompt_value"],
        "summary": row["summary"],
        "source": row["source"],
        "url": row["url"],
        "recordUpdatedAt": row["record_updated_at"],
        "createdAt": row["created_at"],
        "updatedAt": row["updated_at"],
    }


def normalize_entry_payload(payload: dict[str, Any]) -> dict[str, str]:
    return {
        "category": compact_text(payload.get("category")),
        "title": compact_text(payload.get("title")),
        "industry": compact_text(payload.get("industry")),
        "companyLabel": compact_text(payload.get("companyLabel")),
        "companyPromptValue": compact_text(payload.get("companyPromptValue")),
        "summary": preserve_text(payload.get("summary")),
        "source": compact_text(payload.get("source")),
        "url": compact_text(payload.get("url")),
    }


def validate_entry_payload(entry: dict[str, str]) -> None:
    required_fields = [
        ("category", "category is required"),
        ("title", "title is required"),
        ("industry", "industry is required"),
        ("companyLabel", "companyLabel is required"),
        ("summary", "summary is required"),
        ("source", "source is required"),
    ]
    missing_messages = [message for field, message in required_fields if not entry[field]]
    if missing_messages:
        raise ValueError(", ".join(missing_messages))


def build_search_clause(keyword: str, category: str) -> tuple[str, list[str]]:
    clauses = []
    params: list[str] = []
    normalized_category = compact_text(category)
    normalized_keyword = compact_text(keyword)

    if normalized_category:
        clauses.append("category = ?")
        params.append(normalized_category)

    if normalized_keyword:
        like_keyword = f"%{normalized_keyword}%"
        clauses.append(
            """
            (
                title LIKE ?
                OR category LIKE ?
                OR industry LIKE ?
                OR company_label LIKE ?
                OR source LIKE ?
                OR record_updated_at LIKE ?
                OR summary LIKE ?
            )
            """
        )
        params.extend([like_keyword] * 7)

    if not clauses:
        return "", []

    return "AND " + " AND ".join(clauses), params


def list_warehouse_data_entries(
    *,
    page: int,
    page_size: int,
    offset: int | None,
    keyword: str,
    category: str,
) -> dict[str, Any]:
    ensure_warehouse_data_schema()
    normalized_page_size = max(1, min(page_size, 100))
    normalized_page = max(1, page)
    normalized_offset = max(
        0,
        offset if offset is not None else (normalized_page - 1) * normalized_page_size,
    )
    where_sql, search_params = build_search_clause(keyword, category)

    with get_connection() as connection:
        total = connection.execute(
            f"""
            SELECT COUNT(*) AS total
            FROM warehouse_data_entry
            WHERE deleted_at IS NULL
            {where_sql}
            """,
            search_params,
        ).fetchone()["total"]
        rows = connection.execute(
            f"""
            SELECT *
            FROM warehouse_data_entry
            WHERE deleted_at IS NULL
            {where_sql}
            ORDER BY created_at DESC, id DESC
            LIMIT ? OFFSET ?
            """,
            [*search_params, normalized_page_size, normalized_offset],
        ).fetchall()

    return {
        "entries": [row_to_entry(row) for row in rows],
        "total": total,
        "page": normalized_page,
        "pageSize": normalized_page_size,
        "offset": normalized_offset,
    }


def list_applied_warehouse_data_entries(
    *,
    company_label: str,
    company_prompt_value: str,
    industry: str,
    category: str,
) -> list[dict[str, str]]:
    ensure_warehouse_data_schema()
    filters = []
    params: list[str] = []

    normalized_category = compact_text(category)
    normalized_industry = compact_text(industry)
    normalized_company_label = compact_text(company_label)
    normalized_company_prompt_value = compact_text(company_prompt_value)

    if normalized_category:
        filters.append("category = ?")
        params.append(normalized_category)
    if normalized_industry:
        filters.append("industry = ?")
        params.append(normalized_industry)

    where_sql = ""
    if filters:
        where_sql = "AND " + " AND ".join(filters)

    with get_connection() as connection:
        rows = connection.execute(
            f"""
            SELECT *
            FROM warehouse_data_entry
            WHERE deleted_at IS NULL
            {where_sql}
            ORDER BY updated_at DESC, id DESC
            LIMIT 200
            """,
            params,
        ).fetchall()

    entries = [row_to_entry(row) for row in rows]
    if not normalized_company_label and not normalized_company_prompt_value:
        return entries

    return [
        entry
        for entry in entries
        if entry["companyLabel"] == normalized_company_label
        or entry["companyPromptValue"] == normalized_company_prompt_value
    ]


def get_warehouse_data_entry(entry_id: str) -> dict[str, str] | None:
    ensure_warehouse_data_schema()
    with get_connection() as connection:
        row = connection.execute(
            """
            SELECT *
            FROM warehouse_data_entry
            WHERE id = ? AND deleted_at IS NULL
            """,
            [entry_id],
        ).fetchone()
    return row_to_entry(row) if row else None


def create_warehouse_data_entry(payload: dict[str, Any]) -> dict[str, str]:
    ensure_warehouse_data_schema()
    entry = normalize_entry_payload(payload)
    validate_entry_payload(entry)
    entry_id = compact_text(payload.get("id")) or str(uuid.uuid4())
    now = utc_now_iso()

    with get_connection() as connection:
        connection.execute(
            """
            INSERT INTO warehouse_data_entry (
                id,
                category,
                title,
                industry,
                company_label,
                company_prompt_value,
                summary,
                source,
                url,
                record_updated_at,
                created_at,
                updated_at
            )
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            [
                entry_id,
                entry["category"],
                entry["title"],
                entry["industry"],
                entry["companyLabel"],
                entry["companyPromptValue"],
                entry["summary"],
                entry["source"],
                entry["url"],
                now,
                now,
                now,
            ],
        )

    created_entry = get_warehouse_data_entry(entry_id)
    if created_entry is None:
        raise RuntimeError("Failed to load created warehouse data entry.")
    return created_entry


def update_warehouse_data_entry(entry_id: str, payload: dict[str, Any]) -> dict[str, str] | None:
    ensure_warehouse_data_schema()
    if get_warehouse_data_entry(entry_id) is None:
        return None

    entry = normalize_entry_payload(payload)
    validate_entry_payload(entry)
    now = utc_now_iso()

    with get_connection() as connection:
        connection.execute(
            """
            UPDATE warehouse_data_entry
            SET category = ?,
                title = ?,
                industry = ?,
                company_label = ?,
                company_prompt_value = ?,
                summary = ?,
                source = ?,
                url = ?,
                record_updated_at = ?,
                updated_at = ?
            WHERE id = ? AND deleted_at IS NULL
            """,
            [
                entry["category"],
                entry["title"],
                entry["industry"],
                entry["companyLabel"],
                entry["companyPromptValue"],
                entry["summary"],
                entry["source"],
                entry["url"],
                now,
                now,
                entry_id,
            ],
        )

    return get_warehouse_data_entry(entry_id)


def delete_warehouse_data_entry(entry_id: str) -> bool:
    ensure_warehouse_data_schema()
    now = utc_now_iso()
    with get_connection() as connection:
        cursor = connection.execute(
            """
            UPDATE warehouse_data_entry
            SET deleted_at = ?,
                updated_at = ?
            WHERE id = ? AND deleted_at IS NULL
            """,
            [now, now, entry_id],
        )
    return cursor.rowcount > 0
