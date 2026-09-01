from __future__ import annotations

from collections.abc import Iterable, Mapping, Sequence
from functools import lru_cache
from typing import Any

from sqlalchemy import MetaData, Table, create_engine, event, inspect, text
from sqlalchemy.engine import Connection, Engine, URL, make_url
from sqlalchemy.exc import IntegrityError as SQLAlchemyIntegrityError

from src.shared.database.config import DatabaseSettings, get_database_settings
from src.shared.database.serialization import normalize_database_value


class DatabaseIntegrityError(Exception):
    """Database-neutral constraint violation raised by SQLAlchemy."""


class DatabaseRow(dict[str, Any]):
    """Mapping row with the legacy sqlite3.Row integer-index behaviour."""

    def __init__(self, keys: Iterable[str], values: Iterable[Any]):
        normalized_values = tuple(normalize_database_value(value) for value in values)
        super().__init__(zip(keys, normalized_values))
        self._values = normalized_values

    def __getitem__(self, key: str | int) -> Any:
        if isinstance(key, int):
            return self._values[key]
        return super().__getitem__(key)


class DatabaseResult:
    """Small DB-API compatible facade over SQLAlchemy CursorResult."""

    def __init__(self, result: Any):
        self._result = result
        self._keys = list(result.keys()) if result.returns_rows else []
        cursor = getattr(result, "cursor", None)
        self._description = getattr(cursor, "description", None) or [
            (key, None, None, None, None, None, None) for key in self._keys
        ]

    @property
    def rowcount(self) -> int:
        return int(getattr(self._result, "rowcount", -1))

    @property
    def lastrowid(self) -> Any:
        return getattr(self._result, "lastrowid", None)

    @property
    def description(self) -> Any:
        return self._description

    @property
    def inserted_primary_key(self) -> tuple[Any, ...]:
        return tuple(getattr(self._result, "inserted_primary_key", ()) or ())

    def keys(self) -> list[str]:
        return list(self._keys)

    def _row(self, row: Any) -> DatabaseRow | None:
        if row is None:
            return None
        mapping = row._mapping if hasattr(row, "_mapping") else None
        if mapping is not None:
            return DatabaseRow(mapping.keys(), mapping.values())
        return DatabaseRow(self.keys(), row)

    def fetchone(self) -> DatabaseRow | None:
        return self._row(self._result.fetchone())

    def fetchall(self) -> list[DatabaseRow]:
        return [row for item in self._result.fetchall() if (row := self._row(item)) is not None]

    def __iter__(self):
        for row in self._result:
            yield self._row(row)


def _named_parameters(query: str, values: Sequence[Any]) -> tuple[str, dict[str, Any]]:
    """Replace qmark binds outside SQL quotes/comments with SQLAlchemy named binds."""
    output: list[str] = []
    parameters: dict[str, Any] = {}
    value_index = 0
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
            if value_index >= len(values):
                raise ValueError("SQL has more placeholders than supplied parameters.")
            name = f"p{value_index}"
            # Parenthesizing binds before PostgreSQL's double-colon cast keeps
            # SQLAlchemy text() from truncating the parameter name.
            rendered_bind = f":{name}"
            if query[index + 1:index + 3] == "::":
                rendered_bind = f"({rendered_bind})"
            output.append(rendered_bind)
            parameters[name] = values[value_index]
            value_index += 1
            index += 1
        else:
            output.append(character)
            index += 1
    if value_index != len(values):
        raise ValueError("SQL has fewer placeholders than supplied parameters.")
    return "".join(output), parameters


