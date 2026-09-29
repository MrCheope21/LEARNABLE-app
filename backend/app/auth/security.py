"""Password hashing and JWT issuance/verification.

Kept free of web-framework and DB imports so it's unit-testable in isolation.
"""

import uuid
from datetime import UTC, datetime, timedelta
from functools import lru_cache

import jwt
from argon2 import PasswordHasher
from argon2.exceptions import InvalidHashError, VerificationError

from app.core.config import get_settings

# Pinned rather than configurable: letting config pick the algorithm opens the door to
# algorithm-confusion attacks (e.g. "none", or RS/HS key mix-ups).
_JWT_ALGORITHM = "HS256"
_ACCESS_TOKEN_TYPE = "access"  # noqa: S105 — JWT "type" claim value, not a secret

# Argon2id with argon2-cffi's defaults (OWASP's first-choice password hash); no 72-byte input
# truncation, unlike bcrypt.
_hasher = PasswordHasher()


def hash_password(password: str) -> str:
    return _hasher.hash(password)


def verify_password(password: str, password_hash: str) -> bool:
    try:
        return _hasher.verify(password_hash, password)
    except (VerificationError, InvalidHashError):
        return False


def password_needs_rehash(password_hash: str) -> bool:
    return _hasher.check_needs_rehash(password_hash)


@lru_cache
def _dummy_hash() -> str:
    return _hasher.hash("timing-equalization-placeholder")


def spend_equivalent_verification_time(password: str) -> None:
    """Run a real hash verification for a login with an unknown email.

    Without this, "no such user" returns measurably faster than "wrong password", letting an
    attacker enumerate registered emails by timing the login endpoint.
    """
    verify_password(password, _dummy_hash())


def create_access_token(user_id: uuid.UUID, version: int = 0) -> str:
    """`version` is the user's token_version: a password change makes older tokens invalid."""
    settings = get_settings()
    now = datetime.now(UTC)
    payload = {
        "sub": str(user_id),
        "ver": version,
        "type": _ACCESS_TOKEN_TYPE,
        "iat": now,
        "exp": now + timedelta(minutes=settings.auth_access_token_expire_minutes),
    }
    return jwt.encode(payload, settings.auth_secret.get_secret_value(), algorithm=_JWT_ALGORITHM)


def decode_access_token(token: str) -> tuple[uuid.UUID, int] | None:
    """Return (user id, token version) for a valid, unexpired access token, else None. Tokens
    issued before versions existed count as version 0."""
    settings = get_settings()
    try:
        payload = jwt.decode(
            token,
            settings.auth_secret.get_secret_value(),
            algorithms=[_JWT_ALGORITHM],
            options={"require": ["sub", "exp", "iat"]},
        )
    except jwt.InvalidTokenError:
        return None
    if payload.get("type") != _ACCESS_TOKEN_TYPE:
        return None
    version = payload.get("ver", 0)
    if not isinstance(version, int):
        return None
    try:
        return uuid.UUID(payload["sub"]), version
    except (ValueError, TypeError):
        return None
