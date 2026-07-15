from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator


Status = Literal["ACTIVE", "INACTIVE"]


def normalize_menu_code(value: str) -> str:
    return value.strip().upper().replace(" ", "_")


class MenuCommand(BaseModel):
    model_config = ConfigDict(str_strip_whitespace=True, extra="forbid")

    code: str = Field(min_length=2, max_length=100)
    title: str = Field(min_length=1, max_length=100)
    parentId: str | None = None
    routePath: str = ""
    componentKey: str = ""
    icon: str = ""
    sortOrder: int = 0
    status: Status = "ACTIVE"
    requiredPermissionCode: str | None = None

    @field_validator("code")
    @classmethod
    def normalize_code(cls, value: str) -> str:
        return normalize_menu_code(value)

    @field_validator("routePath")
    @classmethod
    def normalize_route_path(cls, value: str) -> str:
        value = value.strip()
        if not value:
            return ""
        return value if value.startswith("/") else f"/{value}"


class MenuPermissionCommand(BaseModel):
    model_config = ConfigDict(str_strip_whitespace=True, extra="forbid")

    roleId: str
    canView: bool = True
    canCreate: bool = False
    canUpdate: bool = False
    canDelete: bool = False


class MenuResponse(BaseModel):
    id: str
    code: str
    title: str
    parentId: str | None
    routePath: str
    componentKey: str
    icon: str
    sortOrder: int
    status: str
    requiredPermissionCode: str | None
    children: list["MenuResponse"] = []
    createdAt: str
    updatedAt: str


class MenuPermissionResponse(BaseModel):
    id: str
    menuId: str
    roleId: str
    roleCode: str
    roleName: str
    canView: bool
    canCreate: bool
    canUpdate: bool
    canDelete: bool
    createdAt: str
    updatedAt: str


class CurrentMenuResponse(BaseModel):
    menus: list[MenuResponse]
