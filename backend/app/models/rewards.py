"""Experience points, hints and daily activity (docs/XP_AND_ACTIVITY.md).

Rewards sit beside the learning loop and never feed back into it: nothing here is read by the
SchedulingPolicy, the ReviewOutcomeResolver or mastery estimates.

    Answer finalized (first final outcome)
      → XpAward row (one per answer, decided once, audited)
      → ItemSuccessCounter (+1 when the attempt was correct)
      → DailyActivity (+1 attempt, +XP on the user's local day)
"""

import uuid
from datetime import date, datetime

from sqlalchemy import (
    Boolean,
    Date,
    ForeignKey,
    Index,
    Integer,
    String,
    UniqueConstraint,
    Uuid,
    false,
)
from sqlalchemy import Enum as SAEnum
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base
from app.db.types import UTCDateTime, utc_now
from app.models.enums import XpReason


class ItemSuccessCounter(Base):
    """How many XP-counted correct answers a Learning Item has had: the n in "the nth correct
    answer earns min(10n, 150)". Shared by all the item's question formulations; independent of
    streaks and of the item's memory state."""

    __tablename__ = "item_success_counters"

    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=uuid.uuid4)
    user_id: Mapped[uuid.UUID] = mapped_column(
        Uuid, ForeignKey("users.id", ondelete="CASCADE"), index=True
    )
    course_id: Mapped[uuid.UUID] = mapped_column(
        Uuid, ForeignKey("courses.id", ondelete="CASCADE"), index=True
    )
    learning_item_id: Mapped[uuid.UUID] = mapped_column(
        Uuid, ForeignKey("learning_items.id", ondelete="CASCADE"), unique=True
    )
    successful_answers: Mapped[int] = mapped_column(Integer, default=0)
    updated_at: Mapped[datetime] = mapped_column(UTCDateTime, default=utc_now, onupdate=utc_now)


class XpAward(Base):
    """The XP decision for one eligible attempt, correct or not (0 XP), written once when the
    answer is first finalized. The unique constraints make a duplicate award impossible even
    under concurrent requests: one row per answer, per occasion (an item's consolidation
    round, or one due date of a scheduled review), and per success ordinal."""

    __tablename__ = "xp_awards"
    __table_args__ = (
        UniqueConstraint("learning_item_id", "occasion_key"),
        UniqueConstraint("learning_item_id", "ordinal"),
        Index("ix_xp_awards_user_id_awarded_at", "user_id", "awarded_at"),
    )

    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=uuid.uuid4)
    user_id: Mapped[uuid.UUID] = mapped_column(
        Uuid, ForeignKey("users.id", ondelete="CASCADE"), index=True
    )
    course_id: Mapped[uuid.UUID] = mapped_column(
        Uuid, ForeignKey("courses.id", ondelete="CASCADE"), index=True
    )
    learning_item_id: Mapped[uuid.UUID] = mapped_column(
        Uuid, ForeignKey("learning_items.id", ondelete="CASCADE"), index=True
    )
    answer_id: Mapped[uuid.UUID] = mapped_column(
        Uuid, ForeignKey("answers.id", ondelete="CASCADE"), unique=True
    )
    session_id: Mapped[uuid.UUID] = mapped_column(
        Uuid, ForeignKey("review_sessions.id", ondelete="CASCADE"), index=True
    )
    reason: Mapped[XpReason] = mapped_column(
        SAEnum(
            XpReason,
            name="xp_reason",
            native_enum=False,
            create_constraint=True,
            length=30,
            validate_strings=True,
        )
    )
    # "initial:2" (the item's second consolidation round) or "review:<due date ISO>".
    occasion_key: Mapped[str] = mapped_column(String(80))
    # Whether the canonical outcome counted as correct (docs/XP_AND_ACTIVITY.md §2).
    correct: Mapped[bool] = mapped_column(Boolean)
    # The item's success count including this answer; null when it wasn't correct.
    ordinal: Mapped[int | None] = mapped_column(Integer, default=None)
    base_xp: Mapped[int] = mapped_column(Integer, default=0)
    hint_used: Mapped[bool] = mapped_column(Boolean, default=False, server_default=false())
    xp: Mapped[int] = mapped_column(Integer, default=0)
    policy_version: Mapped[str] = mapped_column(String(20))
    awarded_at: Mapped[datetime] = mapped_column(UTCDateTime, default=utc_now)


class DailyActivity(Base):
    """Completed attempts and XP per user per local calendar day (the user's timezone when the
    attempt was finalized). The single source for streaks, the daily goal, XP today and the
    activity calendar, so they always agree."""

    __tablename__ = "daily_activity"
    __table_args__ = (UniqueConstraint("user_id", "day"),)

    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=uuid.uuid4)
    user_id: Mapped[uuid.UUID] = mapped_column(
        Uuid, ForeignKey("users.id", ondelete="CASCADE"), index=True
    )
    day: Mapped[date] = mapped_column(Date)
    attempts: Mapped[int] = mapped_column(Integer, default=0)
    xp: Mapped[int] = mapped_column(Integer, default=0)


class HintReveal(Base):
    """A hint shown for one question slot of a session, before the answer. Stored server-side
    so reloading or leaving the page can't undo it; the answer to that slot is marked
    hint-assisted."""

    __tablename__ = "hint_reveals"
    __table_args__ = (UniqueConstraint("session_id", "slot"),)

    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=uuid.uuid4)
    user_id: Mapped[uuid.UUID] = mapped_column(
        Uuid, ForeignKey("users.id", ondelete="CASCADE"), index=True
    )
    course_id: Mapped[uuid.UUID] = mapped_column(
        Uuid, ForeignKey("courses.id", ondelete="CASCADE"), index=True
    )
    session_id: Mapped[uuid.UUID] = mapped_column(
        Uuid, ForeignKey("review_sessions.id", ondelete="CASCADE"), index=True
    )
    # The session position the hint was shown at.
    slot: Mapped[int] = mapped_column(Integer)
    learning_item_id: Mapped[uuid.UUID] = mapped_column(
        Uuid, ForeignKey("learning_items.id", ondelete="CASCADE"), index=True
    )
    question_formulation_id: Mapped[uuid.UUID] = mapped_column(
        Uuid, ForeignKey("question_formulations.id", ondelete="CASCADE")
    )
    text: Mapped[str] = mapped_column(String(300))
    revealed_at: Mapped[datetime] = mapped_column(UTCDateTime, default=utc_now)
