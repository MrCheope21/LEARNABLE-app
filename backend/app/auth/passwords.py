"""Changing, resetting and administratively setting passwords (docs/API.md "Auth").

Every password change bumps `users.token_version`, which every access token carries: all
existing sessions, on every device, end at once. The new session (if any) is issued after.
"""

import hashlib
import secrets
from datetime import UTC, datetime, timedelta

from sqlalchemy import func, select, update
from sqlalchemy.orm import Session

from app.auth.security import hash_password
from app.core.config import get_settings
from app.core.errors import InvalidRequestError
from app.db.types import utc_now
from app.models.auth import PasswordResetToken
from app.models.user import User

# Reset emails per account per hour; beyond this, requests are accepted but nothing is sent.
MAX_RESETS_PER_HOUR = 3
INVALID_RESET = "This reset link is invalid or has expired. Ask for a new one."


def token_hash(token: str) -> str:
    # The token is 256 random bits: a plain SHA-256 is enough to make stored hashes useless.
    return hashlib.sha256(token.encode()).hexdigest()


def set_password(db: Session, user: User, new_password: str) -> None:
    """The caller commits. Ends every session and retires every outstanding reset link."""
    user.hashed_password = hash_password(new_password)
    user.token_version += 1
    db.execute(
        update(PasswordResetToken)
        .where(PasswordResetToken.user_id == user.id, PasswordResetToken.used_at.is_(None))
        .values(used_at=utc_now())
    )


def issue_reset_link(db: Session, user: User) -> str | None:
    """A new single-use link, or None when this account already got MAX_RESETS_PER_HOUR links in
    the last hour. Older unused links stop working. The caller commits."""
    now = utc_now()
    recent = db.scalar(
        select(func.count())
        .select_from(PasswordResetToken)
        .where(
            PasswordResetToken.user_id == user.id,
            PasswordResetToken.created_at > now - timedelta(hours=1),
        )
    )
    if (recent or 0) >= MAX_RESETS_PER_HOUR:
        return None
    db.execute(
        update(PasswordResetToken)
        .where(PasswordResetToken.user_id == user.id, PasswordResetToken.used_at.is_(None))
        .values(used_at=now)
    )
    token = secrets.token_urlsafe(32)
    settings = get_settings()
    db.add(
        PasswordResetToken(
            user_id=user.id,
            token_hash=token_hash(token),
            created_at=now,
            expires_at=now + timedelta(minutes=settings.password_reset_ttl_minutes),
        )
    )
    return f"{settings.public_app_url.rstrip('/')}/reset-password?token={token}"


def reset_with_token(db: Session, token: str, new_password: str) -> User:
    """Sets the new password if the link is valid, unused and unexpired. The caller commits."""
    row = db.scalar(
        select(PasswordResetToken).where(PasswordResetToken.token_hash == token_hash(token))
    )
    if row is None or row.used_at is not None or _aware(row.expires_at) <= utc_now():
        raise InvalidRequestError(INVALID_RESET, details={"reason": "invalid_reset_token"})
    user = db.get(User, row.user_id)
    if user is None:
        raise InvalidRequestError(INVALID_RESET, details={"reason": "invalid_reset_token"})
    set_password(db, user, new_password)
    row.used_at = utc_now()
    return user


def reset_email(link: str, minutes: int) -> tuple[str, str]:
    subject = "Reset your LEARNABLE password"
    body = (
        "Someone (hopefully you) asked to reset the password of your LEARNABLE account.\n\n"
        f"Choose a new password here (the link works once, for {minutes} minutes):\n{link}\n\n"
        "If it wasn't you, ignore this email: your password stays as it is.\n"
    )
    return subject, body


def _aware(value: datetime) -> datetime:
    return value if value.tzinfo else value.replace(tzinfo=UTC)
