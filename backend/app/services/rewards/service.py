"""Recording XP and study activity when an answer is finalized (docs/XP_AND_ACTIVITY.md).

Called from the review service in the same transaction as the answer's outcome and schedule
change, so an attempt, its award and its activity commit or roll back together. Nothing here
decides correctness itself: it reads the ReviewOutcomeResolver's outcome and the AI's
classification, and the client never supplies an amount or asserts correctness.
"""

import uuid
from dataclasses import dataclass
from datetime import date, datetime
from typing import Any
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from sqlalchemy import func, select
from sqlalchemy.dialects import postgresql, sqlite
from sqlalchemy.orm import Session

from app.models.enums import (
    EvaluationClassification,
    MemoryState,
    ReviewOutcome,
    SessionIntent,
    XpReason,
)
from app.models.learning import LearningItem
from app.models.review import Answer, ReviewSession
from app.models.rewards import DailyActivity, HintReveal, ItemSuccessCounter, XpAward
from app.models.user import User
from app.services.rewards import policy

UTC_ZONE = ZoneInfo("UTC")


def zone(name: str | None) -> ZoneInfo:
    """The user's zone; an unknown or empty name falls back to UTC rather than failing."""
    try:
        return ZoneInfo(name) if name else UTC_ZONE
    except (ZoneInfoNotFoundError, ValueError):
        return UTC_ZONE


def is_valid_zone(name: str) -> bool:
    try:
        ZoneInfo(name)
    except (ZoneInfoNotFoundError, ValueError):
        return False
    return True


def local_day(timezone_name: str | None, moment: datetime) -> date:
    return moment.astimezone(zone(timezone_name)).date()


@dataclass(frozen=True)
class Occasion:
    """What makes an attempt XP-eligible, and the key that makes it unique."""

    reason: XpReason
    key: str


def occasion_for(
    db: Session,
    session: ReviewSession,
    item: LearningItem,
    *,
    state_before: MemoryState,
    due_before: datetime | None,
    at: datetime,
) -> Occasion | None:
    """Eligible attempts (§3): an item's first three consolidation rounds, and a scheduled review
    of an item that was due. Learning with the answer shown first (LEARN), practice and exams
    earn nothing."""
    if session.intent is SessionIntent.CONSOLIDATION:
        done = db.scalar(
            select(func.count())
            .select_from(XpAward)
            .where(XpAward.learning_item_id == item.id, XpAward.reason == XpReason.INITIAL)
        )
        attempt = (done or 0) + 1
        if attempt > policy.INITIAL_ROUNDS:
            return None
        return Occasion(XpReason.INITIAL, f"initial:{attempt}")
    if session.intent is SessionIntent.SCHEDULED_REVIEW:
        if state_before is MemoryState.NEW or due_before is None or _aware(due_before) > at:
            return None
        # One award per due date: a second answer before the next due date can't earn again.
        return Occasion(XpReason.SCHEDULED_REVIEW, f"review:{_aware(due_before).isoformat()}")
    return None


def record_attempt(
    db: Session,
    user: User,
    session: ReviewSession,
    item: LearningItem,
    answer: Answer,
    *,
    occasion: Occasion | None,
    classification: EvaluationClassification | None,
    at: datetime,
    self_grade: ReviewOutcome | None = None,
) -> XpAward | None:
    """The attempt is complete (first final outcome). Writes its award (when eligible) and its
    day's activity. Returns the award row, or None when the attempt wasn't eligible.
    `classification` is the AI evaluation's; `self_grade` the student's own grade when they
    graded it themselves, which earns XP like an AI-correct answer."""
    award: XpAward | None = None
    if occasion is not None:
        correct = policy.is_correct(classification, answer.resolved_outcome, self_grade)
        ordinal = _count_success(db, user.id, item) if correct else None
        base = policy.base_xp(ordinal) if ordinal is not None else 0
        xp = policy.awarded_xp(ordinal, answer.hint_used) if ordinal is not None else 0
        award = XpAward(
            user_id=user.id,
            course_id=item.course_id,
            learning_item_id=item.id,
            answer_id=answer.id,
            session_id=session.id,
            reason=occasion.reason,
            occasion_key=occasion.key,
            correct=correct,
            ordinal=ordinal,
            base_xp=base,
            hint_used=answer.hint_used,
            xp=xp,
            policy_version=policy.XP_POLICY_VERSION,
            awarded_at=at,
        )
        db.add(award)
    _add_activity(db, user, at, xp=award.xp if award else 0)
    return award


