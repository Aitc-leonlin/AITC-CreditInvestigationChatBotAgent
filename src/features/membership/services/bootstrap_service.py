from pathlib import Path
import sqlite3
from typing import Any

from src.features.membership.core.database import membership_transaction
from src.features.membership.core.database import get_membership_connection
from src.features.membership.core.permission_registry import (
    LEGACY_PERMISSION_ID_TO_CODE,
    PERMISSION_CODE_TO_LEGACY_ID,
    all_permission_codes,
)
from src.features.membership.seeds.default_seed_data import DEFAULT_USER_ROLE_ID, default_seed_data
from src.shared.database.config import get_database_settings
from src.shared.database.connection import table_exists
from src.shared.database.db_path import PROJECT_ROOT


MIGRATION_VERSION = "V1.7"
MEMBERSHIP_MIGRATION_NAMES = [
    "V1.1__initialize_membership_authorization_schema.sql",
    "V1.2__add_audit_log_retention.sql",
    "V1.3__add_chat_conversation_history.sql",
    "V1.4__normalize_chat_message_references.sql",
    "V1.5__add_membership_groups.sql",
    "V1.6__remove_data_scope_and_masking.sql",
    "V1.7__repair_discontinued_data_scope_tables.sql",
]
XBRL_MIGRATION_NAMES = [
    "V1.0__initialize_financial_statement_xbrl_schema.sql",
    "V2.0__preserve_taxonomy_arc_rows.sql",
]


def apply_xbrl_migration() -> None:
    settings = get_database_settings()
    migration_files = [
        PROJECT_ROOT / "src/sql/migrations" / settings.mode / name
        for name in XBRL_MIGRATION_NAMES
    ]
    missing_files = [str(path) for path in migration_files if not path.is_file()]
    if missing_files:
        raise RuntimeError(
            f"Missing {settings.mode} XBRL migration files: " + ", ".join(missing_files)
        )
    with membership_transaction() as connection:
        migration_table_ready = table_exists(connection, "schema_migrations")
        for migration_file in migration_files:
            version = migration_file.name.split("__", 1)[0]
            if migration_table_ready:
                applied = connection.execute(
                    "SELECT 1 FROM schema_migrations WHERE version = ? LIMIT 1",
                    [version],
                ).fetchone()
                if applied:
                    continue
            migration_sql = migration_file.read_text(encoding="utf-8")
            if settings.mode == "sqlite":
                connection.executescript(migration_sql)
            else:
                connection.execute(migration_sql, prepare=False)
            migration_table_ready = True


def membership_migration_files(database_mode: str | None = None) -> list[Path]:
    mode = database_mode or get_database_settings().mode
    migration_directory = PROJECT_ROOT / "src/sql/migrations" / mode
    files = [migration_directory / name for name in MEMBERSHIP_MIGRATION_NAMES]
    missing_files = [str(path) for path in files if not path.is_file()]
    if missing_files:
        raise RuntimeError(
            f"Missing {mode} membership migration files: " + ", ".join(missing_files)
        )
    return files


def apply_membership_migration() -> None:
    apply_xbrl_migration()
    settings = get_database_settings()
    migration_files = membership_migration_files(settings.mode)
    with membership_transaction() as connection:
        # V1.1 creates this table on a new database. On an existing database,
        # completed migrations must be skipped; rerunning V1.1 used to recreate
        # the discontinued tables removed by V1.6.
        migration_table_ready = table_exists(connection, "membership_schema_migrations")
        for migration_file in migration_files:
            version = migration_file.name.split("__", 1)[0]
            if migration_table_ready and _migration_applied(connection, version, settings.mode):
                continue
            if settings.mode == "sqlite" and version == "V1.1":
                _prepare_consolidated_baseline(connection)
            migration_sql = Path(migration_file).read_text(encoding="utf-8")
            if settings.mode == "sqlite":
                connection.executescript(migration_sql)
            else:
                connection.execute(migration_sql, prepare=False)
            migration_table_ready = True
        if settings.mode == "postgresql":
            return
        _ensure_membership_schema_latest(connection)
        _ensure_permission_code_authorization(connection)
        _drop_permission_definition_tables(connection)


