from typing import Annotated

from fastapi import Header

from src.features.membership.core.exceptions import ForbiddenError, UnauthorizedError
from src.features.membership.services.auth_service import AuthService


def extract_bearer_token(authorization: str | None) -> str:
    if not authorization:
        raise UnauthorizedError("Missing Authorization header.")
    scheme, _, token = authorization.partition(" ")
    if scheme.lower() != "bearer" or not token:
        raise UnauthorizedError("Invalid Authorization header.")
    return token


async def require_authenticated_user(
    authorization: Annotated[str | None, Header()] = None,
) -> dict:
    token = extract_bearer_token(authorization)
    return AuthService().authenticate_access_token(token)


def require_permission(permission_code: str):
    async def dependency(
        authorization: Annotated[str | None, Header()] = None,
    ) -> dict:
        from src.features.membership.services.rbac_service import RbacService

        token = extract_bearer_token(authorization)
        user = AuthService().authenticate_access_token(token)
        if not RbacService().user_has_permission(user["id"], permission_code):
            raise ForbiddenError(
                "Permission denied.",
                {"requiredPermission": permission_code},
            )
        return user

    return dependency


def require_any_permission(permission_codes: list[str]):
    async def dependency(
        authorization: Annotated[str | None, Header()] = None,
    ) -> dict:
        from src.features.membership.services.rbac_service import RbacService

        token = extract_bearer_token(authorization)
        user = AuthService().authenticate_access_token(token)
        rbac_service = RbacService()
        if not any(
            rbac_service.user_has_permission(user["id"], permission_code)
            for permission_code in permission_codes
        ):
            raise ForbiddenError(
                "Permission denied.",
                {"requiredAnyPermission": permission_codes},
            )
        return user

    return dependency