def regrade(db: Session, user: User, item: LearningItem, answer: Answer, at: datetime) -> None:
    """The student changed the grade of an answer already decided (e.g. the AI said AGAIN, the
    student says GOOD). A success now earns the XP the answer didn't get; an answer is rewarded
    at most once, and XP already earned is never taken back."""
    award = award_for(db, answer.id)
    if award is None or award.correct:
        return
    if not policy.is_correct(None, None, self_grade=answer.final_outcome):
        return
    award.correct = True
    award.ordinal = _count_success(db, user.id, item)
    award.base_xp = policy.base_xp(award.ordinal)
    award.xp = policy.awarded_xp(award.ordinal, answer.hint_used)
    _add_activity(db, user, at, xp=award.xp, attempts=0)


def _insert(db: Session, table: Any) -> Any:
    dialect = db.get_bind().dialect.name
    return (postgresql.insert if dialect == "postgresql" else sqlite.insert)(table)


def _count_success(db: Session, user_id: uuid.UUID, item: LearningItem) -> int:
    """+1 on the item's success counter, atomically (one INSERT … ON CONFLICT DO UPDATE …
    RETURNING): two concurrent correct answers can't read the same count."""
    stmt = (
        _insert(db, ItemSuccessCounter)
        .values(
            id=uuid.uuid4(),
            user_id=user_id,
            course_id=item.course_id,
            learning_item_id=item.id,
            successful_answers=1,
        )
        .on_conflict_do_update(
            index_elements=["learning_item_id"],
            set_={"successful_answers": ItemSuccessCounter.successful_answers + 1},
        )
        .returning(ItemSuccessCounter.successful_answers)
    )
    return int(db.execute(stmt).scalar_one())


def _add_activity(db: Session, user: User, at: datetime, *, xp: int, attempts: int = 1) -> None:
    stmt = (
        _insert(db, DailyActivity)
        .values(
            id=uuid.uuid4(),
            user_id=user.id,
            day=local_day(user.timezone, at),
            attempts=attempts,
            xp=xp,
        )
        .on_conflict_do_update(
            index_elements=["user_id", "day"],
            set_={
                "attempts": DailyActivity.attempts + attempts,
                "xp": DailyActivity.xp + xp,
            },
        )
    )
    db.execute(stmt)


# --- What the next answer could earn, shown before answering ---


@dataclass(frozen=True)
class Potential:
    eligible: bool
    # The ordinal and XP a correct answer would get now; 0 when not eligible.
    ordinal: int
    xp: int
    xp_with_hint: int


def potential(db: Session, session: ReviewSession, item: LearningItem, at: datetime) -> Potential:
    state = item.review_state
    occasion = occasion_for(
        db, session, item, state_before=state.state, due_before=state.due_at, at=at
    )
    if occasion is None:
        return Potential(eligible=False, ordinal=0, xp=0, xp_with_hint=0)
    done = db.scalar(
        select(ItemSuccessCounter.successful_answers).where(
            ItemSuccessCounter.learning_item_id == item.id
        )
    )
    ordinal = (done or 0) + 1
    return Potential(
        eligible=True,
        ordinal=ordinal,
        xp=policy.awarded_xp(ordinal, hint_used=False),
        xp_with_hint=policy.awarded_xp(ordinal, hint_used=True),
    )


def session_xp(db: Session, session_id: uuid.UUID) -> int:
    total = db.scalar(
        select(func.coalesce(func.sum(XpAward.xp), 0)).where(XpAward.session_id == session_id)
    )
    return int(total or 0)


def award_for(db: Session, answer_id: uuid.UUID) -> XpAward | None:
    return db.scalar(select(XpAward).where(XpAward.answer_id == answer_id))


def hint_for_slot(db: Session, session_id: uuid.UUID, slot: int) -> HintReveal | None:
    return db.scalar(
        select(HintReveal).where(HintReveal.session_id == session_id, HintReveal.slot == slot)
    )


def _aware(value: datetime) -> datetime:
    return value if value.tzinfo else value.replace(tzinfo=UTC_ZONE)