def _migration_applied(connection: Any, version: str, database_mode: str) -> bool:
    placeholder = "?" if database_mode == "sqlite" else "%s"
    row = connection.execute(
        f"""
        SELECT 1
        FROM membership_schema_migrations
        WHERE version = {placeholder}
        LIMIT 1
        """,
        [version],
    ).fetchone()
    return row is not None


def _prepare_consolidated_baseline(connection: Any) -> None:
    tables = {
        row["name"]
        for row in connection.execute(
            "SELECT name FROM sqlite_master WHERE type = 'table'"
        ).fetchall()
    }
    if "membership_permission" not in tables:
        return
    permission_columns = {
        row["name"]
        for row in connection.execute("PRAGMA table_info(membership_permission)").fetchall()
    }
    role_permission_columns = {
        row["name"]
        for row in connection.execute("PRAGMA table_info(membership_role_permission)").fetchall()
    }
    permission_group_columns = {
        row["name"]
        for row in connection.execute("PRAGMA table_info(membership_permission_group)").fetchall()
    }
    if "group_id" not in permission_columns:
        connection.execute("ALTER TABLE membership_permission ADD COLUMN group_id TEXT")
    if "permission_code" not in role_permission_columns:
        connection.execute("ALTER TABLE membership_role_permission ADD COLUMN permission_code TEXT NOT NULL DEFAULT ''")
    if "module_name" not in permission_group_columns:
        connection.execute("ALTER TABLE membership_permission_group ADD COLUMN module_name TEXT NOT NULL DEFAULT ''")


def _ensure_membership_schema_latest(connection: Any) -> None:
    tables = {
        row["name"]
        for row in connection.execute(
            "SELECT name FROM sqlite_master WHERE type = 'table'"
        ).fetchall()
    }
    user_columns = {
        row["name"]
        for row in connection.execute("PRAGMA table_info(membership_user)").fetchall()
    }
    credential_columns = {
        row["name"]
        for row in connection.execute("PRAGMA table_info(membership_user_credential)").fetchall()
    }
    refresh_columns = {
        row["name"]
        for row in connection.execute("PRAGMA table_info(membership_refresh_token)").fetchall()
    }
    permission_columns = _table_columns(connection, "membership_permission")
    organization_columns = {
        row["name"]
        for row in connection.execute("PRAGMA table_info(membership_organization_unit)").fetchall()
    }

    if "email_verified_at" not in user_columns:
        connection.execute("ALTER TABLE membership_user ADD COLUMN email_verified_at TEXT")
    if "last_login_ip" not in user_columns:
        connection.execute("ALTER TABLE membership_user ADD COLUMN last_login_ip TEXT NOT NULL DEFAULT ''")
    if "last_failed_login_at" not in credential_columns:
        connection.execute("ALTER TABLE membership_user_credential ADD COLUMN last_failed_login_at TEXT")
    if "last_failed_login_ip" not in credential_columns:
        connection.execute("ALTER TABLE membership_user_credential ADD COLUMN last_failed_login_ip TEXT NOT NULL DEFAULT ''")
    if "session_id" not in refresh_columns:
        connection.execute("ALTER TABLE membership_refresh_token ADD COLUMN session_id TEXT")
    if "membership_permission" in tables and "group_id" not in permission_columns:
        connection.execute("ALTER TABLE membership_permission ADD COLUMN group_id TEXT")
    if "unit_type" not in organization_columns:
        connection.execute("ALTER TABLE membership_organization_unit ADD COLUMN unit_type TEXT NOT NULL DEFAULT 'DEPARTMENT'")
    if "company_id" not in organization_columns:
        connection.execute("ALTER TABLE membership_organization_unit ADD COLUMN company_id TEXT")
    if "manager_user_id" not in organization_columns:
        connection.execute("ALTER TABLE membership_organization_unit ADD COLUMN manager_user_id TEXT")
    if "description" not in organization_columns:
        connection.execute("ALTER TABLE membership_organization_unit ADD COLUMN description TEXT NOT NULL DEFAULT ''")
    connection.execute("DROP INDEX IF EXISTS idx_membership_menu_parent")
    connection.execute("DROP TABLE IF EXISTS membership_menu_item")

    if "membership_permission_group" in tables:
        _drop_column_if_exists(connection, "membership_permission_group", "sort_order", drop_indexes=[
            "idx_membership_permission_group_sort",
        ])
    if "membership_permission" in tables:
        _drop_column_if_exists(connection, "membership_permission", "resource")
        _drop_column_if_exists(connection, "membership_permission", "scope")
        connection.execute(
            """
            CREATE INDEX IF NOT EXISTS idx_membership_permission_group
            ON membership_permission(group_id)
            WHERE deleted_at IS NULL
            """
        )
        connection.execute(
            """
            UPDATE membership_permission
            SET group_id = CASE
                WHEN code LIKE 'membership.%' THEN 'perm-group-membership'
                WHEN code LIKE 'rbac.%' THEN 'perm-group-rbac'
                WHEN code LIKE 'organization-scope.%' THEN 'perm-group-org-scope'
                WHEN code LIKE 'audit.%' THEN 'perm-group-audit'
                WHEN code LIKE 'notification.%' THEN 'perm-group-notification'
                ELSE group_id
            END
            WHERE group_id IS NULL OR group_id = ''
            """
        )
    if "membership_permission_group" in tables:
        connection.execute(
            """
            UPDATE membership_permission_group
            SET module_name = CASE
                WHEN code IN ('CREDIT_AI') THEN '授信 AI 助理'
                WHEN code IN ('REPORT_GENERATOR') THEN '徵審報告產生器'
                WHEN code IN ('MEMBERSHIP', 'RBAC', 'ORG_SCOPE', 'AUDIT', 'NOTIFICATION') THEN '會員權限管理'
                ELSE module_name
            END
            WHERE module_name IS NULL OR module_name = ''
            """
        )
    _remove_menu_management_authorization(connection)


