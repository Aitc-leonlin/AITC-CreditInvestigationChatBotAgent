import json
from datetime import date, datetime, time
from decimal import Decimal
from pathlib import Path
from typing import Any
from uuid import UUID


def normalize_database_value(value: Any) -> Any:
    """Return one DB value in the representation shared by both backends."""
    if isinstance(value, (datetime, date, time)):
        return value.isoformat()
    if isinstance(value, Decimal):
        return int(value) if value == value.to_integral_value() else float(value)
    if isinstance(value, (UUID, Path)):
        return str(value)
    return value


def to_json_compatible(value: Any) -> Any:
    """Recursively normalize native PostgreSQL values before JSON boundaries."""
    normalized = normalize_database_value(value)
    if normalized is not value:
        return normalized
    if isinstance(value, dict):
        return {str(key): to_json_compatible(item) for key, item in value.items()}
    if isinstance(value, (list, tuple, set)):
        return [to_json_compatible(item) for item in value]
    return value


def database_json_default(value: Any) -> Any:
    normalized = normalize_database_value(value)
    if normalized is value:
        raise TypeError(f"Object of type {type(value).__name__} is not JSON serializable")
    return normalized


def database_json_dumps(value: Any, **kwargs: Any) -> str:
    kwargs.setdefault("default", database_json_default)
    return json.dumps(value, **kwargs)
