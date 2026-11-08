import uuid
from datetime import date, datetime

from sqlalchemy import Date, ForeignKey, Integer, String, UniqueConstraint, Uuid
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base
from app.db.types import UTCDateTime, utc_now


class PasswordResetToken(Base):
    """A "forgot your password" link (docs/API.md "Auth"). Only a SHA-256 of the random token is
    stored, so a database leak can't be turned into working links. Single use, short-lived, and
    issuing a new one retires the older ones."""

    __tablename__ = "password_reset_tokens"

    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=uuid.uuid4)
    user_id: Mapped[uuid.UUID] = mapped_column(
        Uuid, ForeignKey("users.id", ondelete="CASCADE"), index=True
    )
    token_hash: Mapped[str] = mapped_column(String(64), unique=True)
    created_at: Mapped[datetime] = mapped_column(UTCDateTime, default=utc_now)
    expires_at: Mapped[datetime] = mapped_column(UTCDateTime)
    # Set when used, or when a newer link or a password change retired it.
    used_at: Mapped[datetime | None] = mapped_column(UTCDateTime, default=None)


class Invitation(Base):
    """Permission to create an account, handed out by an administrator as a link. Only a SHA-256
    of the random code is stored (like password reset links): the code can't be read back from the
    database, and the administrator sees the link once, when it is created. Single use."""

    __tablename__ = "invitations"

    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=uuid.uuid4)
    token_hash: Mapped[str] = mapped_column(String(64), unique=True)
    created_by: Mapped[uuid.UUID | None] = mapped_column(
        Uuid, ForeignKey("users.id", ondelete="SET NULL"), default=None
    )
    created_at: Mapped[datetime] = mapped_column(UTCDateTime, default=utc_now)
    expires_at: Mapped[datetime] = mapped_column(UTCDateTime)
    # When set, only this address can use it.
    email: Mapped[str | None] = mapped_column(String(320), default=None)
    # The administrator's own label, e.g. "Marco".
    note: Mapped[str] = mapped_column(String(120), default="")
    used_at: Mapped[datetime | None] = mapped_column(UTCDateTime, default=None)
    used_by: Mapped[uuid.UUID | None] = mapped_column(
        Uuid, ForeignKey("users.id", ondelete="SET NULL"), default=None
    )
    revoked_at: Mapped[datetime | None] = mapped_column(UTCDateTime, default=None)


class AiUsage(Base):
    """How many AI-backed requests an account made on a UTC day, per kind ("evaluation" or
    "generation"). The daily limits (app/services/quota.py) read it; it survives restarts."""

    __tablename__ = "ai_usage"
    __table_args__ = (UniqueConstraint("user_id", "day", "kind"),)

    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=uuid.uuid4)
    user_id: Mapped[uuid.UUID] = mapped_column(
        Uuid, ForeignKey("users.id", ondelete="CASCADE"), index=True
    )
    day: Mapped[date] = mapped_column(Date, index=True)
    kind: Mapped[str] = mapped_column(String(16))
    count: Mapped[int] = mapped_column(Integer, default=0)
