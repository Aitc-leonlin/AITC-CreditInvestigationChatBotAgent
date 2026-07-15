from pathlib import Path
import sqlite3
from typing import Any

from src.features.membership.core.database import membership_transaction
from src.features.membership.seeds.default_seed_data import default_seed_data
from src.shared.database.db_path import PROJECT_ROOT


MIGRATION_VERSION = "V1.1"
MIGRATION_FILES = [
    PROJECT_ROOT / "src/sql/migrations/V1.1__initialize_membership_authorization_schema.sql",
]


def apply_membership_migration() -> None:
    with membership_transaction() as connection:
        migration_table_ready = False
        for migration_file in MIGRATION_FILES:
            version = migration_file.name.split("__", 1)[0]
            if migration_table_ready and _migration_applied(connection, version):
                continue
            if version == "V1.1":
                _prepare_consolidated_baseline(connection)
            migration_sql = Path(migration_file).read_text(encoding="utf-8")
            connection.executescript(migration_sql)
            if version == "V1.1":
                migration_table_ready = True
        _ensure_membership_schema_latest(connection)
        _ensure_latest_permission_definitions(connection)


def _migration_applied(connection: Any, version: str) -> bool:
    row = connection.execute(
        """
        SELECT 1
        FROM membership_schema_migrations
        WHERE version = ?
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
    if "group_id" not in permission_columns:
        connection.execute("ALTER TABLE membership_permission ADD COLUMN group_id TEXT")


def _ensure_membership_schema_latest(connection: Any) -> None:
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
    permission_columns = {
        row["name"]
        for row in connection.execute("PRAGMA table_info(membership_permission)").fetchall()
    }
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
    if "group_id" not in permission_columns:
        connection.execute("ALTER TABLE membership_permission ADD COLUMN group_id TEXT")
    if "unit_type" not in organization_columns:
        connection.execute("ALTER TABLE membership_organization_unit ADD COLUMN unit_type TEXT NOT NULL DEFAULT 'DEPARTMENT'")
    if "company_id" not in organization_columns:
        connection.execute("ALTER TABLE membership_organization_unit ADD COLUMN company_id TEXT")
    if "manager_user_id" not in organization_columns:
        connection.execute("ALTER TABLE membership_organization_unit ADD COLUMN manager_user_id TEXT")
    if "description" not in organization_columns:
        connection.execute("ALTER TABLE membership_organization_unit ADD COLUMN description TEXT NOT NULL DEFAULT ''")

    _drop_column_if_exists(connection, "membership_permission_group", "sort_order", drop_indexes=[
        "idx_membership_permission_group_sort",
    ])
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
            WHEN code LIKE 'menu.%' THEN 'perm-group-menu'
            WHEN code LIKE 'organization-scope.%' THEN 'perm-group-org-scope'
            WHEN code LIKE 'audit.%' THEN 'perm-group-audit'
            WHEN code LIKE 'notification.%' THEN 'perm-group-notification'
            ELSE group_id
        END
        WHERE group_id IS NULL OR group_id = ''
        """
    )


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


