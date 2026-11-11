"""Friends, blocks, private messages and notifications (docs/COMMUNITY.md)."""

import uuid
from datetime import datetime
from typing import Any

from sqlalchemy import (
    JSON,
    CheckConstraint,
    ForeignKey,
    Index,
    String,
    Text,
    UniqueConstraint,
    Uuid,
)
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base
from app.db.types import UTCDateTime, utc_now

PENDING = "PENDING"
ACCEPTED = "ACCEPTED"


def pair_key(a: uuid.UUID, b: uuid.UUID) -> str:
    """The same key whichever of the two people is named first."""
    low, high = sorted((a.hex, b.hex))
    return f"{low}:{high}"


class Friendship(Base):
    """A friend request and, once accepted, the friendship. One row per pair of people
    (`pair_key` is unique), so two crossing requests can't both exist. Declining, cancelling
    and removing a friend all delete the row: either may ask again later."""

    __tablename__ = "friendships"
    __table_args__ = (
        CheckConstraint("requester_id <> addressee_id", name="not_self"),
        Index("ix_friendships_addressee_id_status", "addressee_id", "status"),
        Index("ix_friendships_requester_id_status", "requester_id", "status"),
    )

    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=uuid.uuid4)
    pair_key: Mapped[str] = mapped_column(String(65), unique=True)
    requester_id: Mapped[uuid.UUID] = mapped_column(
        Uuid, ForeignKey("users.id", ondelete="CASCADE")
    )
    addressee_id: Mapped[uuid.UUID] = mapped_column(
        Uuid, ForeignKey("users.id", ondelete="CASCADE")
    )
    status: Mapped[str] = mapped_column(String(16), default=PENDING)
    created_at: Mapped[datetime] = mapped_column(UTCDateTime, default=utc_now)
    responded_at: Mapped[datetime | None] = mapped_column(UTCDateTime, default=None)


class Block(Base):
    """`blocker_id` doesn't want to hear from `blocked_id`: no requests, no messages, and
    neither finds the other. The blocked person isn't told."""

    __tablename__ = "blocks"
    __table_args__ = (
        UniqueConstraint("blocker_id", "blocked_id"),
        CheckConstraint("blocker_id <> blocked_id", name="not_self"),
    )

    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=uuid.uuid4)
    blocker_id: Mapped[uuid.UUID] = mapped_column(
        Uuid, ForeignKey("users.id", ondelete="CASCADE"), index=True
    )
    blocked_id: Mapped[uuid.UUID] = mapped_column(
        Uuid, ForeignKey("users.id", ondelete="CASCADE"), index=True
    )
    created_at: Mapped[datetime] = mapped_column(UTCDateTime, default=utc_now)


class Message(Base):
    """A private message between two friends. Plain text; kept until either account is
    deleted."""

    __tablename__ = "messages"
    __table_args__ = (
        Index("ix_messages_pair_key_created_at", "pair_key", "created_at"),
        Index("ix_messages_recipient_id_read_at", "recipient_id", "read_at"),
    )

    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=uuid.uuid4)
    pair_key: Mapped[str] = mapped_column(String(65))
    sender_id: Mapped[uuid.UUID] = mapped_column(
        Uuid, ForeignKey("users.id", ondelete="CASCADE"), index=True
    )
    recipient_id: Mapped[uuid.UUID] = mapped_column(
        Uuid, ForeignKey("users.id", ondelete="CASCADE")
    )
    body: Mapped[str] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(UTCDateTime, default=utc_now)
    read_at: Mapped[datetime | None] = mapped_column(UTCDateTime, default=None)


class Notification(Base):
    """Something that happened for a user while they weren't looking: a friend request, an
    accepted request, an update to a course they have, a review of their course, a sale. The
    text is written by the client from `kind` and `data` (so it's in the reader's language)."""

    __tablename__ = "notifications"
    __table_args__ = (Index("ix_notifications_user_id_created_at", "user_id", "created_at"),)

    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=uuid.uuid4)
    user_id: Mapped[uuid.UUID] = mapped_column(Uuid, ForeignKey("users.id", ondelete="CASCADE"))
    kind: Mapped[str] = mapped_column(String(32))
    # Who caused it, when it was a person (their display name is read when listing).
    actor_id: Mapped[uuid.UUID | None] = mapped_column(
        Uuid, ForeignKey("users.id", ondelete="CASCADE"), default=None
    )
    data: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict)
    # Where clicking it goes, inside the app (e.g. "/community/friends").
    link: Mapped[str] = mapped_column(String(300), default="")
    created_at: Mapped[datetime] = mapped_column(UTCDateTime, default=utc_now)
    read_at: Mapped[datetime | None] = mapped_column(UTCDateTime, default=None)
