import sqlite3
from typing import Any

from src.shared.database.config import DatabaseSettings, get_database_settings


class DatabaseIntegrityError(sqlite3.IntegrityError):
    """Backend-neutral constraint violation raised by the PostgreSQL adapter."""


def is_postgresql() -> bool:
    return get_database_settings().mode == "postgresql"


def _postgresql_placeholders(query: str) -> str:
    """Convert DB-API qmark parameters without touching quoted SQL text."""
    output: list[str] = []
    index = 0
    quote: str | None = None
    while index < len(query):
        character = query[index]
        following = query[index + 1] if index + 1 < len(query) else ""

        if quote == "--":
            output.append(character)
            if character == "\n":
                quote = None
            index += 1
            continue
        if quote == "/*":
            output.append(character)
            if character == "*" and following == "/":
                output.append(following)
                index += 2
                quote = None
            else:
                index += 1
            continue
        if quote in {"'", '"'}:
            output.append(character)
            if character == quote:
                if following == quote:
                    output.append(following)
                    index += 2
                    continue
                quote = None
            index += 1
            continue

        if character == "-" and following == "-":
            output.extend((character, following))
            quote = "--"
            index += 2
        elif character == "/" and following == "*":
            output.extend((character, following))
            quote = "/*"
            index += 2
        elif character in {"'", '"'}:
            output.append(character)
            quote = character
            index += 1
        elif character == "?":
            output.append("%s")
            index += 1
        else:
            output.append(character)
            index += 1
    return "".join(output)


class PostgreSQLConnectionAdapter:
    """Expose the SQLite-style connection API used by existing repositories."""

    def __init__(self, connection: Any):
        self._connection = connection

    def execute(self, query: Any, params: Any = None, **kwargs: Any) -> Any:
        if isinstance(query, str):
            if query.strip().upper() == "BEGIN IMMEDIATE":
                query = "BEGIN"
            elif params is not None:
                query = _postgresql_placeholders(query)
        try:
            if params is None:
                return self._connection.execute(query, **kwargs)
            return self._connection.execute(query, params, **kwargs)
        except Exception as exc:
            if exc.__class__.__name__ == "IntegrityError":
                raise DatabaseIntegrityError(str(exc)) from exc
            raise

    def executemany(self, query: str, params_seq: Any, **kwargs: Any) -> Any:
        try:
            cursor = self._connection.cursor()
            cursor.executemany(_postgresql_placeholders(query), params_seq, **kwargs)
            return cursor
        except Exception as exc:
            if exc.__class__.__name__ == "IntegrityError":
                raise DatabaseIntegrityError(str(exc)) from exc
            raise

    def __getattr__(self, name: str) -> Any:
        return getattr(self._connection, name)

    def __enter__(self) -> "PostgreSQLConnectionAdapter":
        self._connection.__enter__()
        return self

    def __exit__(self, exc_type: Any, exc: Any, traceback: Any) -> Any:
        return self._connection.__exit__(exc_type, exc, traceback)


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
        from psycopg import sql
        from psycopg.rows import dict_row
    except ImportError as exc:
        raise RuntimeError(
            "PostgreSQL mode requires psycopg. Install dependencies from requirements.txt."
        ) from exc

    connection_parameters = {
        "host": resolved.host,
        "port": resolved.port,
        "dbname": resolved.database,
        "user": resolved.username,
        "password": resolved.password,
        "sslmode": resolved.sslmode,
        "connect_timeout": resolved.connect_timeout_seconds,
        "application_name": resolved.application_name,
        "row_factory": dict_row,
    }
    if resolved.sslrootcert:
        connection_parameters["sslrootcert"] = resolved.sslrootcert

    connection = psycopg.connect(
        **connection_parameters,
    )
    schema_exists = connection.execute(
        "SELECT 1 FROM information_schema.schemata WHERE schema_name = %s",
        [resolved.schema],
    ).fetchone()
    if schema_exists is None:
        connection.close()
        raise RuntimeError(
            f"PostgreSQL schema {resolved.schema!r} does not exist or is not accessible."
        )
    connection.execute(
        sql.SQL("SET search_path TO {}").format(sql.Identifier(resolved.schema))
    )
    connection.commit()
    return PostgreSQLConnectionAdapter(connection)


def get_table_columns(connection: Any, table_name: str) -> set[str]:
    if is_postgresql():
        rows = connection.execute(
            """
            SELECT column_name
            FROM information_schema.columns
            WHERE table_schema = current_schema() AND table_name = ?
            """,
            [table_name],
        ).fetchall()
        return {row["column_name"] for row in rows}
    return {
        row["name"]
        for row in connection.execute(f"PRAGMA table_info({table_name})").fetchall()
    }


def test_database_connection(settings: DatabaseSettings | None = None) -> None:
    connection = open_database_connection(settings)
    try:
        connection.execute("SELECT 1").fetchone()
    finally:
        connection.close()