def _ensure_latest_permission_definitions(connection: Any) -> None:
    connection.executescript(
        """
        INSERT OR IGNORE INTO membership_permission_group (
            id, code, name, description, status, created_at, updated_at, deleted_at
        )
        VALUES
            (
                'perm-group-rbac',
                'RBAC',
                '角色權限',
                '角色、權限、授權關聯管理。',
                'ACTIVE',
                CURRENT_TIMESTAMP,
                CURRENT_TIMESTAMP,
                NULL
            ),
            (
                'perm-group-org-scope',
                'ORG_SCOPE',
                '組織資料權限',
                '組織與資料可視範圍。',
                'ACTIVE',
                CURRENT_TIMESTAMP,
                CURRENT_TIMESTAMP,
                NULL
            ),
            (
                'perm-group-credit-ai',
                'CREDIT_AI',
                '授信 AI 助理',
                '授信 AI 助理、專家知識庫與資料倉儲作業權限。',
                'ACTIVE',
                CURRENT_TIMESTAMP,
                CURRENT_TIMESTAMP,
                NULL
            ),
            (
                'perm-group-report-generator',
                'REPORT_GENERATOR',
                '徵審報告產生器',
                '徵審報告產生與歷史報告查詢作業權限。',
                'ACTIVE',
                CURRENT_TIMESTAMP,
                CURRENT_TIMESTAMP,
                NULL
            );

        INSERT OR IGNORE INTO membership_permission (
            id, code, name, description, action, group_id, status,
            created_at, updated_at, deleted_at
        )
        VALUES
            ('perm-rbac-view', 'rbac.view', '角色權限', '檢視角色、權限、角色授權與使用者角色設定。', 'VIEW', 'perm-group-rbac', 'ACTIVE', CURRENT_TIMESTAMP, CURRENT_TIMESTAMP, NULL),
            ('perm-rbac-add', 'rbac.add', '角色權限', '新增角色與 RBAC 設定。', 'ADD', 'perm-group-rbac', 'ACTIVE', CURRENT_TIMESTAMP, CURRENT_TIMESTAMP, NULL),
            ('perm-rbac-edit', 'rbac.edit', '角色權限', '編輯角色、角色權限與使用者角色設定。', 'EDIT', 'perm-group-rbac', 'ACTIVE', CURRENT_TIMESTAMP, CURRENT_TIMESTAMP, NULL),
            ('perm-rbac-delete', 'rbac.delete', '角色權限', '刪除角色與 RBAC 設定。', 'DELETE', 'perm-group-rbac', 'ACTIVE', CURRENT_TIMESTAMP, CURRENT_TIMESTAMP, NULL),
            ('perm-org-scope-view', 'organization-scope.view', '組織資料權限', '檢視組織、職位、部門關聯、主管關係與資料權限規則。', 'VIEW', 'perm-group-org-scope', 'ACTIVE', CURRENT_TIMESTAMP, CURRENT_TIMESTAMP, NULL),
            ('perm-org-scope-add', 'organization-scope.add', '組織資料權限', '新增組織、職位、部門關聯、主管關係與資料權限規則。', 'ADD', 'perm-group-org-scope', 'ACTIVE', CURRENT_TIMESTAMP, CURRENT_TIMESTAMP, NULL),
            ('perm-org-scope-edit', 'organization-scope.edit', '組織資料權限', '編輯組織、職位與資料權限規則。', 'EDIT', 'perm-group-org-scope', 'ACTIVE', CURRENT_TIMESTAMP, CURRENT_TIMESTAMP, NULL),
            ('perm-org-scope-delete', 'organization-scope.delete', '組織資料權限', '刪除組織、職位、部門關聯、主管關係與資料權限規則。', 'DELETE', 'perm-group-org-scope', 'ACTIVE', CURRENT_TIMESTAMP, CURRENT_TIMESTAMP, NULL),
            ('perm-credit-ai-chat', 'credit-ai.chat', '使用授信 AI 助理', '允許使用授信 AI 助理問答作業。', 'chat', 'perm-group-credit-ai', 'ACTIVE', CURRENT_TIMESTAMP, CURRENT_TIMESTAMP, NULL),
            ('perm-credit-ai-expert-knowledge-view', 'credit-ai.expert-knowledge.view', '專家知識庫', '檢視專家知識庫', 'VIEW', 'perm-group-credit-ai', 'ACTIVE', CURRENT_TIMESTAMP, CURRENT_TIMESTAMP, NULL),
            ('perm-credit-ai-expert-knowledge-add', 'credit-ai.expert-knowledge.add', '專家知識庫', '新增專家知識庫', 'ADD', 'perm-group-credit-ai', 'ACTIVE', CURRENT_TIMESTAMP, CURRENT_TIMESTAMP, NULL),
            ('perm-credit-ai-expert-knowledge-edit', 'credit-ai.expert-knowledge.edit', '專家知識庫', '編輯專家知識庫', 'EDIT', 'perm-group-credit-ai', 'ACTIVE', CURRENT_TIMESTAMP, CURRENT_TIMESTAMP, NULL),
            ('perm-credit-ai-expert-knowledge-delete', 'credit-ai.expert-knowledge.delete', '專家知識庫', '刪除專家知識庫', 'DELETE', 'perm-group-credit-ai', 'ACTIVE', CURRENT_TIMESTAMP, CURRENT_TIMESTAMP, NULL),
            ('perm-credit-ai-warehouse-data-view', 'credit-ai.warehouse-data.view', '資料倉儲', '檢視資料倉儲', 'VIEW', 'perm-group-credit-ai', 'ACTIVE', CURRENT_TIMESTAMP, CURRENT_TIMESTAMP, NULL),
            ('perm-credit-ai-warehouse-data-add', 'credit-ai.warehouse-data.add', '資料倉儲', '新增資料倉儲', 'ADD', 'perm-group-credit-ai', 'ACTIVE', CURRENT_TIMESTAMP, CURRENT_TIMESTAMP, NULL),
            ('perm-credit-ai-warehouse-data-edit', 'credit-ai.warehouse-data.edit', '資料倉儲', '編輯資料倉儲', 'EDIT', 'perm-group-credit-ai', 'ACTIVE', CURRENT_TIMESTAMP, CURRENT_TIMESTAMP, NULL),
            ('perm-credit-ai-warehouse-data-delete', 'credit-ai.warehouse-data.delete', '資料倉儲', '刪除資料倉儲', 'DELETE', 'perm-group-credit-ai', 'ACTIVE', CURRENT_TIMESTAMP, CURRENT_TIMESTAMP, NULL),
            ('perm-report-generator-create', 'report-generator.create', '產生徵審報告', '允許使用徵審報告產生器。', 'create', 'perm-group-report-generator', 'ACTIVE', CURRENT_TIMESTAMP, CURRENT_TIMESTAMP, NULL),
            ('perm-report-generator-history', 'report-generator.history', '檢視歷史報告', '允許檢視徵審歷史報告。', 'history', 'perm-group-report-generator', 'ACTIVE', CURRENT_TIMESTAMP, CURRENT_TIMESTAMP, NULL);

        WITH old_role_permissions AS (
            SELECT DISTINCT
                role_id,
                CASE permission_id
                    WHEN 'perm-credit-ai-expert-knowledge' THEN 'expert-knowledge'
                    WHEN 'perm-credit-ai-warehouse-data' THEN 'warehouse-data'
                END AS module_key
            FROM membership_role_permission
            WHERE deleted_at IS NULL
              AND permission_id IN (
                  'perm-credit-ai-expert-knowledge',
                  'perm-credit-ai-warehouse-data'
              )
        ),
        new_permissions AS (
            SELECT 'expert-knowledge' AS module_key, 'perm-credit-ai-expert-knowledge-view' AS permission_id
            UNION ALL SELECT 'expert-knowledge', 'perm-credit-ai-expert-knowledge-add'
            UNION ALL SELECT 'expert-knowledge', 'perm-credit-ai-expert-knowledge-edit'
            UNION ALL SELECT 'expert-knowledge', 'perm-credit-ai-expert-knowledge-delete'
            UNION ALL SELECT 'warehouse-data', 'perm-credit-ai-warehouse-data-view'
            UNION ALL SELECT 'warehouse-data', 'perm-credit-ai-warehouse-data-add'
            UNION ALL SELECT 'warehouse-data', 'perm-credit-ai-warehouse-data-edit'
            UNION ALL SELECT 'warehouse-data', 'perm-credit-ai-warehouse-data-delete'
        )
        INSERT OR IGNORE INTO membership_role_permission (
            id, role_id, permission_id, effect, created_at, updated_at, deleted_at
        )
        SELECT
            'role-permission-' || old_role_permissions.role_id || '-' || new_permissions.permission_id,
            old_role_permissions.role_id,
            new_permissions.permission_id,
            'ALLOW',
            CURRENT_TIMESTAMP,
            CURRENT_TIMESTAMP,
            NULL
        FROM old_role_permissions
        JOIN new_permissions
            ON new_permissions.module_key = old_role_permissions.module_key;

        WITH old_role_permissions AS (
            SELECT DISTINCT
                role_id,
                CASE permission_id
                    WHEN 'perm-rbac-read' THEN 'rbac-read'
                    WHEN 'perm-rbac-manage' THEN 'rbac-manage'
                    WHEN 'perm-org-scope-manage' THEN 'organization-scope-manage'
                END AS module_key
            FROM membership_role_permission
            WHERE deleted_at IS NULL
              AND permission_id IN (
                  'perm-rbac-read',
                  'perm-rbac-manage',
                  'perm-org-scope-manage'
              )
        ),
        new_permissions AS (
            SELECT 'rbac-read' AS module_key, 'perm-rbac-view' AS permission_id
            UNION ALL SELECT 'rbac-manage', 'perm-rbac-view'
            UNION ALL SELECT 'rbac-manage', 'perm-rbac-add'
            UNION ALL SELECT 'rbac-manage', 'perm-rbac-edit'
            UNION ALL SELECT 'rbac-manage', 'perm-rbac-delete'
            UNION ALL SELECT 'organization-scope-manage', 'perm-org-scope-view'
            UNION ALL SELECT 'organization-scope-manage', 'perm-org-scope-add'
            UNION ALL SELECT 'organization-scope-manage', 'perm-org-scope-edit'
            UNION ALL SELECT 'organization-scope-manage', 'perm-org-scope-delete'
        )
        INSERT OR IGNORE INTO membership_role_permission (
            id, role_id, permission_id, effect, created_at, updated_at, deleted_at
        )
        SELECT
            'role-permission-' || old_role_permissions.role_id || '-' || new_permissions.permission_id,
            old_role_permissions.role_id,
            new_permissions.permission_id,
            'ALLOW',
            CURRENT_TIMESTAMP,
            CURRENT_TIMESTAMP,
            NULL
        FROM old_role_permissions
        JOIN new_permissions
            ON new_permissions.module_key = old_role_permissions.module_key;

        INSERT OR IGNORE INTO membership_role_permission (
            id, role_id, permission_id, effect, created_at, updated_at, deleted_at
        )
        SELECT
            'role-permission-super-admin-' || p.id,
            'role-super-admin',
            p.id,
            'ALLOW',
            CURRENT_TIMESTAMP,
            CURRENT_TIMESTAMP,
            NULL
        FROM membership_permission p
        WHERE p.id IN (
            'perm-rbac-view',
            'perm-rbac-add',
            'perm-rbac-edit',
            'perm-rbac-delete',
            'perm-org-scope-view',
            'perm-org-scope-add',
            'perm-org-scope-edit',
            'perm-org-scope-delete',
            'perm-credit-ai-chat',
            'perm-credit-ai-expert-knowledge-view',
            'perm-credit-ai-expert-knowledge-add',
            'perm-credit-ai-expert-knowledge-edit',
            'perm-credit-ai-expert-knowledge-delete',
            'perm-credit-ai-warehouse-data-view',
            'perm-credit-ai-warehouse-data-add',
            'perm-credit-ai-warehouse-data-edit',
            'perm-credit-ai-warehouse-data-delete',
            'perm-report-generator-create',
            'perm-report-generator-history'
        )
        AND EXISTS (
            SELECT 1
            FROM membership_role r
            WHERE r.id = 'role-super-admin'
              AND r.deleted_at IS NULL
        );

        UPDATE membership_role_permission
        SET deleted_at = CURRENT_TIMESTAMP,
            updated_at = CURRENT_TIMESTAMP
        WHERE deleted_at IS NULL
          AND permission_id IN (
              'perm-credit-ai-expert-knowledge',
              'perm-credit-ai-warehouse-data',
              'perm-rbac-read',
              'perm-rbac-manage',
              'perm-org-scope-manage'
          );

        UPDATE membership_permission
        SET status = 'INACTIVE',
            deleted_at = CURRENT_TIMESTAMP,
            updated_at = CURRENT_TIMESTAMP
        WHERE deleted_at IS NULL
          AND id IN (
              'perm-credit-ai-expert-knowledge',
              'perm-credit-ai-warehouse-data',
              'perm-rbac-read',
              'perm-rbac-manage',
              'perm-org-scope-manage'
          );

        UPDATE membership_menu_item
        SET required_permission_code = CASE required_permission_code
            WHEN 'rbac.read' THEN 'rbac.view'
            WHEN 'organization-scope.manage' THEN 'organization-scope.view'
            ELSE required_permission_code
        END,
            updated_at = CURRENT_TIMESTAMP
        WHERE required_permission_code IN ('rbac.read', 'organization-scope.manage');
        """
    )


