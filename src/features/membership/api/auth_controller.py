"""Membership 認證 API。

負責登入、refresh token、登出、目前使用者/session 查詢，以及忘記密碼、重設密碼、
Email 驗證 token 流程。注意：實際寄信尚未完成串接，相關流程目前由 service 建立 token
與 notification outbox 資料供測試或後續寄信 worker 使用。
"""

from fastapi import Header, Request

from src.features.membership.api.base import create_membership_router
from src.features.membership.core.auth_middleware import extract_bearer_token
from src.features.membership.core.responses import ok
from src.features.membership.schemas.auth import (
    AuthTokenResponse,
    AuthUserResponse,
    EmailVerificationCommand,
    EmailVerificationResponse,
    ForgotPasswordCommand,
    ForgotPasswordResponse,
    LoginCommand,
    LogoutCommand,
    RefreshTokenCommand,
    ResetPasswordCommand,
    SessionResponse,
)
from src.features.membership.schemas.common import StandardResponse
from src.features.membership.services.auth_service import AuthService


membership_auth_router = create_membership_router(
    prefix="/api/membership/auth",
    tags=["membership-auth"],
)


def auth_service() -> AuthService:
    return AuthService()


def request_ip(request: Request) -> str:
    forwarded_for = request.headers.get("x-forwarded-for", "")
    if forwarded_for:
        return forwarded_for.split(",", 1)[0].strip()
    return request.client.host if request.client else ""


def request_user_agent(request: Request) -> str:
    return request.headers.get("user-agent", "")


@membership_auth_router.post(
    "/login",
    response_model=StandardResponse[AuthTokenResponse],
)
async def login(payload: LoginCommand, request: Request):
    return ok(
        auth_service().login(
            login=payload.login,
            password=payload.password,
            remember_me=payload.rememberMe,
            ip_address=request_ip(request),
            user_agent=request_user_agent(request),
        )
    )


@membership_auth_router.post(
    "/refresh",
    response_model=StandardResponse[AuthTokenResponse],
)
async def refresh_token(payload: RefreshTokenCommand):
    return ok(auth_service().refresh(refresh_token=payload.refreshToken))


@membership_auth_router.post(
    "/logout",
    response_model=StandardResponse[dict[str, bool]],
)
async def logout(payload: LogoutCommand, authorization: str | None = Header(default=None)):
    access_token = None
    if authorization:
        access_token = extract_bearer_token(authorization)
    return ok(auth_service().logout(refresh_token=payload.refreshToken, access_token=access_token))


@membership_auth_router.get(
    "/me",
    response_model=StandardResponse[AuthUserResponse],
)
async def me(authorization: str | None = Header(default=None)):
    return ok(auth_service().me(extract_bearer_token(authorization)))


@membership_auth_router.get(
    "/sessions",
    response_model=StandardResponse[list[SessionResponse]],
)
async def list_sessions(authorization: str | None = Header(default=None)):
    return ok(auth_service().list_sessions(extract_bearer_token(authorization)))


@membership_auth_router.post(
    "/forgot-password",
    response_model=StandardResponse[ForgotPasswordResponse],
)
async def forgot_password(payload: ForgotPasswordCommand, request: Request):
    return ok(
        auth_service().forgot_password(
            email=payload.email,
            ip_address=request_ip(request),
            user_agent=request_user_agent(request),
        )
    )


@membership_auth_router.post(
    "/reset-password",
    response_model=StandardResponse[dict[str, bool]],
)
async def reset_password(payload: ResetPasswordCommand, request: Request):
    return ok(auth_service().reset_password(
        token=payload.token,
        new_password=payload.newPassword,
        ip_address=request_ip(request),
        user_agent=request_user_agent(request),
    ))


@membership_auth_router.post(
    "/email-verification/request",
    response_model=StandardResponse[EmailVerificationResponse],
)
async def request_email_verification(
    request: Request,
    authorization: str | None = Header(default=None),
):
    return ok(
        auth_service().request_email_verification(
            access_token=extract_bearer_token(authorization),
            ip_address=request_ip(request),
            user_agent=request_user_agent(request),
        )
    )


@membership_auth_router.post(
    "/email-verification/verify",
    response_model=StandardResponse[dict[str, bool]],
)
async def verify_email(payload: EmailVerificationCommand, request: Request):
    return ok(auth_service().verify_email(
        token=payload.token,
        ip_address=request_ip(request),
        user_agent=request_user_agent(request),
    ))
