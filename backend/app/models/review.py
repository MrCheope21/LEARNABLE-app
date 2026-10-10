"""Review sessions, answers, AI evaluations and the scheduler's history
(docs/PROJECT_SPEC.md §83-86).

    Answer → Evaluation (AI evidence, never overwritten) → ReviewOutcomeResolver →
    resolved_outcome → optional user override → final_outcome → SchedulingPolicy → Review row

Everything is kept, so a later reader can tell what the AI said, what the rules made of it,
what the user changed, and what the scheduler did.
"""

import uuid
from datetime import datetime
from typing import Any

from sqlalchemy import (
    JSON,
    Boolean,
    Float,
    ForeignKey,
    Index,
    Integer,
    String,
    Text,
    Uuid,
    false,
)
from sqlalchemy import Enum as SAEnum
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base
from app.db.types import UTCDateTime, utc_now
from app.models.enums import (
    AnswerMethod,
    EvaluationClassification,
    EvaluationStatus,
    MemoryState,
    ReviewOutcome,
    SelectionMode,
    SessionIntent,
)


def _enum(enum_cls: Any, name: str, length: int = 30) -> SAEnum:
    return SAEnum(
        enum_cls,
        name=name,
        native_enum=False,
        create_constraint=True,
        length=length,
        validate_strings=True,
    )


class ReviewSession(Base):
    """One sitting. Keeps everything needed to reconstruct how its pool was chosen (§83)."""

    __tablename__ = "review_sessions"

    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=uuid.uuid4)
    user_id: Mapped[uuid.UUID] = mapped_column(
        Uuid, ForeignKey("users.id", ondelete="CASCADE"), index=True
    )
    course_id: Mapped[uuid.UUID] = mapped_column(
        Uuid, ForeignKey("courses.id", ondelete="CASCADE"), index=True
    )
    intent: Mapped[SessionIntent] = mapped_column(_enum(SessionIntent, "session_intent"))
    selection_mode: Mapped[SelectionMode] = mapped_column(_enum(SelectionMode, "selection_mode"))
    # Whether answers go through the SchedulingPolicy: LEARN and SCHEDULED_REVIEW always,
    # PRACTICE only if the user opted in, EXAM never (for now).
    affects_schedule: Mapped[bool] = mapped_column(Boolean)
    # Scope the pool was drawn from (all optional within the Course).
    chapter_id: Mapped[uuid.UUID | None] = mapped_column(Uuid, default=None)
    topic_id: Mapped[uuid.UUID | None] = mapped_column(Uuid, default=None)
    concept_ids: Mapped[list[str] | None] = mapped_column(JSON, default=None)
    # The pool, in order. LEARN appends an item again when it isn't encoded yet.
    item_ids: Mapped[list[str]] = mapped_column(JSON)
    position: Mapped[int] = mapped_column(Integer, default=0)
    started_at: Mapped[datetime] = mapped_column(UTCDateTime, default=utc_now)
    ended_at: Mapped[datetime | None] = mapped_column(UTCDateTime, default=None)


class Answer(Base):
    """What the user answered (spec §84), and how it was finally graded (task §5.6)."""

    __tablename__ = "answers"
    # Dashboard: the user's recent completed attempts, and each Course's last study time.
    __table_args__ = (
        Index("ix_answers_user_id_finalized_at", "user_id", "finalized_at"),
        Index("ix_answers_course_id_finalized_at", "course_id", "finalized_at"),
    )

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
    learning_item_id: Mapped[uuid.UUID] = mapped_column(
        Uuid, ForeignKey("learning_items.id", ondelete="CASCADE"), index=True
    )
    question_formulation_id: Mapped[uuid.UUID] = mapped_column(
        Uuid, ForeignKey("question_formulations.id", ondelete="CASCADE")
    )
    intent: Mapped[SessionIntent] = mapped_column(_enum(SessionIntent, "answer_intent"))
    method: Mapped[AnswerMethod] = mapped_column(_enum(AnswerMethod, "answer_method", 10))
    text: Mapped[str] = mapped_column(Text)
    # From the ReviewOutcomeResolver; null when the evaluation can't decide (insufficient
    # context, uncertain, failed): the user grades it.
    resolved_outcome: Mapped[ReviewOutcome | None] = mapped_column(
        _enum(ReviewOutcome, "resolved_outcome", 10), default=None
    )
    resolver_version: Mapped[str | None] = mapped_column(String(50), default=None)
    # The user's own grade; never replaces the evaluation or the resolved outcome.
    override_outcome: Mapped[ReviewOutcome | None] = mapped_column(
        _enum(ReviewOutcome, "override_outcome", 10), default=None
    )
    override_note: Mapped[str | None] = mapped_column(String(500), default=None)
    overridden_at: Mapped[datetime | None] = mapped_column(UTCDateTime, default=None)
    # What counts: the override if any, else the resolved outcome.
    final_outcome: Mapped[ReviewOutcome | None] = mapped_column(
        _enum(ReviewOutcome, "final_outcome", 10), default=None
    )
    # When the answer first got a final outcome: the moment it became a completed attempt for
    # activity, streak and goal. Set once; a later override doesn't move it.
    finalized_at: Mapped[datetime | None] = mapped_column(UTCDateTime, default=None)
    # CONSOLIDATION sessions: which of the item's three rounds this answer was (1-3).
    consolidation_round: Mapped[int | None] = mapped_column(Integer, default=None)
    # A hint was revealed for this attempt before the answer was submitted (halves its XP).
    hint_used: Mapped[bool] = mapped_column(Boolean, default=False, server_default=false())
    # A drawn answer: its media type; the image is stored under drawings.answer_key(answer).
    drawing_type: Mapped[str | None] = mapped_column(String(32), default=None)
    # Green on at least 3 of the 4 scores but not a GOOD: the answer waits for the student to
    # review the reference answer and repeat it (services/evaluation/resolver.py).
    repeat_offered: Mapped[bool] = mapped_column(Boolean, default=False, server_default=false())
    repeat_text: Mapped[str | None] = mapped_column(Text, default=None)
    repeated_at: Mapped[datetime | None] = mapped_column(UTCDateTime, default=None)
    created_at: Mapped[datetime] = mapped_column(UTCDateTime, default=utc_now)


