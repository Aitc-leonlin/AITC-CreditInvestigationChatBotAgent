from typing import Any, Generic, TypeVar

from pydantic import BaseModel, Field


DataT = TypeVar("DataT")


class ApiError(BaseModel):
    code: str
    message: str
    details: dict[str, Any] = Field(default_factory=dict)


class ApiResponse(BaseModel, Generic[DataT]):
    success: bool = True
    data: DataT | None = None
    error: ApiError | None = None
    meta: dict[str, Any] = Field(default_factory=dict)


def ok(data: Any = None, meta: dict[str, Any] | None = None) -> dict[str, Any]:
    return {
        "success": True,
        "data": data,
        "error": None,
        "meta": meta or {},
    }