def _drop_column_if_exists(
    connection: Any,
    table_name: str,
    column_name: str,
    *,
    drop_indexes: list[str] | None = None,
) -> None:
    columns = {
        row["name"]
        for row in connection.execute(f"PRAGMA table_info({table_name})").fetchall()
    }
    if column_name not in columns:
        return
    for index_name in drop_indexes or []:
        connection.execute(f"DROP INDEX IF EXISTS {index_name}")
    try:
        connection.execute(f"ALTER TABLE {table_name} DROP COLUMN {column_name}")
    except sqlite3.OperationalError as exc:
        raise RuntimeError(
            f"Unable to consolidate {table_name}.{column_name}; SQLite DROP COLUMN failed."
        ) from exc


def _remove_menu_management_authorization(connection: Any) -> None:
    connection.execute("DROP TABLE IF EXISTS membership_role_menu_permission")
    role_permission_columns = _table_columns(connection, "membership_role_permission")
    has_permission_table = bool(_table_columns(connection, "membership_permission"))
    has_permission_group_table = bool(_table_columns(connection, "membership_permission_group"))
    if "permission_id" in role_permission_columns:
        connection.execute(
            """
            UPDATE membership_role_permission
            SET deleted_at = COALESCE(deleted_at, CURRENT_TIMESTAMP),
                updated_at = CURRENT_TIMESTAMP
            WHERE permission_id IN ('perm-menu-read', 'perm-menu-manage')
              AND deleted_at IS NULL
            """
        )
    if "permission_code" in role_permission_columns:
        connection.execute(
            """
            UPDATE membership_role_permission
            SET deleted_at = COALESCE(deleted_at, CURRENT_TIMESTAMP),
                updated_at = CURRENT_TIMESTAMP
            WHERE permission_code IN ('menu.read', 'menu.manage')
              AND deleted_at IS NULL
            """
        )
    if has_permission_table:
        connection.execute(
            """
            UPDATE membership_permission
            SET deleted_at = COALESCE(deleted_at, CURRENT_TIMESTAMP),
                updated_at = CURRENT_TIMESTAMP,
                status = 'INACTIVE'
            WHERE id IN ('perm-menu-read', 'perm-menu-manage')
               OR code IN ('menu.read', 'menu.manage')
            """
        )
    if has_permission_group_table:
        connection.execute(
            """
            UPDATE membership_permission_group
            SET deleted_at = COALESCE(deleted_at, CURRENT_TIMESTAMP),
                updated_at = CURRENT_TIMESTAMP,
                status = 'INACTIVE'
            WHERE id = 'perm-group-menu'
               OR code = 'MENU'
            """
        )


