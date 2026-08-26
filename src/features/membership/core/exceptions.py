from dataclasses import dataclass, field
import logging
from typing import Any
import uuid

from fastapi import HTTPException, Request, status
from fastapi.responses import JSONResponse
from pydantic import ValidationError


logger = logging.getLogger(__name__)


@dataclass
class MembershipError(Exception):
    message: str
    code: str = "MEMBERSHIP_ERROR"
    status_code: int = status.HTTP_400_BAD_REQUEST
    details: dict[str, Any] = field(default_factory=dict)


class ResourceNotFoundError(MembershipError):
    def __init__(self, message: str = "Resource not found.", details: dict[str, Any] | None = None):
        super().__init__(
            message=message,
            code="RESOURCE_NOT_FOUND",
            status_code=status.HTTP_404_NOT_FOUND,
            details=details or {},
        )


class ConflictError(MembershipError):
    def __init__(self, message: str = "Resource conflict.", details: dict[str, Any] | None = None):
        super().__init__(
            message=message,
            code="RESOURCE_CONFLICT",
            status_code=status.HTTP_409_CONFLICT,
            details=details or {},
        )


class ValidationFailureError(MembershipError):
    def __init__(self, message: str = "Validation failed.", details: dict[str, Any] | None = None):
        super().__init__(
            message=message,
            code="VALIDATION_FAILED",
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            details=details or {},
        )


class UnauthorizedError(MembershipError):
    def __init__(self, message: str = "Unauthorized.", details: dict[str, Any] | None = None):
        super().__init__(
            message=message,
            code="UNAUTHORIZED",
            status_code=status.HTTP_401_UNAUTHORIZED,
            details=details or {},
        )


class ForbiddenError(MembershipError):
    def __init__(self, message: str = "Forbidden.", details: dict[str, Any] | None = None):
        super().__init__(
            message=message,
            code="FORBIDDEN",
            status_code=status.HTTP_403_FORBIDDEN,
            details=details or {},
        )


async def membership_error_handler(_: Request, exc: MembershipError) -> JSONResponse:
    return JSONResponse(
        status_code=exc.status_code,
        content={
            "success": False,
            "data": None,
            "error": {
                "code": exc.code,
                "message": exc.message,
                "details": exc.details,
            },
            "meta": {},
        },
    )


async def http_error_handler(_: Request, exc: HTTPException) -> JSONResponse:
    return JSONResponse(
        status_code=exc.status_code,
        content={
            "success": False,
            "data": None,
            "error": {
                "code": "HTTP_ERROR",
                "message": str(exc.detail),
                "details": {},
            },
            "meta": {},
        },
    )


async def unhandled_error_handler(request: Request, exc: Exception) -> JSONResponse:
    request_id = str(uuid.uuid4())
    logger.exception(
        "Unhandled API error request_id=%s method=%s path=%s",
        request_id,
        request.method,
        request.url.path,
        exc_info=exc,
    )
    return JSONResponse(
        status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
        content={
            "success": False,
            "data": None,
            "error": {
                "code": "INTERNAL_SERVER_ERROR",
                "message": "系統處理請求時發生錯誤。",
                "details": {"requestId": request_id},
            },
            "meta": {},
        },
        headers={"X-Request-ID": request_id},
    )


def validation_error_details(exc: ValidationError) -> dict[str, Any]:
    return {"errors": exc.errors()}
