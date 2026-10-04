"""Learning Items, their questions, sources and memory state (docs/PROJECT_SPEC.md §23-27, §48).

A Concept is the knowledge area; a LearningItem is the atomic unit that is trained and
scheduled. Every LearningItem has exactly one ReviewState, shared by all its
QuestionFormulations, and nothing here schedules a Concept.
"""

import uuid
from datetime import datetime
from typing import Any

from sqlalchemy import (
    JSON,
    Boolean,
    ForeignKey,
    Integer,
    String,
    Text,
    UniqueConstraint,
    Uuid,
    false,
)
from sqlalchemy import Enum as SAEnum
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base
from app.db.types import UTCDateTime, utc_now
from app.models.enums import LearningItemRole, MemoryState, QuestionType


def _enum(enum_cls: Any, name: str, length: int = 30) -> SAEnum:
    # VARCHAR + CHECK like study_state, so adding a value later is a plain migration.
    return SAEnum(
        enum_cls,
        name=name,
        native_enum=False,
        create_constraint=True,
        length=length,
        validate_strings=True,
    )


class LearningItem(Base):
    __tablename__ = "learning_items"

    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=uuid.uuid4)
    concept_id: Mapped[uuid.UUID] = mapped_column(
        Uuid, ForeignKey("concepts.id", ondelete="CASCADE"), index=True
    )
    # Denormalized like Concept, so scoping and pools are single WHERE clauses.
    topic_id: Mapped[uuid.UUID] = mapped_column(
        Uuid, ForeignKey("topics.id", ondelete="CASCADE"), index=True
    )
    chapter_id: Mapped[uuid.UUID] = mapped_column(
        Uuid, ForeignKey("chapters.id", ondelete="CASCADE"), index=True
    )
    course_id: Mapped[uuid.UUID] = mapped_column(
        Uuid, ForeignKey("courses.id", ondelete="CASCADE"), index=True
    )
    title: Mapped[str] = mapped_column(String(200))
    # What the learner should be able to do, e.g. "Define the bank deposit and its effects".
    objective: Mapped[str] = mapped_column(String(2000), default="")
    # The reference answer, grounded in the sources; what answers are evaluated against.
    expected_knowledge: Mapped[str] = mapped_column(Text, default="")
    essential_points: Mapped[list[str]] = mapped_column(JSON, default=list)
    role: Mapped[LearningItemRole] = mapped_column(_enum(LearningItemRole, "learning_item_role"))
    # Whether it takes part in spaced repetition. Starts from the role (trainable roles: on) and
    # is the user's to change; turning it off keeps sources, questions and history.
    in_training: Mapped[bool] = mapped_column(Boolean, default=False, server_default=false())
    difficulty: Mapped[int] = mapped_column(Integer, default=3)  # 1 (easy) - 5 (hard)
    # TEXT: answered in words. DRAWING: answered by drawing, compared with the reference drawing
    # stored under drawings.reference_key(item); its media type is kept here.
    answer_format: Mapped[str] = mapped_column(String(16), default="TEXT", server_default="TEXT")
    # 1 Essential, 2 Important, 3 Extra: set by the user (enums.default_priority when generated).
    priority: Mapped[int] = mapped_column(Integer, default=2, server_default="2")
    # Marketplace courses: the id of the author's item this one mirrors (sync key), and the
    # author's priority. `priority` is then the acquirer's own, starting from the author's.
    origin_key: Mapped[str | None] = mapped_column(String(32), default=None)
    origin_priority: Mapped[int | None] = mapped_column(Integer, default=None)
    reference_drawing_type: Mapped[str | None] = mapped_column(String(32), default=None)
    order: Mapped[int] = mapped_column(Integer, default=0)
    # Item-level pause (spec §56); the schedule shift is in ReviewState.paused_at.
    paused: Mapped[bool] = mapped_column(Boolean, default=False, server_default=false())
    # What generated it (spec §73, §74); null for items the user wrote.
    ai_provider: Mapped[str | None] = mapped_column(String(50), default=None)
    ai_model: Mapped[str | None] = mapped_column(String(200), default=None)
    ai_model_version: Mapped[str | None] = mapped_column(String(200), default=None)
    prompt_version: Mapped[str | None] = mapped_column(String(100), default=None)
    created_at: Mapped[datetime] = mapped_column(UTCDateTime, default=utc_now)
    updated_at: Mapped[datetime] = mapped_column(UTCDateTime, default=utc_now, onupdate=utc_now)

    review_state: Mapped["ReviewState"] = relationship(
        back_populates="learning_item",
        uselist=False,
        cascade="all, delete-orphan",
        passive_deletes=True,
    )
    questions: Mapped[list["QuestionFormulation"]] = relationship(
        back_populates="learning_item",
        cascade="all, delete-orphan",
        passive_deletes=True,
        order_by="QuestionFormulation.created_at",
    )


