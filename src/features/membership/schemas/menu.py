from pydantic import BaseModel


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


class CurrentMenuResponse(BaseModel):
    menus: list[MenuResponse]
