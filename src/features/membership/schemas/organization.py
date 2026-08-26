import re
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator


Status = Literal["ACTIVE", "INACTIVE"]
OrganizationUnitType = Literal["COMPANY", "DEPARTMENT", "TEAM"]


def normalize_code(value: str) -> str:
    normalized = value.strip().upper()
    if not re.fullmatch(r"[A-Z]{2}", normalized):
        raise ValueError("組織代碼必須是兩碼英文字母。")
    return normalized


class OrganizationUnitCommand(BaseModel):
    model_config = ConfigDict(str_strip_whitespace=True, extra="forbid")

    code: str = Field(min_length=2, max_length=2)
    name: str = Field(min_length=1, max_length=120)
    unitType: OrganizationUnitType = "DEPARTMENT"
    parentId: str | None = None
    companyId: str | None = None
    managerUserId: str | None = None
    description: str = ""
    status: Status = "ACTIVE"

    @field_validator("code")
    @classmethod
    def normalize_unit_code(cls, value: str) -> str:
        return normalize_code(value)


class PositionCommand(BaseModel):
    model_config = ConfigDict(str_strip_whitespace=True, extra="forbid")

    name: str = Field(min_length=1, max_length=120)
    description: str = ""
    level: int = 0
    status: Status = "ACTIVE"


class OrganizationUnitResponse(BaseModel):
    id: str
    code: str
    name: str
    unitType: str
    parentId: str | None
    companyId: str | None
    managerUserId: str | None
    managerDisplayName: str | None
    description: str
    path: str
    level: int
    status: str
    children: list["OrganizationUnitResponse"] = Field(default_factory=list)
    createdAt: str
    updatedAt: str


class OrganizationDeleteResponse(BaseModel):
    deleted: bool
    deletedCount: int
    detachedUserCount: int


class PositionResponse(BaseModel):
    id: str
    name: str
    description: str
    level: int
    status: str
    createdAt: str
    updatedAt: str
