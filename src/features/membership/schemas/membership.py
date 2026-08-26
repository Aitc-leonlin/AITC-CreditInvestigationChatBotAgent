from pydantic import BaseModel


class OrganizationUnitSchema(BaseModel):
    id: str
    code: str
    name: str
    parent_id: str | None
    path: str
    level: int
    status: str
    sort_order: int
    created_at: str
    updated_at: str
    deleted_at: str | None


class UserSchema(BaseModel):
    id: str
    username: str
    email: str
    display_name: str
    employee_no: str
    organization_id: str | None
    status: str
    locale: str
    timezone: str
    last_login_at: str | None
    created_at: str
    updated_at: str
    deleted_at: str | None


class RoleSchema(BaseModel):
    id: str
    code: str
    name: str
    description: str
    role_type: str
    status: str
    is_system: int
    created_at: str
    updated_at: str
    deleted_at: str | None


class PermissionSchema(BaseModel):
    id: str
    code: str
    name: str
    description: str
    action: str
    status: str
    created_at: str
    updated_at: str
    deleted_at: str | None


class MenuItemSchema(BaseModel):
    id: str
    code: str
    title: str
    parent_id: str | None
    route_path: str
    component_key: str
    icon: str
    sort_order: int
    status: str
    required_permission_code: str | None
    created_at: str
    updated_at: str
    deleted_at: str | None