def _drop_permission_definition_tables(connection: Any) -> None:
    connection.execute("DROP INDEX IF EXISTS idx_membership_permission_group")
    connection.execute("DROP TABLE IF EXISTS membership_permission")
    connection.execute("DROP TABLE IF EXISTS membership_permission_group")


def _table_columns(connection: Any, table_name: str) -> set[str]:
    row = connection.execute(
        "SELECT 1 FROM sqlite_master WHERE type = 'table' AND name = ?",
        [table_name],
    ).fetchone()
    if row is None:
        return set()
    return {
        row["name"]
        for row in connection.execute(f"PRAGMA table_info({table_name})").fetchall()
    }


def _ensure_permission_code_authorization(connection: Any) -> None:
    role_permission_columns = _table_columns(connection, "membership_role_permission")
    if "permission_code" not in role_permission_columns:
        connection.execute("ALTER TABLE membership_role_permission ADD COLUMN permission_code TEXT NOT NULL DEFAULT ''")
        role_permission_columns.add("permission_code")

    if "permission_id" in role_permission_columns and _table_columns(connection, "membership_permission"):
        connection.execute(
            """
            UPDATE membership_role_permission
            SET permission_code = COALESCE((
                    SELECT p.code
                    FROM membership_permission p
                    WHERE p.id = membership_role_permission.permission_id
                    LIMIT 1
                ), permission_code)
            WHERE permission_code = ''
              AND permission_id IS NOT NULL
              AND permission_id != ''
            """
        )

    for legacy_permission_id, permission_code in LEGACY_PERMISSION_ID_TO_CODE.items():
        if "permission_id" in role_permission_columns:
            connection.execute(
                """
                UPDATE membership_role_permission
                SET permission_code = ?
                WHERE permission_code = ''
                  AND permission_id = ?
                """,
                [permission_code, legacy_permission_id],
            )

    legacy_expansions = {
        "perm-credit-ai-expert-knowledge": [
            "credit-ai.expert-knowledge.view",
            "credit-ai.expert-knowledge.add",
            "credit-ai.expert-knowledge.edit",
            "credit-ai.expert-knowledge.delete",
        ],
        "perm-credit-ai-warehouse-data": [
            "credit-ai.warehouse-data.view",
            "credit-ai.warehouse-data.add",
            "credit-ai.warehouse-data.edit",
            "credit-ai.warehouse-data.delete",
        ],
        "perm-rbac-manage": ["rbac.view", "rbac.add", "rbac.edit", "rbac.delete"],
        "perm-org-scope-manage": [
            "organization-scope.view",
            "organization-scope.add",
            "organization-scope.edit",
            "organization-scope.delete",
        ],
    }
    if "permission_id" in role_permission_columns:
        for legacy_permission_id, permission_codes in legacy_expansions.items():
            role_rows = connection.execute(
                """
                SELECT DISTINCT role_id
                FROM membership_role_permission
                WHERE permission_id = ?
                  AND deleted_at IS NULL
                """,
                [legacy_permission_id],
            ).fetchall()
            for role_row in role_rows:
                for permission_code in permission_codes:
                    _insert_role_permission_code(connection, role_row["role_id"], permission_code)

    legacy_code_replacements = {
        "audit.read": "audit.view",
        "notification.manage": "notification.view",
    }
    for legacy_code, new_code in legacy_code_replacements.items():
        role_rows = connection.execute(
            """
            SELECT DISTINCT role_id
            FROM membership_role_permission
            WHERE permission_code = ?
              AND deleted_at IS NULL
            """,
            [legacy_code],
        ).fetchall()
        for role_row in role_rows:
            _insert_role_permission_code(connection, role_row["role_id"], new_code)

    connection.execute(
        """
        UPDATE membership_role_permission
        SET deleted_at = COALESCE(deleted_at, CURRENT_TIMESTAMP),
            updated_at = CURRENT_TIMESTAMP
        WHERE permission_code IN ('audit.read', 'notification.manage')
          AND deleted_at IS NULL
        """
    )

    connection.execute(
        """
        UPDATE membership_role_permission
        SET deleted_at = COALESCE(deleted_at, CURRENT_TIMESTAMP),
            updated_at = CURRENT_TIMESTAMP
        WHERE permission_code IN ('menu.read', 'menu.manage')
          AND deleted_at IS NULL
        """
    )

    if "permission_id" in role_permission_columns:
        _rebuild_role_permission_code_table(connection)

    if connection.execute(
        "SELECT 1 FROM membership_role WHERE id = 'role-super-admin' AND deleted_at IS NULL"
    ).fetchone():
        for permission_code in all_permission_codes():
            _insert_role_permission_code(connection, "role-super-admin", permission_code)

    _remove_menu_management_authorization(connection)


