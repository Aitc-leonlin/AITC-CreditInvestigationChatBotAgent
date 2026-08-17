from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator


Status = Literal["ACTIVE", "INACTIVE"]
OrganizationUnitType = Literal["COMPANY", "DEPARTMENT", "TEAM"]


def normalize_code(value: str) -> str:
    return value.strip().upper().replace(" ", "_")


class OrganizationUnitCommand(BaseModel):
    model_config = ConfigDict(str_strip_whitespace=True, extra="forbid")

    code: str = Field(min_length=2, max_length=100)
    name: str = Field(min_length=1, max_length=120)
    unitType: OrganizationUnitType = "DEPARTMENT"
    parentId: str | None = None
    companyId: str | None = None
    managerUserId: str | None = None
    description: str = ""
    sortOrder: int = 0
    status: Status = "ACTIVE"

    @field_validator("code")
    @classmethod
    def normalize_unit_code(cls, value: str) -> str:
        return normalize_code(value)


class PositionCommand(BaseModel):
    model_config = ConfigDict(str_strip_whitespace=True, extra="forbid")

    code: str = Field(min_length=2, max_length=100)
    name: str = Field(min_length=1, max_length=120)
    description: str = ""
    level: int = 0
    sortOrder: int = 0
    status: Status = "ACTIVE"

    @field_validator("code")
    @classmethod
    def normalize_position_code(cls, value: str) -> str:
        return normalize_code(value)


class UserDepartmentMappingCommand(BaseModel):
    model_config = ConfigDict(str_strip_whitespace=True, extra="forbid")

    userId: str
    organizationId: str
    positionId: str | None = None
    isPrimary: bool = False
    effectiveFrom: str | None = None
    effectiveTo: str | None = None


class ManagerRelationCommand(BaseModel):
    model_config = ConfigDict(str_strip_whitespace=True, extra="forbid")

    managerUserId: str
    employeeUserId: str
    organizationId: str | None = None
    relationType: str = "DIRECT"
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
    sortOrder: int
    status: str
    children: list["OrganizationUnitResponse"] = Field(default_factory=list)
    createdAt: str
    updatedAt: str


class PositionResponse(BaseModel):
    id: str
    code: str
    name: str
    description: str
    level: int
    sortOrder: int
    status: str
    userCount: int
    createdAt: str
    updatedAt: str


class UserDepartmentMappingResponse(BaseModel):
    id: str
    userId: str
    username: str | None
    displayName: str | None
    organizationId: str
    organizationName: str | None
    positionId: str | None
    positionName: str | None
    isPrimary: bool
    effectiveFrom: str | None
    effectiveTo: str | None
    createdAt: str
    updatedAt: str


class ManagerRelationResponse(BaseModel):
    id: str
    managerUserId: str
    managerDisplayName: str | None
    employeeUserId: str
    employeeDisplayName: str | None
    organizationId: str | None
    organizationName: str | None
    relationType: str
    status: str
    createdAt: str
    updatedAt: str
