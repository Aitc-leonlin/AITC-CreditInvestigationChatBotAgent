from typing import Any, Generic, TypeVar

from pydantic import BaseModel, Field


DataT = TypeVar("DataT")


class ErrorResponse(BaseModel):
    code: str
    message: str
    details: dict[str, Any] = Field(default_factory=dict)


class StandardResponse(BaseModel, Generic[DataT]):
    success: bool
    data: DataT | None
    error: ErrorResponse | None = None
    meta: dict[str, Any] = Field(default_factory=dict)


class InfrastructureStatus(BaseModel):
    migrationVersion: str
    migrationFile: str
    seedCounts: dict[str, int]


class ModuleMetadata(BaseModel):
    module: str
    phase: str
    capabilities: list[str]
    nextPhases: list[str]
