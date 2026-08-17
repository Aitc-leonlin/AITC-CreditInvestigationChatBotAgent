import os
from pathlib import Path
from typing import Dict, List

from src.shared.database.config import (
    DATABASE_MODE_ENV,
    PROJECT_ROOT,
    SQLITE_DB_PATH_ENV,
    get_database_settings,
)

DEFAULT_XBRL_DB_NAME = "FinancialStatementXBRL.db"


def resolve_sqlite_db_path(default_name: str = DEFAULT_XBRL_DB_NAME) -> Path:
    settings = get_database_settings()
    if settings.mode != "sqlite":
        raise RuntimeError(
            f"resolve_sqlite_db_path() is unavailable when {DATABASE_MODE_ENV}=postgresql. "
            "This caller still needs to be migrated to the shared database connection layer."
        )
    if os.getenv(SQLITE_DB_PATH_ENV, "").strip() and settings.sqlite_path is not None:
        return settings.sqlite_path
    return (PROJECT_ROOT / default_name).resolve()


def build_sqlite_db_diagnostics(default_name: str = DEFAULT_XBRL_DB_NAME) -> Dict[str, object]:
    settings = get_database_settings()
    if settings.mode != "sqlite":
        return settings.diagnostics()
    resolved_path = resolve_sqlite_db_path(default_name)
    parent_dir = resolved_path.parent
    exists = resolved_path.exists()
    is_file = resolved_path.is_file()
    size_bytes = resolved_path.stat().st_size if exists and is_file else 0
    parent_listing: List[str] = []
    if parent_dir.exists() and parent_dir.is_dir():
        parent_listing = sorted(path.name for path in parent_dir.iterdir())[:30]

    return {
        "sqlite_env_var_name": SQLITE_DB_PATH_ENV,
        "database_mode_env_var_name": DATABASE_MODE_ENV,
        "database_mode": settings.mode,
        "sqlite_env_var_value": str(settings.sqlite_path) if settings.sqlite_path else None,
        "project_root": str(PROJECT_ROOT),
        "cwd": os.getcwd(),
        "resolved_path": str(resolved_path),
        "parent_dir": str(parent_dir),
        "exists": exists,
        "is_file": is_file,
        "size_bytes": size_bytes,
        "parent_dir_sample": parent_listing,
    }


def build_database_diagnostics(default_name: str = DEFAULT_XBRL_DB_NAME) -> Dict[str, object]:
    return build_sqlite_db_diagnostics(default_name)