class SQLAlchemyConnectionAdapter:
    """Compatibility facade routing runtime database I/O through SQLAlchemy."""

    def __init__(self, connection: Connection, settings: DatabaseSettings):
        self._connection = connection
        self.settings = settings
        self.dialect_name = connection.dialect.name
        self._tables: dict[str, Table] = {}

    def execute(self, query: Any, params: Any = None, **_: Any) -> DatabaseResult:
        try:
            if not isinstance(query, str):
                result = self._connection.execute(query, params or {})
            elif params is None:
                result = self._connection.exec_driver_sql(query)
            elif isinstance(params, Mapping):
                result = self._connection.execute(text(query), dict(params))
            else:
                statement, named = _named_parameters(query, list(params))
                result = self._connection.execute(text(statement), named)
            return DatabaseResult(result)
        except SQLAlchemyIntegrityError as exc:
            raise DatabaseIntegrityError(str(exc)) from exc

    def executemany(self, query: str, params_seq: Iterable[Sequence[Any]]) -> DatabaseResult:
        rows = [list(values) for values in params_seq]
        if not rows:
            return self.execute("SELECT 1 WHERE 0 = 1")
        statement, _ = _named_parameters(query, rows[0])
        names = [f"p{index}" for index in range(len(rows[0]))]
        payload = [dict(zip(names, values)) for values in rows]
        try:
            return DatabaseResult(self._connection.execute(text(statement), payload))
        except SQLAlchemyIntegrityError as exc:
            raise DatabaseIntegrityError(str(exc)) from exc

    def executescript(self, script: str) -> None:
        """Run a dialect-specific migration script through SQLAlchemy's driver."""
        driver_connection = self._connection.connection.driver_connection
        if self.dialect_name == "sqlite":
            driver_connection.executescript(script)
        else:
            if not self._connection.in_transaction():
                self._connection.begin()
            driver_connection.execute(script, prepare=False)

    def get_table(self, table_name: str) -> Table:
        if table_name in self._tables:
            return self._tables[table_name]
        schema = self.settings.schema if self.dialect_name == "postgresql" else None
        table = Table(
            table_name,
            MetaData(),
            schema=schema,
            autoload_with=self._connection,
        )
        self._tables[table_name] = table
        return table

    def begin_write_transaction(self) -> None:
        if self._connection.in_transaction():
            return
        statement = "BEGIN IMMEDIATE" if self.dialect_name == "sqlite" else "BEGIN"
        self._connection.exec_driver_sql(statement)

    def clear_tables(self, table_names: Sequence[str]) -> None:
        available_tables = set(get_table_names(self))
        unknown_tables = set(table_names) - available_tables
        if unknown_tables:
            raise ValueError(
                "Cannot clear unknown tables: " + ", ".join(sorted(unknown_tables))
            )
        if not table_names:
            return
        if self.dialect_name == "sqlite":
            # SQLite only accepts foreign-key mode changes outside a transaction.
            self.rollback()
            self._connection.exec_driver_sql("PRAGMA foreign_keys = OFF")
            try:
                for table_name in table_names:
                    self._connection.execute(self.get_table(table_name).delete())
                self.commit()
            except Exception:
                self.rollback()
                raise
            finally:
                self._connection.exec_driver_sql("PRAGMA foreign_keys = ON")
                self.commit()
            return
        preparer = self._connection.dialect.identifier_preparer
        schema = preparer.quote_schema(self.settings.schema)
        qualified_tables = ", ".join(
            f"{schema}.{preparer.quote(table_name)}" for table_name in table_names
        )
        self._connection.exec_driver_sql(
            f"TRUNCATE TABLE {qualified_tables} RESTART IDENTITY CASCADE"
        )

    def insert_do_nothing(
        self,
        table_name: str,
        payload: Mapping[str, Any],
        *,
        conflict_columns: Sequence[str] | None = None,
    ) -> DatabaseResult:
        table = self.get_table(table_name)
        if self.dialect_name == "postgresql":
            from sqlalchemy.dialects.postgresql import insert
        else:
            from sqlalchemy.dialects.sqlite import insert
        statement = insert(table).values(**payload).on_conflict_do_nothing(
            index_elements=list(conflict_columns) if conflict_columns else None
        )
        try:
            return DatabaseResult(self._connection.execute(statement))
        except SQLAlchemyIntegrityError as exc:
            raise DatabaseIntegrityError(str(exc)) from exc

    def insert(self, table_name: str, payload: Mapping[str, Any]) -> DatabaseResult:
        table = self.get_table(table_name)
        try:
            return DatabaseResult(self._connection.execute(table.insert().values(**payload)))
        except SQLAlchemyIntegrityError as exc:
            raise DatabaseIntegrityError(str(exc)) from exc

    def upsert(
        self,
        table_name: str,
        payload: Mapping[str, Any],
        *,
        conflict_columns: Sequence[str],
        update_columns: Sequence[str] | None = None,
    ) -> DatabaseResult:
        table = self.get_table(table_name)
        if self.dialect_name == "postgresql":
            from sqlalchemy.dialects.postgresql import insert
        else:
            from sqlalchemy.dialects.sqlite import insert
        insert_statement = insert(table).values(**payload)
        columns = list(update_columns or [
            name for name in payload if name not in conflict_columns
        ])
        statement = insert_statement.on_conflict_do_update(
            index_elements=list(conflict_columns),
            set_={name: getattr(insert_statement.excluded, name) for name in columns},
        )
        try:
            return DatabaseResult(self._connection.execute(statement))
        except SQLAlchemyIntegrityError as exc:
            raise DatabaseIntegrityError(str(exc)) from exc

    def commit(self) -> None:
        self._connection.commit()

    def rollback(self) -> None:
        self._connection.rollback()

    def close(self) -> None:
        self._connection.close()

    def __enter__(self) -> "SQLAlchemyConnectionAdapter":
        return self

    def __exit__(self, exc_type: Any, exc: Any, traceback: Any) -> None:
        if exc_type is None:
            self.commit()
        else:
            self.rollback()
        self.close()