class QuestionFormulation(Base):
    """One way of asking a Learning Item (spec §27). All formulations of an item share its one
    ReviewState, so rewording never resets or duplicates memory."""

    __tablename__ = "question_formulations"

    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=uuid.uuid4)
    learning_item_id: Mapped[uuid.UUID] = mapped_column(
        Uuid, ForeignKey("learning_items.id", ondelete="CASCADE"), index=True
    )
    course_id: Mapped[uuid.UUID] = mapped_column(
        Uuid, ForeignKey("courses.id", ondelete="CASCADE"), index=True
    )
    question_type: Mapped[QuestionType] = mapped_column(_enum(QuestionType, "question_type"))
    text: Mapped[str] = mapped_column(Text)
    # Used to rotate wording (spec §58): the least recently asked formulation goes next.
    times_asked: Mapped[int] = mapped_column(Integer, default=0)
    # A retrieval cue for this question (a keyword or the opening words of the reference), kept
    # once built so every reveal shows the same hint. Empty: none built yet.
    hint: Mapped[str | None] = mapped_column(String(300), default=None)
    last_asked_at: Mapped[datetime | None] = mapped_column(UTCDateTime, default=None)
    # Set when the AI wrote this formulation (spec §74); empty for the user's own.
    ai_provider: Mapped[str | None] = mapped_column(String(50), default=None)
    ai_model: Mapped[str | None] = mapped_column(String(200), default=None)
    ai_model_version: Mapped[str | None] = mapped_column(String(200), default=None)
    prompt_version: Mapped[str | None] = mapped_column(String(100), default=None)
    created_at: Mapped[datetime] = mapped_column(UTCDateTime, default=utc_now)

    learning_item: Mapped["LearningItem"] = relationship(back_populates="questions")


class LearningItemSource(Base):
    """The passages a Learning Item was generated from and is evaluated against (spec §18)."""

    __tablename__ = "learning_item_sources"
    __table_args__ = (UniqueConstraint("learning_item_id", "chunk_id"),)

    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=uuid.uuid4)
    learning_item_id: Mapped[uuid.UUID] = mapped_column(
        Uuid, ForeignKey("learning_items.id", ondelete="CASCADE"), index=True
    )
    chunk_id: Mapped[uuid.UUID] = mapped_column(
        Uuid, ForeignKey("document_chunks.id", ondelete="CASCADE"), index=True
    )
    course_id: Mapped[uuid.UUID] = mapped_column(
        Uuid, ForeignKey("courses.id", ondelete="CASCADE"), index=True
    )
    created_at: Mapped[datetime] = mapped_column(UTCDateTime, default=utc_now)


class ReviewState(Base):
    """A Learning Item's memory state (spec §23, §48), owned by the SchedulingPolicy
    (app/services/scheduling). Created NEW with its item; nothing else writes these fields."""

    __tablename__ = "review_states"

    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=uuid.uuid4)
    learning_item_id: Mapped[uuid.UUID] = mapped_column(
        Uuid, ForeignKey("learning_items.id", ondelete="CASCADE"), unique=True
    )
    course_id: Mapped[uuid.UUID] = mapped_column(
        Uuid, ForeignKey("courses.id", ondelete="CASCADE"), index=True
    )
    state: Mapped[MemoryState] = mapped_column(
        _enum(MemoryState, "memory_state", 20), default=MemoryState.NEW
    )
    level: Mapped[int] = mapped_column(Integer, default=0)
    interval_seconds: Mapped[int | None] = mapped_column(Integer, default=None)
    due_at: Mapped[datetime | None] = mapped_column(UTCDateTime, default=None, index=True)
    last_reviewed_at: Mapped[datetime | None] = mapped_column(UTCDateTime, default=None)
    review_count: Mapped[int] = mapped_column(Integer, default=0)
    successful_review_count: Mapped[int] = mapped_column(Integer, default=0)
    failed_review_count: Mapped[int] = mapped_column(Integer, default=0)
    lapse_count: Mapped[int] = mapped_column(Integer, default=0)
    hard_count: Mapped[int] = mapped_column(Integer, default=0)
    marked_hard: Mapped[bool] = mapped_column(Boolean, default=False, server_default=false())
    paused_at: Mapped[datetime | None] = mapped_column(UTCDateTime, default=None)
    scheduling_policy: Mapped[str] = mapped_column(String(50))
    scheduling_policy_version: Mapped[str] = mapped_column(String(20))
    updated_at: Mapped[datetime] = mapped_column(UTCDateTime, default=utc_now, onupdate=utc_now)

    learning_item: Mapped["LearningItem"] = relationship(back_populates="review_state")
