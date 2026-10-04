import uuid
from datetime import datetime

from sqlalchemy import Integer, String, Uuid
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base
from app.db.types import UTCDateTime, utc_now


class User(Base):
    __tablename__ = "users"

    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=uuid.uuid4)
    # Always stored lowercased (normalized in app/auth/schemas.py), so uniqueness is
    # case-insensitive in practice.
    email: Mapped[str] = mapped_column(String(320), unique=True, index=True)
    hashed_password: Mapped[str] = mapped_column(String(255))
    # IANA zone ("Europe/Rome"): decides the user's calendar day for streaks, the daily goal,
    # XP today and the activity calendar. Set from the device at registration; UTC otherwise
    # (docs/XP_AND_ACTIVITY.md §5).
    timezone: Mapped[str] = mapped_column(String(64), default="UTC", server_default="UTC")
    # Completed answers per day the user aims for.
    daily_goal: Mapped[int] = mapped_column(Integer, default=20, server_default="20")
    # Interface language of the web and app clients (a code from auth.schemas.Language).
    language: Mapped[str] = mapped_column(String(8), default="en", server_default="en")
    # How the user wants to be shown; optional, the email is used otherwise.
    display_name: Mapped[str | None] = mapped_column(String(80), default=None)
    # Carried by every access token; a password change increments it, so every existing session
    # (on every device) ends at once.
    token_version: Mapped[int] = mapped_column(Integer, default=0, server_default="0")
    created_at: Mapped[datetime] = mapped_column(UTCDateTime, default=utc_now)
