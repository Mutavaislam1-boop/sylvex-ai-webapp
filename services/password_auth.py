"""Password hashing and one-time tokens for SYLVEX website email accounts.

Stdlib-only (PBKDF2-HMAC-SHA256 via hashlib), matching this codebase's existing
preference for no new dependencies over Telegram initData/media-signing HMAC
code in services/security.py. Never logs or returns a password or its hash.
"""
from __future__ import annotations
import hashlib
import hmac
import os
import re
import secrets

PBKDF2_ITERATIONS = 260_000
_HASH_PREFIX = "pbkdf2_sha256"

EMAIL_RE = re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]+$")


def is_valid_email(email: str) -> bool:
    return bool(isinstance(email, str) and 3 <= len(email) <= 254 and EMAIL_RE.match(email.strip()))


def normalize_email(email: str) -> str:
    return email.strip().lower()


def password_strength_error(password: str) -> str | None:
    """Returns an error code, or None if the password is acceptable."""
    if not isinstance(password, str) or len(password) < 8:
        return "password_too_short"
    if len(password) > 256:
        return "password_too_long"
    return None


def hash_password(password: str) -> str:
    salt = secrets.token_hex(16)
    digest = hashlib.pbkdf2_hmac("sha256", password.encode("utf-8"), salt.encode("utf-8"), PBKDF2_ITERATIONS)
    return f"{_HASH_PREFIX}${PBKDF2_ITERATIONS}${salt}${digest.hex()}"


def verify_password(password: str, encoded: str) -> bool:
    try:
        algo, iterations_s, salt, hex_digest = (encoded or "").split("$", 3)
        if algo != _HASH_PREFIX:
            return False
        iterations = int(iterations_s)
    except (ValueError, AttributeError):
        return False
    candidate = hashlib.pbkdf2_hmac("sha256", (password or "").encode("utf-8"), salt.encode("utf-8"), iterations)
    return hmac.compare_digest(candidate.hex(), hex_digest)


def new_token() -> str:
    """A random, URL-safe token for email verification / password reset links."""
    return secrets.token_urlsafe(32)


def new_negative_account_seed() -> int:
    """Fallback in-process unique negative id if the DB sequence is unavailable."""
    return -int.from_bytes(os.urandom(6), "big")
