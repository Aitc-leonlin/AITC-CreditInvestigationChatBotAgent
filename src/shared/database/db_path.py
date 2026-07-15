import os
from pathlib import Path
from typing import Dict, List


PROJECT_ROOT = Path(__file__).resolve().parents[3]
DEFAULT_XBRL_DB_NAME = "FinancialStatementXBRL.db"
SQLITE_DB_PATH_ENV = "SQLITE_DB_PATH"


def resolve_sqlite_db_path(default_name: str = DEFAULT_XBRL_DB_NAME) -> Path:
    configured_path = os.getenv(SQLITE_DB_PATH_ENV, "").strip()
    if configured_path:
        candidate = Path(configured_path)
        if not candidate.is_absolute():
            candidate = PROJECT_ROOT / candidate
        return candidate.resolve()
    return (PROJECT_ROOT / default_name).resolve()


def build_sqlite_db_diagnostics(default_name: str = DEFAULT_XBRL_DB_NAME) -> Dict[str, object]:
    configured_path = os.getenv(SQLITE_DB_PATH_ENV, "").strip()
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
        "sqlite_env_var_value": configured_path or None,
        "project_root": str(PROJECT_ROOT),
        "cwd": os.getcwd(),
        "resolved_path": str(resolved_path),
        "parent_dir": str(parent_dir),
        "exists": exists,
        "is_file": is_file,
        "size_bytes": size_bytes,
        "parent_dir_sample": parent_listing,
    }