def seed_membership_data() -> dict[str, int]:
    seed_data = default_seed_data()
    inserted_counts: dict[str, int] = {}
    with membership_transaction() as connection:
        for table_name, rows in seed_data.items():
            inserted_counts[table_name] = 0
            for row in rows:
                columns = list(row.keys())
                placeholders = ", ".join("?" for _ in columns)
                column_sql = ", ".join(columns)
                cursor = connection.execute(
                    f"INSERT OR IGNORE INTO {table_name} ({column_sql}) VALUES ({placeholders})",
                    [row[column] for column in columns],
                )
                inserted_counts[table_name] += cursor.rowcount

        permission_rows = connection.execute(
            "SELECT id FROM membership_permission WHERE deleted_at IS NULL"
        ).fetchall()
        for row in permission_rows:
            cursor = connection.execute(
                """
                INSERT OR IGNORE INTO membership_role_permission (
                    id,
                    role_id,
                    permission_id,
                    effect
                )
                VALUES (?, ?, ?, 'ALLOW')
                """,
                [f"role-permission-super-admin-{row['id']}", "role-super-admin", row["id"]],
            )
            inserted_counts["membership_role_permission"] = (
                inserted_counts.get("membership_role_permission", 0) + cursor.rowcount
            )

        menu_rows = connection.execute(
            "SELECT id FROM membership_menu_item WHERE deleted_at IS NULL"
        ).fetchall()
        for row in menu_rows:
            cursor = connection.execute(
                """
                INSERT OR IGNORE INTO membership_role_menu_permission (
                    id,
                    role_id,
                    menu_item_id,
                    can_view,
                    can_create,
                    can_update,
                    can_delete
                )
                VALUES (?, ?, ?, 1, 1, 1, 1)
                """,
                [f"role-menu-super-admin-{row['id']}", "role-super-admin", row["id"]],
            )
            inserted_counts["membership_role_menu_permission"] = (
                inserted_counts.get("membership_role_menu_permission", 0) + cursor.rowcount
            )

    return inserted_counts


def ensure_membership_infrastructure() -> dict[str, Any]:
    apply_membership_migration()
    seed_counts = seed_membership_data()
    return {
        "migrationVersion": MIGRATION_VERSION,
        "migrationFile": str(MIGRATION_FILES[-1]),
        "migrationFiles": [str(path) for path in MIGRATION_FILES],
        "seedCounts": seed_counts,
    }
