"""Password hashing helpers (stdlib PBKDF2 — no extra dependency)."""

from __future__ import annotations

import hashlib
import hmac
import secrets

_SCHEME = "pbkdf2_sha256"
_ITERATIONS = 260_000


def hash_password(password: str) -> str:
    salt = secrets.token_hex(16)
    dk = hashlib.pbkdf2_hmac("sha256", password.encode("utf-8"), salt.encode("utf-8"), _ITERATIONS)
    return f"{_SCHEME}${_ITERATIONS}${salt}${dk.hex()}"


def verify_password(password: str, password_hash: str) -> bool:
    try:
        scheme, iter_s, salt, digest = password_hash.split("$", 3)
        if scheme != _SCHEME:
            return False
        iterations = int(iter_s)
    except (ValueError, TypeError):
        return False
    dk = hashlib.pbkdf2_hmac(
        "sha256", password.encode("utf-8"), salt.encode("utf-8"), iterations
    )
    return hmac.compare_digest(dk.hex(), digest)


def hash_session_token(token: str) -> str:
    return hashlib.sha256(token.encode("utf-8")).hexdigest()


def new_session_token() -> str:
    return secrets.token_urlsafe(32)
