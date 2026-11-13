import uuid
from datetime import date, datetime

from sqlalchemy import Boolean, Date, Integer, String, Uuid, false, true
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base
from app.db.types import UTCDateTime, utc_now


class User(Base):
    __tablename__ = "users"

    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=uuid.uuid4)
    # Always stored lowercased (normalized in app/auth/schemas.py), so uniqueness is
    # case-insensitive in practice.
    email: Mapped[str] = mapped_column(String(320), unique=True, index=True)
    # Optional sign-in name, an alternative to the email. Lowercase letters, digits and . _ -
    # (app/auth/schemas.py); never contains "@", so it can't be mistaken for an email.
    username: Mapped[str | None] = mapped_column(String(30), unique=True, index=True, default=None)
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
    # Opt-in to the community: appears on leaderboards, can be found and followed. Off by
    # default; needs a display_name (the email is never shown to other users).
    community_visible: Mapped[bool] = mapped_column(Boolean, default=False, server_default=false())
    # Carried by every access token; a password change increments it, so every existing session
    # (on every device) ends at once.
    token_version: Mapped[int] = mapped_column(Integer, default=0, server_default="0")
    # Administrators manage invitations and accounts (app/api/admin.py). Set from the command line
    # (scripts/manage_users.py), never by an API call.
    is_admin: Mapped[bool] = mapped_column(Boolean, default=False, server_default=false())
    # False: suspended. Signing in and every existing token stop working at once.
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, server_default=true())
    # Per-account overrides of the daily limits (null: the server defaults, see config.py).
    limit_evaluations: Mapped[int | None] = mapped_column(Integer, default=None)
    limit_generations: Mapped[int | None] = mapped_column(Integer, default=None)
    limit_storage_mb: Mapped[int | None] = mapped_column(Integer, default=None)
    # Email about updates to courses the user has (the in-app notification is always there).
    email_updates: Mapped[bool] = mapped_column(Boolean, default=True, server_default=true())
    # Selling paid courses: the seller's account at the payment provider, and whether it can
    # take payments yet (services/payments.py).
    payout_account_id: Mapped[str | None] = mapped_column(String(255), default=None)
    payout_ready: Mapped[bool] = mapped_column(Boolean, default=False, server_default=false())
    # Review reminders by push notification: the local hour to send one (null: none), and the
    # user's local day the last one went out (services/push.py).
    reminder_hour: Mapped[int | None] = mapped_column(Integer, default=18, server_default="18")
    last_reminded_on: Mapped[date | None] = mapped_column(Date, default=None)
    created_at: Mapped[datetime] = mapped_column(UTCDateTime, default=utc_now)
