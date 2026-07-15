import base64
import hashlib
import hmac
import json
import os
import time
from typing import Any

from src.features.membership.core.exceptions import UnauthorizedError


JWT_ALGORITHM = "HS256"
JWT_SECRET_ENV = "MEMBERSHIP_JWT_SECRET"
DEFAULT_JWT_SECRET = "change-this-membership-jwt-secret"


def base64url_encode(raw: bytes) -> str:
    return base64.urlsafe_b64encode(raw).rstrip(b"=").decode("ascii")


def base64url_decode(value: str) -> bytes:
    padding = "=" * (-len(value) % 4)
    return base64.urlsafe_b64decode((value + padding).encode("ascii"))


def jwt_secret() -> bytes:
    return os.getenv(JWT_SECRET_ENV, DEFAULT_JWT_SECRET).encode("utf-8")


def encode_jwt(payload: dict[str, Any]) -> str:
    header = {"alg": JWT_ALGORITHM, "typ": "JWT"}
    encoded_header = base64url_encode(json.dumps(header, separators=(",", ":")).encode("utf-8"))
    encoded_payload = base64url_encode(json.dumps(payload, separators=(",", ":")).encode("utf-8"))
    signing_input = f"{encoded_header}.{encoded_payload}".encode("ascii")
    signature = hmac.new(jwt_secret(), signing_input, hashlib.sha256).digest()
    return f"{encoded_header}.{encoded_payload}.{base64url_encode(signature)}"


def decode_jwt(token: str) -> dict[str, Any]:
    try:
        encoded_header, encoded_payload, encoded_signature = token.split(".", 2)
        signing_input = f"{encoded_header}.{encoded_payload}".encode("ascii")
        expected_signature = hmac.new(jwt_secret(), signing_input, hashlib.sha256).digest()
        actual_signature = base64url_decode(encoded_signature)
        if not hmac.compare_digest(actual_signature, expected_signature):
            raise UnauthorizedError("Invalid access token.")
        header = json.loads(base64url_decode(encoded_header))
        if header.get("alg") != JWT_ALGORITHM:
            raise UnauthorizedError("Unsupported token algorithm.")
        payload = json.loads(base64url_decode(encoded_payload))
    except UnauthorizedError:
        raise
    except Exception as exc:
        raise UnauthorizedError("Invalid access token.") from exc

    expires_at = int(payload.get("exp") or 0)
    if expires_at <= int(time.time()):
        raise UnauthorizedError("Access token expired.")
    return payload
