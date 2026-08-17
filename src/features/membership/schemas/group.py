from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator


GroupStatus = Literal["ACTIVE", "INACTIVE"]


class GroupCommand(BaseModel):
    model_config = ConfigDict(str_strip_whitespace=True, extra="forbid")

    code: str = Field(min_length=2, max_length=100)
    name: str = Field(min_length=1, max_length=120)
    category: str = Field(default="GENERAL", max_length=100)
    description: str = Field(default="", max_length=1000)
    masterUserId: str | None = None
    status: GroupStatus = "ACTIVE"

    @field_validator("code")
    @classmethod
    def normalize_code(cls, value: str) -> str:
        return value.strip().upper().replace(" ", "_")


class GroupMemberAddCommand(BaseModel):
    model_config = ConfigDict(extra="forbid")

    userIds: list[str] = Field(min_length=1, max_length=200)


class GroupMemberRemoveCommand(BaseModel):
    model_config = ConfigDict(extra="forbid")

    userIds: list[str] = Field(min_length=1, max_length=200)


class GroupMemberResponse(BaseModel):
    id: str
    userId: str
    username: str
    displayName: str
    email: str
    status: str
    isMaster: bool
    createdAt: str


class GroupResponse(BaseModel):
    id: str
    code: str
    name: str
    category: str
    description: str
    masterUserId: str | None
    masterUsername: str | None
    masterDisplayName: str | None
    status: str
    memberCount: int
    members: list[GroupMemberResponse] = Field(default_factory=list)
    canEditGroup: bool
    canManageMembers: bool
    createdAt: str
    updatedAt: str


class GroupListResponse(BaseModel):
    groups: list[GroupResponse]
    canCreateGroup: bool


class GroupAvailableUserResponse(BaseModel):
    id: str
    username: str
    displayName: str
    email: str
    status: str
