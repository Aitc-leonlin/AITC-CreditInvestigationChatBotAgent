from collections.abc import Iterator
from contextlib import contextmanager
from typing import Any

from src.shared.database.connection import open_database_connection


def get_membership_connection() -> Any:
    return open_database_connection()


@contextmanager
def membership_transaction() -> Iterator[Any]:
    connection = get_membership_connection()
    try:
        yield connection
        connection.commit()
    except Exception:
        connection.rollback()
        raise
    finally:
        connection.close()