def _rebuild_role_permission_code_table(connection: Any) -> None:
    connection.execute(
        """
        CREATE TABLE IF NOT EXISTS membership_role_permission_code_only (
            id TEXT PRIMARY KEY,
            role_id TEXT NOT NULL,
            permission_code TEXT NOT NULL DEFAULT '',
            effect TEXT NOT NULL DEFAULT 'ALLOW',
            created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
            updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
            deleted_at TEXT,

            UNIQUE (role_id, permission_code),
            FOREIGN KEY (role_id) REFERENCES membership_role(id)
        )
        """
    )
    connection.execute(
        """
        INSERT OR REPLACE INTO membership_role_permission_code_only (
            id, role_id, permission_code, effect, created_at, updated_at, deleted_at
        )
        SELECT id, role_id, permission_code, effect, created_at, updated_at, deleted_at
        FROM membership_role_permission
        WHERE permission_code IS NOT NULL
          AND permission_code != ''
        """
    )
    connection.execute("DROP TABLE membership_role_permission")
    connection.execute("ALTER TABLE membership_role_permission_code_only RENAME TO membership_role_permission")
    connection.execute(
        """
        CREATE INDEX IF NOT EXISTS idx_membership_role_permission_role
        ON membership_role_permission(role_id)
        WHERE deleted_at IS NULL
        """
    )
    connection.execute(
        """
        CREATE INDEX IF NOT EXISTS idx_membership_role_permission_permission
        ON membership_role_permission(permission_code)
        WHERE deleted_at IS NULL
        """
    )


def _insert_role_permission_code(connection: Any, role_id: str, permission_code: str) -> int:
    if get_database_settings().mode == "postgresql":
        cursor = connection.execute(
            """
            INSERT INTO membership_role_permission (
                id, role_id, permission_code, effect, created_at, updated_at, deleted_at
            )
            VALUES (%s, %s, %s, 'ALLOW', CURRENT_TIMESTAMP::TEXT, CURRENT_TIMESTAMP::TEXT, NULL)
            ON CONFLICT (role_id, permission_code) DO UPDATE
            SET effect = EXCLUDED.effect,
                updated_at = CURRENT_TIMESTAMP::TEXT,
                deleted_at = NULL
            """,
            [f"role-permission-{role_id}-{permission_code}", role_id, permission_code],
        )
        return max(cursor.rowcount, 0)

    now = "CURRENT_TIMESTAMP"
    columns = _table_columns(connection, "membership_role_permission")
    payload: dict[str, Any] = {
        "id": f"role-permission-{role_id}-{permission_code}",
        "role_id": role_id,
        "permission_code": permission_code,
        "effect": "ALLOW",
        "deleted_at": None,
    }
    if "permission_id" in columns:
        payload["permission_id"] = PERMISSION_CODE_TO_LEGACY_ID.get(permission_code, permission_code)
    if "created_at" in columns:
        payload["created_at"] = now
    if "updated_at" in columns:
        payload["updated_at"] = now
    column_names = list(payload.keys())
    values_sql = ", ".join("CURRENT_TIMESTAMP" if payload[column] == now else "?" for column in column_names)
    values = [payload[column] for column in column_names if payload[column] != now]
    cursor = connection.execute(
        f"INSERT OR REPLACE INTO membership_role_permission ({', '.join(column_names)}) VALUES ({values_sql})",
        values,
    )
    return max(cursor.rowcount, 0)


