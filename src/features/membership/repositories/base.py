import uuid
from typing import Any, Generic, TypeVar

from src.features.membership.core.database import get_membership_connection, membership_transaction
from src.features.membership.core.time import utc_now_iso
from src.features.membership.models.entities import MembershipModel
from src.shared.database.connection import SQLAlchemyConnectionAdapter


ModelT = TypeVar("ModelT", bound=MembershipModel)


class BaseRepository(Generic[ModelT]):
    table_name: str
    model_class: type[ModelT]

    def __init__(self, connection: SQLAlchemyConnectionAdapter | None = None):
        self.connection = connection

    def _connection(self) -> SQLAlchemyConnectionAdapter:
        return self.connection or get_membership_connection()

    def get_by_id(self, entity_id: str) -> ModelT | None:
        connection = self._connection()
        should_close = self.connection is None
        try:
            row = connection.execute(
                f"SELECT * FROM {self.table_name} WHERE id = ? AND deleted_at IS NULL",
                [entity_id],
            ).fetchone()
            return self.model_class.from_row(row) if row else None
        finally:
            if should_close:
                connection.close()

    def get_by_column(self, column: str, value: Any) -> ModelT | None:
        connection = self._connection()
        should_close = self.connection is None
        try:
            row = connection.execute(
                f"SELECT * FROM {self.table_name} WHERE {column} = ? AND deleted_at IS NULL",
                [value],
            ).fetchone()
            return self.model_class.from_row(row) if row else None
        finally:
            if should_close:
                connection.close()

    def list(self, *, limit: int = 100, offset: int = 0) -> list[ModelT]:
        normalized_limit = max(1, min(limit, 500))
        normalized_offset = max(0, offset)
        connection = self._connection()
        should_close = self.connection is None
        try:
            rows = connection.execute(
                f"""
                SELECT *
                FROM {self.table_name}
                WHERE deleted_at IS NULL
                ORDER BY created_at DESC, id DESC
                LIMIT ? OFFSET ?
                """,
                [normalized_limit, normalized_offset],
            ).fetchall()
            return [self.model_class.from_row(row) for row in rows]
        finally:
            if should_close:
                connection.close()

    def count(self) -> int:
        connection = self._connection()
        should_close = self.connection is None
        try:
            row = connection.execute(
                f"SELECT COUNT(*) AS total FROM {self.table_name} WHERE deleted_at IS NULL"
            ).fetchone()
            return int(row["total"])
        finally:
            if should_close:
                connection.close()

    def create(self, values: dict[str, Any]) -> ModelT:
        entity_id = str(values.get("id") or uuid.uuid4())
        now = utc_now_iso()
        payload = {
            **values,
            "id": entity_id,
            "created_at": values.get("created_at") or now,
            "updated_at": values.get("updated_at") or now,
            "deleted_at": values.get("deleted_at"),
        }
        columns = list(payload.keys())
        placeholders = ", ".join("?" for _ in columns)
        column_sql = ", ".join(columns)

        if self.connection is not None:
            self.connection.execute(
                f"INSERT INTO {self.table_name} ({column_sql}) VALUES ({placeholders})",
                [payload[column] for column in columns],
            )
        else:
            with membership_transaction() as connection:
                connection.execute(
                    f"INSERT INTO {self.table_name} ({column_sql}) VALUES ({placeholders})",
                    [payload[column] for column in columns],
                )

        created = self.get_by_id(entity_id)
        if created is None:
            raise RuntimeError(f"Failed to create {self.table_name} entity.")
        return created

    def update(self, entity_id: str, values: dict[str, Any]) -> ModelT | None:
        if not values:
            return self.get_by_id(entity_id)

        payload = {**values, "updated_at": utc_now_iso()}
        assignments = ", ".join(f"{column} = ?" for column in payload.keys())

        if self.connection is not None:
            cursor = self.connection.execute(
                f"""
                UPDATE {self.table_name}
                SET {assignments}
                WHERE id = ? AND deleted_at IS NULL
                """,
                [*payload.values(), entity_id],
            )
        else:
            with membership_transaction() as connection:
                cursor = connection.execute(
                    f"""
                    UPDATE {self.table_name}
                    SET {assignments}
                    WHERE id = ? AND deleted_at IS NULL
                    """,
                    [*payload.values(), entity_id],
                )
        if cursor.rowcount == 0:
            return None

        return self.get_by_id(entity_id)

    def soft_delete(self, entity_id: str) -> bool:
        now = utc_now_iso()
        if self.connection is not None:
            cursor = self.connection.execute(
                f"""
                UPDATE {self.table_name}
                SET deleted_at = ?,
                    updated_at = ?
                WHERE id = ? AND deleted_at IS NULL
                """,
                [now, now, entity_id],
            )
            return cursor.rowcount > 0

        with membership_transaction() as connection:
            cursor = connection.execute(
                f"""
                UPDATE {self.table_name}
                SET deleted_at = ?,
                    updated_at = ?
                WHERE id = ? AND deleted_at IS NULL
                """,
                [now, now, entity_id],
            )
            return cursor.rowcount > 0