def _database_url(settings: DatabaseSettings) -> URL:
    if settings.mode == "sqlite":
        assert settings.sqlite_path is not None
        return URL.create("sqlite+pysqlite", database=str(settings.sqlite_path))
    if settings.connection_url:
        raw_url = settings.connection_url
        if raw_url.startswith("postgres://"):
            raw_url = "postgresql://" + raw_url.removeprefix("postgres://")
        url = make_url(raw_url)
        return url.set(drivername="postgresql+psycopg")
    return URL.create(
        "postgresql+psycopg",
        username=settings.username,
        password=settings.password,
        host=settings.host,
        port=settings.port,
        database=settings.database,
    )


def create_database_engine(settings: DatabaseSettings | None = None) -> Engine:
    resolved = settings or get_database_settings()
    return _create_database_engine(resolved)


@lru_cache(maxsize=8)
def _create_database_engine(resolved: DatabaseSettings) -> Engine:
    connect_args: dict[str, Any] = {}
    if resolved.mode == "postgresql":
        connect_args = {
            "sslmode": resolved.sslmode,
            "connect_timeout": resolved.connect_timeout_seconds,
            "application_name": resolved.application_name,
        }
        if resolved.sslrootcert:
            connect_args["sslrootcert"] = resolved.sslrootcert
    engine = create_engine(
        _database_url(resolved),
        connect_args=connect_args,
        pool_pre_ping=True,
    )
    if resolved.mode == "sqlite":
        @event.listens_for(engine, "connect")
        def _enable_sqlite_foreign_keys(dbapi_connection: Any, _: Any) -> None:
            cursor = dbapi_connection.cursor()
            cursor.execute("PRAGMA foreign_keys = ON")
            cursor.close()
    return engine


def open_database_connection(
    settings: DatabaseSettings | None = None,
) -> SQLAlchemyConnectionAdapter:
    resolved = settings or get_database_settings()
    connection = create_database_engine(resolved).connect()
    adapter = SQLAlchemyConnectionAdapter(connection, resolved)
    if resolved.mode == "postgresql":
        schema_exists = adapter.execute(
            "SELECT 1 FROM information_schema.schemata WHERE schema_name = ?",
            [resolved.schema],
        ).fetchone()
        if schema_exists is None:
            adapter.close()
            raise RuntimeError(
                f"PostgreSQL schema {resolved.schema!r} does not exist or is not accessible."
            )
        quoted_schema = connection.dialect.identifier_preparer.quote(resolved.schema)
        connection.exec_driver_sql(f"SET search_path TO {quoted_schema}")
        connection.commit()
    return adapter


def get_table_columns(
    connection: SQLAlchemyConnectionAdapter,
    table_name: str,
) -> set[str]:
    schema = connection.settings.schema if connection.dialect_name == "postgresql" else None
    return {
        column["name"]
        for column in inspect(connection._connection).get_columns(
            table_name,
            schema=schema,
        )
    }


def get_table_names(
    connection: SQLAlchemyConnectionAdapter,
    *,
    prefix: str = "",
) -> list[str]:
    schema = connection.settings.schema if connection.dialect_name == "postgresql" else None
    names = inspect(connection._connection).get_table_names(schema=schema)
    return sorted(name for name in names if not prefix or name.startswith(prefix))


def get_table_column_details(
    connection: SQLAlchemyConnectionAdapter,
    table_name: str,
) -> list[dict[str, Any]]:
    schema = connection.settings.schema if connection.dialect_name == "postgresql" else None
    inspector = inspect(connection._connection)
    primary_keys = set(
        inspector.get_pk_constraint(table_name, schema=schema).get(
            "constrained_columns"
        )
        or []
    )
    return [
        {
            "name": column["name"],
            "column_type": str(column["type"]),
            "not_null": not column.get("nullable", True),
            "default_value": column.get("default"),
            "is_pk": column["name"] in primary_keys,
        }
        for column in inspector.get_columns(table_name, schema=schema)
    ]


def database_storage_exists(settings: DatabaseSettings | None = None) -> bool:
    resolved = settings or get_database_settings()
    if resolved.mode == "postgresql":
        return True
    return resolved.sqlite_path is not None and resolved.sqlite_path.is_file()


def table_exists(connection: SQLAlchemyConnectionAdapter, table_name: str) -> bool:
    schema = connection.settings.schema if connection.dialect_name == "postgresql" else None
    return inspect(connection._connection).has_table(table_name, schema=schema)


def test_database_connection(settings: DatabaseSettings | None = None) -> None:
    with open_database_connection(settings) as connection:
        connection.execute("SELECT 1").fetchone()
