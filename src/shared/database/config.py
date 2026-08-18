import os
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Literal
from urllib.parse import unquote, urlparse


PROJECT_ROOT = Path(__file__).resolve().parents[3]
DEFAULT_SQLITE_DB_NAME = "FinancialStatementXBRL.db"

DATABASE_MODE_ENV = "DATABASE_MODE"
SQLITE_DB_PATH_ENV = "SQLITE_DB_PATH"


def _env(name: str, default: str = "") -> str:
    return os.getenv(name, default).strip()


def _positive_int(name: str, default: int) -> int:
    raw_value = _env(name)
    if not raw_value:
        return default
    try:
        value = int(raw_value)
    except ValueError as exc:
        raise RuntimeError(f"{name} must be an integer.") from exc
    if value <= 0:
        raise RuntimeError(f"{name} must be greater than zero.")
    return value


@dataclass(frozen=True)
class DatabaseSettings:
    mode: Literal["sqlite", "postgresql"]
    sqlite_path: Path | None = None
    connection_url: str = ""
    host: str = ""
    port: int = 5432
    database: str = ""
    username: str = ""
    password: str = ""
    sslmode: str = "require"
    sslrootcert: str = ""
    connect_timeout_seconds: int = 10
    application_name: str = "aitc-credit-investigation-backend"
    schema: str = "public"

    @classmethod
    def from_env(cls) -> "DatabaseSettings":
        raw_mode = _env(DATABASE_MODE_ENV, "sqlite").lower()
        mode_aliases = {
            "sqlite": "sqlite",
            "local": "sqlite",
            "postgres": "postgresql",
            "postgresql": "postgresql",
            "external": "postgresql",
        }
        mode = mode_aliases.get(raw_mode)
        if mode is None:
            raise RuntimeError(
                f"{DATABASE_MODE_ENV} must be sqlite or postgresql; received {raw_mode!r}."
            )

        if mode == "sqlite":
            configured_path = _env(SQLITE_DB_PATH_ENV, DEFAULT_SQLITE_DB_NAME)
            sqlite_path = Path(configured_path)
            if not sqlite_path.is_absolute():
                sqlite_path = PROJECT_ROOT / sqlite_path
            return cls(mode="sqlite", sqlite_path=sqlite_path.resolve())

        connection_url = _env("DATABASE_URL")
        parsed_url = urlparse(connection_url) if connection_url else None
        if parsed_url and parsed_url.scheme not in {"postgres", "postgresql"}:
            raise RuntimeError("DATABASE_URL must use the postgres or postgresql scheme.")

        values = {
            "host": _env("DATABASE_HOST"),
            "database": _env("DATABASE_NAME"),
            "username": _env("DATABASE_USER"),
            "password": _env("DATABASE_PASSWORD"),
        }
        missing = [name for name, value in values.items() if not value]
        if missing and not connection_url:
            env_names = {
                "host": "DATABASE_HOST",
                "database": "DATABASE_NAME",
                "username": "DATABASE_USER",
                "password": "DATABASE_PASSWORD",
            }
            raise RuntimeError(
                "PostgreSQL configuration is incomplete. Missing: "
                + ", ".join(env_names[name] for name in missing)
            )

        schema = _env("DATABASE_SCHEMA", "public")
        if not re.fullmatch(r"[A-Za-z_][A-Za-z0-9_]*", schema):
            raise RuntimeError("DATABASE_SCHEMA must be a valid PostgreSQL identifier.")

        sslmode = _env("DATABASE_SSLMODE", "require").lower()
        allowed_ssl_modes = {
            "disable",
            "allow",
            "prefer",
            "require",
            "verify-ca",
            "verify-full",
        }
        if sslmode not in allowed_ssl_modes:
            raise RuntimeError(
                "DATABASE_SSLMODE must be one of: " + ", ".join(sorted(allowed_ssl_modes))
            )

        return cls(
            mode="postgresql",
            connection_url=connection_url,
            host=values["host"] or (parsed_url.hostname if parsed_url else ""),
            port=_positive_int(
                "DATABASE_PORT",
                parsed_url.port if parsed_url and parsed_url.port else 5432,
            ),
            database=values["database"] or (
                unquote(parsed_url.path.lstrip("/")) if parsed_url else ""
            ),
            username=values["username"] or (
                unquote(parsed_url.username or "") if parsed_url else ""
            ),
            password=values["password"] or (
                unquote(parsed_url.password or "") if parsed_url else ""
            ),
            sslmode=sslmode,
            sslrootcert=_env("DATABASE_SSLROOTCERT"),
            connect_timeout_seconds=_positive_int("DATABASE_CONNECT_TIMEOUT_SECONDS", 10),
            application_name=_env(
                "DATABASE_APPLICATION_NAME", "aitc-credit-investigation-backend"
            ),
            schema=schema,
        )

    def diagnostics(self) -> dict[str, object]:
        if self.mode == "sqlite":
            assert self.sqlite_path is not None
            exists = self.sqlite_path.exists()
            return {
                "mode": self.mode,
                "path": str(self.sqlite_path),
                "exists": exists,
                "isFile": self.sqlite_path.is_file() if exists else False,
                "sizeBytes": self.sqlite_path.stat().st_size if exists and self.sqlite_path.is_file() else 0,
            }
        return {
            "mode": self.mode,
            "host": self.host,
            "port": self.port,
            "database": self.database,
            "username": self.username,
            "sslmode": self.sslmode,
            "sslRootCertificateConfigured": bool(self.sslrootcert),
            "connectTimeoutSeconds": self.connect_timeout_seconds,
            "applicationName": self.application_name,
            "schema": self.schema,
            "passwordConfigured": bool(self.password),
            "connectionUrlConfigured": bool(self.connection_url),
        }


def get_database_settings() -> DatabaseSettings:
    return DatabaseSettings.from_env()
