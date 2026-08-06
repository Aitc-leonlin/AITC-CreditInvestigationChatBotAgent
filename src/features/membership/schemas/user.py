from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator


UserStatus = Literal["ACTIVE", "INACTIVE"]


def normalize_email_value(value: str) -> str:
    normalized = value.strip().lower()
    if (
        "@" not in normalized
        or normalized.startswith("@")
        or normalized.endswith("@")
        or "." not in normalized.split("@", 1)[1]
    ):
        raise ValueError("email format is invalid")
    return normalized


class UserCreateCommand(BaseModel):
    model_config = ConfigDict(str_strip_whitespace=True, extra="forbid")

    username: str = Field(min_length=3, max_length=64)
    email: str = Field(min_length=3, max_length=254)
    displayName: str = Field(min_length=1, max_length=100)
    employeeNo: str = Field(default="", max_length=50)
    organizationId: str | None = None
    departmentId: str | None = None
    managerUserId: str | None = None
    status: UserStatus = "ACTIVE"
    locale: str = Field(default="zh-TW", max_length=20)
    timezone: str = Field(default="Asia/Taipei", max_length=60)
    password: str = Field(min_length=8, max_length=128)
    mustChangePassword: bool = True
    roleIds: list[str] = Field(default_factory=lambda: ["role-default-user"])

    @field_validator("username")
    @classmethod
    def normalize_username(cls, value: str) -> str:
        normalized = value.strip().lower()
        if " " in normalized:
            raise ValueError("username cannot contain spaces")
        return normalized

    @field_validator("email")
    @classmethod
    def normalize_email(cls, value: str) -> str:
        return normalize_email_value(value)


class UserUpdateCommand(BaseModel):
    model_config = ConfigDict(str_strip_whitespace=True, extra="forbid")

    username: str = Field(min_length=3, max_length=64)
    email: str = Field(min_length=3, max_length=254)
    displayName: str = Field(min_length=1, max_length=100)
    employeeNo: str = Field(default="", max_length=50)
    organizationId: str | None = None
    departmentId: str | None = None
    managerUserId: str | None = None
    status: UserStatus = "ACTIVE"
    locale: str = Field(default="zh-TW", max_length=20)
    timezone: str = Field(default="Asia/Taipei", max_length=60)
    roleIds: list[str] | None = None

    @field_validator("username")
    @classmethod
    def normalize_username(cls, value: str) -> str:
        normalized = value.strip().lower()
        if " " in normalized:
            raise ValueError("username cannot contain spaces")
        return normalized

    @field_validator("email")
    @classmethod
    def normalize_email(cls, value: str) -> str:
        return normalize_email_value(value)


class UserProfileUpdateCommand(BaseModel):
    model_config = ConfigDict(str_strip_whitespace=True, extra="forbid")

    displayName: str = Field(min_length=1, max_length=100)
    email: str = Field(min_length=3, max_length=254)
    locale: str = Field(default="zh-TW", max_length=20)
    timezone: str = Field(default="Asia/Taipei", max_length=60)

    @field_validator("email")
    @classmethod
    def normalize_email(cls, value: str) -> str:
        return normalize_email_value(value)


class UserStatusCommand(BaseModel):
    model_config = ConfigDict(str_strip_whitespace=True, extra="forbid")

    status: UserStatus


class UserLockCommand(BaseModel):
    model_config = ConfigDict(str_strip_whitespace=True, extra="forbid")

    lockedUntil: str | None = None


class UserChangePasswordCommand(BaseModel):
    model_config = ConfigDict(str_strip_whitespace=True, extra="forbid")

    currentPassword: str = Field(min_length=1, max_length=128)
    newPassword: str = Field(min_length=8, max_length=128)


class AdminResetPasswordCommand(BaseModel):
    model_config = ConfigDict(str_strip_whitespace=True, extra="forbid")

    newPassword: str = Field(min_length=8, max_length=128)
    mustChangePassword: bool = True


class UserResponse(BaseModel):
    id: str
    username: str
    email: str
    displayName: str
    employeeNo: str
    organizationId: str | None
    organizationName: str | None
    departmentId: str | None = None
    departmentName: str | None = None
    managerUserId: str | None = None
    managerDisplayName: str | None = None
    status: str
    locale: str
    timezone: str
    lastLoginAt: str | None
    lockedUntil: str | None
    failedLoginCount: int
    mustChangePassword: bool
    mfaEnabled: bool
    createdAt: str
    updatedAt: str


class UserListResponse(BaseModel):
    users: list[UserResponse]
    total: int
    page: int
    pageSize: int
    offset: int