def seed_membership_data() -> dict[str, int]:
    database_mode = get_database_settings().mode
    seed_data = default_seed_data()
    inserted_counts: dict[str, int] = {}
    with membership_transaction() as connection:
        for table_name, rows in seed_data.items():
            inserted_counts[table_name] = 0
            for row in rows:
                columns = list(row.keys())
                placeholder = "?" if database_mode == "sqlite" else "%s"
                placeholders = ", ".join(placeholder for _ in columns)
                column_sql = ", ".join(columns)
                insert_prefix = "INSERT OR IGNORE" if database_mode == "sqlite" else "INSERT"
                conflict_clause = "" if database_mode == "sqlite" else " ON CONFLICT DO NOTHING"
                cursor = connection.execute(
                    f"{insert_prefix} INTO {table_name} ({column_sql}) VALUES ({placeholders}){conflict_clause}",
                    [row[column] for column in columns],
                )
                inserted_counts[table_name] += max(cursor.rowcount, 0)

        for permission_code in all_permission_codes():
            inserted_counts["membership_role_permission"] = (
                inserted_counts.get("membership_role_permission", 0)
                + _insert_role_permission_code(connection, "role-super-admin", permission_code)
            )
        default_user_permissions = [
            permission_code
            for permission_code in all_permission_codes()
            if permission_code.startswith("credit-ai.")
            or permission_code.startswith("report-generator.")
        ]
        for permission_code in default_user_permissions:
            inserted_counts["membership_role_permission"] = (
                inserted_counts.get("membership_role_permission", 0)
                + _insert_role_permission_code(connection, DEFAULT_USER_ROLE_ID, permission_code)
            )

    return inserted_counts


def reset_membership_seed_data() -> dict[str, Any]:
    apply_membership_migration()
    database_mode = get_database_settings().mode
    cleared_tables: list[str] = []
    with get_membership_connection() as connection:
        if database_mode == "sqlite":
            table_query = """
                SELECT name
                FROM sqlite_master
                WHERE type = 'table'
                  AND (
                      name LIKE 'membership_%'
                      OR name IN (
                          'chat_conversation',
                          'chat_conversation_message',
                          'chat_message_expert_knowledge',
                          'chat_message_external_data'
                      )
                  )
                  AND name != 'membership_schema_migrations'
                ORDER BY name
                """
        else:
            table_query = """
                SELECT tablename AS name
                FROM pg_catalog.pg_tables
                WHERE schemaname = current_schema()
                  AND (
                      tablename LIKE 'membership_%'
                      OR tablename IN (
                          'chat_conversation',
                          'chat_conversation_message',
                          'chat_message_expert_knowledge',
                          'chat_message_external_data'
                      )
                  )
                  AND tablename != 'membership_schema_migrations'
                ORDER BY tablename
                """
        tables = [row["name"] for row in connection.execute(table_query).fetchall()]
        try:
            if database_mode == "sqlite":
                connection.execute("PRAGMA foreign_keys = OFF")
                for table_name in tables:
                    connection.execute(f"DELETE FROM {table_name}")
                    cleared_tables.append(table_name)
            elif tables:
                quoted_tables = ", ".join(f'"{table_name}"' for table_name in tables)
                connection.execute(f"TRUNCATE TABLE {quoted_tables} RESTART IDENTITY CASCADE")
                cleared_tables.extend(tables)
            connection.commit()
        except Exception:
            connection.rollback()
            raise
        finally:
            if database_mode == "sqlite":
                connection.execute("PRAGMA foreign_keys = ON")

    seed_counts = seed_membership_data()
    return {
        "clearedTables": cleared_tables,
        "clearedTableCount": len(cleared_tables),
        "seedCounts": seed_counts,
    }


def ensure_membership_infrastructure() -> dict[str, Any]:
    apply_membership_migration()
    seed_counts = seed_membership_data()
    migration_files = membership_migration_files()
    return {
        "migrationVersion": MIGRATION_VERSION,
        "migrationFile": str(migration_files[-1]),
        "migrationFiles": [str(path) for path in migration_files],
        "seedCounts": seed_counts,
    }
