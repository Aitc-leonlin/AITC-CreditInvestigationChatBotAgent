import hashlib
import hmac
import os
from base64 import b64decode, b64encode


PASSWORD_ALGORITHM = "pbkdf2_sha256"
PBKDF2_ITERATIONS = 260000


def hash_password(password: str) -> str:
    salt = os.urandom(16)
    digest = hashlib.pbkdf2_hmac(
        "sha256",
        password.encode("utf-8"),
        salt,
        PBKDF2_ITERATIONS,
    )
    return "$".join(
        [
            PASSWORD_ALGORITHM,
            str(PBKDF2_ITERATIONS),
            b64encode(salt).decode("ascii"),
            b64encode(digest).decode("ascii"),
        ]
    )


def verify_password(password: str, password_hash: str) -> bool:
    try:
        algorithm, iterations_text, salt_text, digest_text = password_hash.split("$", 3)
        if algorithm != PASSWORD_ALGORITHM:
            return False
        iterations = int(iterations_text)
        salt = b64decode(salt_text.encode("ascii"))
        expected_digest = b64decode(digest_text.encode("ascii"))
    except Exception:
        return False

    actual_digest = hashlib.pbkdf2_hmac(
        "sha256",
        password.encode("utf-8"),
        salt,
        iterations,
    )
    return hmac.compare_digest(actual_digest, expected_digest)
