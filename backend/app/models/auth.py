import uuid
from datetime import datetime

from sqlalchemy import ForeignKey, String, Uuid
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
