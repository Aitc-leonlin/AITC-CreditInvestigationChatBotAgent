from dataclasses import asdict, dataclass
from sqlite3 import Row
from typing import Any, TypeVar


ModelT = TypeVar("ModelT", bound="MembershipModel")


@dataclass(slots=True)
class MembershipModel:
    id: str
    created_at: str
    updated_at: str
    deleted_at: str | None = None

    @classmethod
    def from_row(cls: type[ModelT], row: Row | dict[str, Any]) -> ModelT:
        return cls(**dict(row))

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(slots=True)
class OrganizationUnit(MembershipModel):
    code: str = ""
    name: str = ""
    parent_id: str | None = None
    path: str = ""
    level: int = 0
    status: str = "ACTIVE"


@dataclass(slots=True)
class User(MembershipModel):
    username: str = ""
    email: str = ""
    display_name: str = ""
    employee_no: str = ""
    organization_id: str | None = None
    position_id: str | None = None
    status: str = "ACTIVE"
    locale: str = "zh-TW"
    timezone: str = "Asia/Taipei"
    last_login_at: str | None = None


@dataclass(slots=True)
class Role(MembershipModel):
    code: str = ""
    name: str = ""
    description: str = ""
    role_type: str = "BUSINESS"
    status: str = "ACTIVE"
    is_system: int = 0


@dataclass(slots=True)
class Permission(MembershipModel):
    code: str = ""
    name: str = ""
    description: str = ""
    action: str = ""
    status: str = "ACTIVE"


@dataclass(slots=True)
class MenuItem(MembershipModel):
    code: str = ""
    title: str = ""
    parent_id: str | None = None
    route_path: str = ""
    component_key: str = ""
    icon: str = ""
    sort_order: int = 0
    status: str = "ACTIVE"
    required_permission_code: str | None = None


@dataclass(slots=True)
class AuditLog(MembershipModel):
    actor_user_id: str | None = None
    action: str = ""
    resource_type: str = ""
    resource_id: str = ""
    outcome: str = "SUCCESS"
    ip_address: str = ""
    user_agent: str = ""
    metadata_json: str = "{}"