class Evaluation(Base):
    """One AI evaluation attempt of an Answer (spec §85). Immutable once written; a retry after
    a failure is a new row."""

    __tablename__ = "evaluations"
    __table_args__ = (Index("ix_evaluations_course_id_created_at", "course_id", "created_at"),)

    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=uuid.uuid4)
    answer_id: Mapped[uuid.UUID] = mapped_column(
        Uuid, ForeignKey("answers.id", ondelete="CASCADE"), index=True
    )
    course_id: Mapped[uuid.UUID] = mapped_column(
        Uuid, ForeignKey("courses.id", ondelete="CASCADE"), index=True
    )
    status: Mapped[EvaluationStatus] = mapped_column(_enum(EvaluationStatus, "evaluation_status"))
    error_message: Mapped[str | None] = mapped_column(String(500), default=None)
    classification: Mapped[EvaluationClassification | None] = mapped_column(
        _enum(EvaluationClassification, "evaluation_classification"), default=None
    )
    correctness: Mapped[float | None] = mapped_column(Float, default=None)
    completeness: Mapped[float | None] = mapped_column(Float, default=None)
    conceptual_understanding: Mapped[float | None] = mapped_column(Float, default=None)
    precision: Mapped[float | None] = mapped_column(Float, default=None)
    confidence: Mapped[float | None] = mapped_column(Float, default=None)
    correct_points: Mapped[list[str]] = mapped_column(JSON, default=list)
    missing_points: Mapped[list[str]] = mapped_column(JSON, default=list)
    # Stored against the answer → item → Concept, so later question selection can target them.
    misconceptions: Mapped[list[str]] = mapped_column(JSON, default=list)
    source_corrections: Mapped[list[str]] = mapped_column(JSON, default=list)
    context_sufficient: Mapped[bool | None] = mapped_column(Boolean, default=None)
    feedback: Mapped[str] = mapped_column(Text, default="")
    # Set on a second opinion: the student's objection to the first evaluation, which the
    # evaluator was shown. Such a row never decides the outcome, the schedule or XP.
    user_argument: Mapped[str | None] = mapped_column(String(1000), default=None)
    ai_provider: Mapped[str | None] = mapped_column(String(50), default=None)
    ai_model: Mapped[str | None] = mapped_column(String(200), default=None)
    ai_model_version: Mapped[str | None] = mapped_column(String(200), default=None)
    prompt_version: Mapped[str | None] = mapped_column(String(100), default=None)
    created_at: Mapped[datetime] = mapped_column(UTCDateTime, default=utc_now)


class Review(Base):
    """One scheduling transition (spec §86): append-only. A user override of an already
    scheduled answer adds a row that `supersedes` the original; nothing is rewritten."""

    __tablename__ = "reviews"

    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=uuid.uuid4)
    course_id: Mapped[uuid.UUID] = mapped_column(
        Uuid, ForeignKey("courses.id", ondelete="CASCADE"), index=True
    )
    learning_item_id: Mapped[uuid.UUID] = mapped_column(
        Uuid, ForeignKey("learning_items.id", ondelete="CASCADE"), index=True
    )
    answer_id: Mapped[uuid.UUID] = mapped_column(
        Uuid, ForeignKey("answers.id", ondelete="CASCADE"), index=True
    )
    intent: Mapped[SessionIntent] = mapped_column(_enum(SessionIntent, "review_intent"))
    outcome: Mapped[ReviewOutcome] = mapped_column(_enum(ReviewOutcome, "review_outcome", 10))
    previous_state: Mapped[MemoryState] = mapped_column(_enum(MemoryState, "previous_state", 20))
    previous_level: Mapped[int] = mapped_column(Integer)
    previous_due_at: Mapped[datetime | None] = mapped_column(UTCDateTime, default=None)
    next_state: Mapped[MemoryState] = mapped_column(_enum(MemoryState, "next_state", 20))
    next_level: Mapped[int] = mapped_column(Integer)
    next_due_at: Mapped[datetime | None] = mapped_column(UTCDateTime, default=None)
    reviewed_at: Mapped[datetime] = mapped_column(UTCDateTime)
    lateness_seconds: Mapped[int] = mapped_column(Integer, default=0)
    scheduling_policy: Mapped[str] = mapped_column(String(50))
    scheduling_policy_version: Mapped[str] = mapped_column(String(20))
    # The complete memory state before the transition, so an override can be replayed from
    # exactly there.
    previous_snapshot: Mapped[dict[str, Any]] = mapped_column(JSON)
    supersedes_review_id: Mapped[uuid.UUID | None] = mapped_column(
        Uuid, ForeignKey("reviews.id", ondelete="SET NULL"), default=None
    )
    superseded: Mapped[bool] = mapped_column(Boolean, default=False, server_default=false())
    created_at: Mapped[datetime] = mapped_column(UTCDateTime, default=utc_now)
