import sqlite3
from collections.abc import Iterator
from contextlib import contextmanager

from src.shared.database.db_path import resolve_sqlite_db_path


def get_membership_connection() -> sqlite3.Connection:
    connection = sqlite3.connect(resolve_sqlite_db_path())
    connection.row_factory = sqlite3.Row
    connection.execute("PRAGMA foreign_keys = ON")
    return connection


@contextmanager
def membership_transaction() -> Iterator[sqlite3.Connection]:
    connection = get_membership_connection()
    try:
        yield connection
        connection.commit()
    except Exception:
        connection.rollback()
        raise
    finally:
        connection.close()
