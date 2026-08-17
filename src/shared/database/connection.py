import sqlite3
from typing import Any

from src.shared.database.config import DatabaseSettings, get_database_settings


def open_database_connection(settings: DatabaseSettings | None = None) -> Any:
    resolved = settings or get_database_settings()
    if resolved.mode == "sqlite":
        assert resolved.sqlite_path is not None
        connection = sqlite3.connect(resolved.sqlite_path)
        connection.row_factory = sqlite3.Row
        connection.execute("PRAGMA foreign_keys = ON")
        return connection

    try:
        import psycopg
        from psycopg.rows import dict_row
    except ImportError as exc:
        raise RuntimeError(
            "PostgreSQL mode requires psycopg. Install dependencies from requirements.txt."
        ) from exc

    return psycopg.connect(
        host=resolved.host,
        port=resolved.port,
        dbname=resolved.database,
        user=resolved.username,
        password=resolved.password,
        sslmode=resolved.sslmode,
        connect_timeout=resolved.connect_timeout_seconds,
        application_name=resolved.application_name,
        row_factory=dict_row,
    )


def test_database_connection(settings: DatabaseSettings | None = None) -> None:
    connection = open_database_connection(settings)
    try:
        connection.execute("SELECT 1").fetchone()
    finally:
        connection.close()
