import sqlite3
import uuid
from datetime import datetime, timezone
from typing import Any

from src.services.db_path import resolve_sqlite_db_path


ALL_COMPANY_VALUE = "All"
DEFAULT_DATA_SOURCE = "財務報表"


def utc_now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def compact_text(value: Any) -> str:
    return " ".join(str(value or "").split())


def preserve_text(value: Any) -> str:
    return str(value or "").strip()


def build_schema_segment(value: str) -> str:
    return "_".join(compact_text(value).split())


def build_source_schema_key(data_source: str, industry: str, company_label: str) -> str:
    return (
        "expert_knowledge."
        f"{build_schema_segment(data_source)}."
        f"{build_schema_segment(industry)}."
        f"{build_schema_segment(company_label)}"
    )


def get_connection() -> sqlite3.Connection:
    connection = sqlite3.connect(resolve_sqlite_db_path())
    connection.row_factory = sqlite3.Row
    return connection


def ensure_expert_knowledge_schema() -> None:
    now = utc_now_iso()
    with get_connection() as connection:
        connection.execute(
            """
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
            )
            """
        )
        columns = {
            row["name"]
            for row in connection.execute("PRAGMA table_info(expert_knowledge_entry)")
        }
        if "created_at" not in columns:
            connection.execute(
                "ALTER TABLE expert_knowledge_entry ADD COLUMN created_at TEXT NOT NULL DEFAULT ''"
            )
        if "updated_at" not in columns:
            connection.execute(
                "ALTER TABLE expert_knowledge_entry ADD COLUMN updated_at TEXT NOT NULL DEFAULT ''"
            )
        connection.execute(
            """
            UPDATE expert_knowledge_entry
            SET created_at = ?
            WHERE created_at = ''
                OR created_at IS NULL
            """,
            [now],
        )
        connection.execute(
            """
            UPDATE expert_knowledge_entry
            SET updated_at = ?
            WHERE updated_at = ''
                OR updated_at IS NULL
            """,
            [now],
        )
        connection.execute(
            """
            CREATE INDEX IF NOT EXISTS idx_expert_knowledge_entry_updated_at
            ON expert_knowledge_entry(updated_at DESC)
            WHERE deleted_at IS NULL
            """
        )
        connection.execute(
            """
            CREATE INDEX IF NOT EXISTS idx_expert_knowledge_entry_created_at
            ON expert_knowledge_entry(created_at DESC)
            WHERE deleted_at IS NULL
            """
        )
        connection.execute(
            """
            CREATE INDEX IF NOT EXISTS idx_expert_knowledge_entry_lookup
            ON expert_knowledge_entry(data_source, industry, company_label, company_prompt_value)
            WHERE deleted_at IS NULL
            """
        )


def row_to_entry(row: sqlite3.Row) -> dict[str, str]:
    return {
        "id": row["id"],
        "title": row["title"],
        "dataSource": row["data_source"],
        "industry": row["industry"],
        "companyLabel": row["company_label"],
        "companyPromptValue": row["company_prompt_value"],
        "sourceSchemaKey": row["source_schema_key"],
        "anchorDescription": row["anchor_description"],
        "systemPrompt": row["system_prompt"],
        "createdAt": row["created_at"],
        "updatedAt": row["updated_at"],
    }


def normalize_entry_payload(payload: dict[str, Any]) -> dict[str, str]:
    title = compact_text(payload.get("title"))
    data_source = compact_text(payload.get("dataSource")) or DEFAULT_DATA_SOURCE
    industry = compact_text(payload.get("industry"))
    company_label = compact_text(payload.get("companyLabel")) or ALL_COMPANY_VALUE
    company_prompt_value = compact_text(payload.get("companyPromptValue"))
    anchor_description = preserve_text(payload.get("anchorDescription"))
    system_prompt = preserve_text(payload.get("systemPrompt"))
    source_schema_key = compact_text(payload.get("sourceSchemaKey")) or build_source_schema_key(
        data_source,
        industry,
        company_label,
    )

    return {
        "title": title,
        "dataSource": data_source,
        "industry": industry,
        "companyLabel": company_label,
        "companyPromptValue": company_prompt_value,
        "sourceSchemaKey": source_schema_key,
        "anchorDescription": anchor_description,
        "systemPrompt": system_prompt,
    }


def validate_entry_payload(entry: dict[str, str]) -> None:
    required_fields = [
        ("title", "title is required"),
        ("dataSource", "dataSource is required"),
        ("industry", "industry is required"),
        ("companyLabel", "companyLabel is required"),
        ("sourceSchemaKey", "sourceSchemaKey is required"),
        ("anchorDescription", "anchorDescription is required"),
        ("systemPrompt", "systemPrompt is required"),
    ]
    missing_messages = [message for field, message in required_fields if not entry[field]]
    if missing_messages:
        raise ValueError(", ".join(missing_messages))


def build_search_clause(keyword: str) -> tuple[str, list[str]]:
    normalized_keyword = compact_text(keyword)
    if not normalized_keyword:
        return "", []

    like_keyword = f"%{normalized_keyword}%"
    return (
        """
        AND (
            title LIKE ?
            OR industry LIKE ?
            OR company_label LIKE ?
            OR data_source LIKE ?
            OR anchor_description LIKE ?
            OR system_prompt LIKE ?
        )
        """,
        [like_keyword] * 6,
    )


