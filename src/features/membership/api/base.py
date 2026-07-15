"""Membership API router 共用工具。

提供 create_membership_router(...) 統一建立 FastAPI APIRouter，讓各
membership API 使用一致的 prefix、tags 與 dependencies 註冊方式。
"""

from fastapi import APIRouter
from typing import Any


def create_membership_router(
    *,
    prefix: str,
    tags: list[str],
    dependencies: list[Any] | None = None,
) -> APIRouter:
    return APIRouter(prefix=prefix, tags=tags, dependencies=dependencies or [])
