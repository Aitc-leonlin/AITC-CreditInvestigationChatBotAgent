from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator


Status = Literal["ACTIVE", "INACTIVE"]
RoleType = Literal["SYSTEM", "BUSINESS"]


def normalize_code(value: str) -> str:
    return value.strip().upper().replace(" ", "_")


class RoleCommand(BaseModel):
    model_config = ConfigDict(str_strip_whitespace=True, extra="forbid")

    code: str = Field(min_length=2, max_length=100)
    name: str = Field(min_length=1, max_length=100)
    description: str = ""
    roleType: RoleType = "BUSINESS"
    status: Status = "ACTIVE"
    isSystem: bool = False

    @field_validator("code")
    @classmethod
    def normalize_role_code(cls, value: str) -> str:
        return normalize_code(value)


class PermissionGroupCommand(BaseModel):
    model_config = ConfigDict(str_strip_whitespace=True, extra="forbid")

    code: str = Field(min_length=2, max_length=100)
    name: str = Field(min_length=1, max_length=100)
    description: str = ""
    status: Status = "ACTIVE"

    @field_validator("code")
    @classmethod
    def normalize_group_code(cls, value: str) -> str:
        return normalize_code(value)


class PermissionCommand(BaseModel):
    model_config = ConfigDict(str_strip_whitespace=True, extra="forbid")

    code: str = Field(min_length=3, max_length=160)
    name: str = Field(min_length=1, max_length=120)
    description: str = ""
    action: str = Field(min_length=1, max_length=100)
    status: Status = "ACTIVE"
    groupId: str | None = None

    @field_validator("code", "action")
    @classmethod
    def normalize_permission_identity(cls, value: str) -> str:
        return value.strip().lower()


class IdsCommand(BaseModel):
    model_config = ConfigDict(str_strip_whitespace=True, extra="forbid")

    ids: list[str] = Field(default_factory=list)


class UserRolesCommand(BaseModel):
    model_config = ConfigDict(str_strip_whitespace=True, extra="forbid")

    roleIds: list[str] = Field(default_factory=list)
    organizationId: str | None = None


class RoleResponse(BaseModel):
    id: str
    code: str
    name: str
    description: str
    roleType: str
    status: str
    isSystem: bool
    userCount: int
    permissionCount: int
    createdAt: str
    updatedAt: str


class PermissionGroupResponse(BaseModel):
    id: str
    code: str
    name: str
    description: str
    status: str
    permissionCount: int
    createdAt: str
    updatedAt: str


class PermissionResponse(BaseModel):
    id: str
    code: str
    name: str
    description: str
    action: str
    status: str
    groupId: str | None
    groupCode: str | None
    groupName: str | None
    createdAt: str
    updatedAt: str


class UserRolesResponse(BaseModel):
    userId: str
    roleIds: list[str]


class RolePermissionsResponse(BaseModel):
    roleId: str
    permissionIds: list[str]


class CurrentPermissionsResponse(BaseModel):
    permissions: list[str]
