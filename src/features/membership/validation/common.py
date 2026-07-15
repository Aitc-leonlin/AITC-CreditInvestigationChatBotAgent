from typing import Any

from pydantic import BaseModel, ConfigDict, Field, field_validator


class MembershipCommand(BaseModel):
    model_config = ConfigDict(str_strip_whitespace=True, extra="forbid")


class PaginationQuery(BaseModel):
    page: int = Field(default=1, ge=1)
    page_size: int = Field(default=20, ge=1, le=200)

    @property
    def offset(self) -> int:
        return (self.page - 1) * self.page_size


class CodeFieldMixin(BaseModel):
    code: str = Field(min_length=2, max_length=100)

    @field_validator("code")
    @classmethod
    def normalize_code(cls, value: str) -> str:
        normalized = value.strip()
        if not normalized:
            raise ValueError("code is required")
        return normalized.upper().replace(" ", "_")


def compact_text(value: Any) -> str:
    return " ".join(str(value or "").split())