def list_expert_knowledge_entries(
    *,
    page: int,
    page_size: int,
    offset: int | None,
    keyword: str,
) -> dict[str, Any]:
    ensure_expert_knowledge_schema()
    normalized_page_size = max(1, min(page_size, 100))
    normalized_page = max(1, page)
    normalized_offset = max(0, offset if offset is not None else (normalized_page - 1) * normalized_page_size)
    where_sql, search_params = build_search_clause(keyword)

    with get_connection() as connection:
        total = connection.execute(
            f"""
            SELECT COUNT(*) AS total
            FROM expert_knowledge_entry
            WHERE deleted_at IS NULL
            {where_sql}
            """,
            search_params,
        ).fetchone()["total"]
        rows = connection.execute(
            f"""
            SELECT *
            FROM expert_knowledge_entry
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


def list_all_active_expert_knowledge_entries() -> list[dict[str, str]]:
    ensure_expert_knowledge_schema()
    with get_connection() as connection:
        rows = connection.execute(
            """
            SELECT *
            FROM expert_knowledge_entry
            WHERE deleted_at IS NULL
            ORDER BY updated_at DESC, id DESC
            """
        ).fetchall()
    return [row_to_entry(row) for row in rows]


def list_applied_expert_knowledge_entries(
    *,
    company_label: str,
    company_prompt_value: str,
    industry: str,
    data_source: str,
) -> list[dict[str, str]]:
    ensure_expert_knowledge_schema()
    filters = []
    params: list[str] = []

    normalized_data_source = compact_text(data_source)
    normalized_industry = compact_text(industry)
    normalized_company_label = compact_text(company_label)
    normalized_company_prompt_value = compact_text(company_prompt_value)

    if normalized_data_source:
        filters.append("data_source = ?")
        params.append(normalized_data_source)
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
            FROM expert_knowledge_entry
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
        if entry["companyLabel"] == ALL_COMPANY_VALUE
        or entry["companyLabel"] == normalized_company_label
        or entry["companyPromptValue"] == normalized_company_prompt_value
    ]


def get_expert_knowledge_entry(entry_id: str) -> dict[str, str] | None:
    ensure_expert_knowledge_schema()
    with get_connection() as connection:
        row = connection.execute(
            """
            SELECT *
            FROM expert_knowledge_entry
            WHERE id = ? AND deleted_at IS NULL
            """,
            [entry_id],
        ).fetchone()
    return row_to_entry(row) if row else None


def create_expert_knowledge_entry(payload: dict[str, Any]) -> dict[str, str]:
    ensure_expert_knowledge_schema()
    entry = normalize_entry_payload(payload)
    validate_entry_payload(entry)
    entry_id = compact_text(payload.get("id")) or str(uuid.uuid4())
    now = utc_now_iso()

    with get_connection() as connection:
        connection.execute(
            """
            INSERT INTO expert_knowledge_entry (
                id,
                title,
                data_source,
                industry,
                company_label,
                company_prompt_value,
                source_schema_key,
                anchor_description,
                system_prompt,
                created_at,
                updated_at
            )
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            [
                entry_id,
                entry["title"],
                entry["dataSource"],
                entry["industry"],
                entry["companyLabel"],
                entry["companyPromptValue"],
                entry["sourceSchemaKey"],
                entry["anchorDescription"],
                entry["systemPrompt"],
                now,
                now,
            ],
        )

    created_entry = get_expert_knowledge_entry(entry_id)
    if created_entry is None:
        raise RuntimeError("Failed to load created expert knowledge entry.")
    return created_entry


def update_expert_knowledge_entry(entry_id: str, payload: dict[str, Any]) -> dict[str, str] | None:
    ensure_expert_knowledge_schema()
    if get_expert_knowledge_entry(entry_id) is None:
        return None

    entry = normalize_entry_payload(payload)
    validate_entry_payload(entry)
    now = utc_now_iso()

    with get_connection() as connection:
        connection.execute(
            """
            UPDATE expert_knowledge_entry
            SET title = ?,
                data_source = ?,
                industry = ?,
                company_label = ?,
                company_prompt_value = ?,
                source_schema_key = ?,
                anchor_description = ?,
                system_prompt = ?,
                updated_at = ?
            WHERE id = ? AND deleted_at IS NULL
            """,
            [
                entry["title"],
                entry["dataSource"],
                entry["industry"],
                entry["companyLabel"],
                entry["companyPromptValue"],
                entry["sourceSchemaKey"],
                entry["anchorDescription"],
                entry["systemPrompt"],
                now,
                entry_id,
            ],
        )

    return get_expert_knowledge_entry(entry_id)


def delete_expert_knowledge_entry(entry_id: str) -> bool:
    ensure_expert_knowledge_schema()
    now = utc_now_iso()
    with get_connection() as connection:
        cursor = connection.execute(
            """
            UPDATE expert_knowledge_entry
            SET deleted_at = ?,
                updated_at = ?
            WHERE id = ? AND deleted_at IS NULL
            """,
            [now, now, entry_id],
        )
    return cursor.rowcount > 0
