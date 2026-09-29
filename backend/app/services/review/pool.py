"""Review pools: which Learning Items a session may ask (docs/PROJECT_SPEC.md §49-51, §56).

Eligible for any session: in this Course, in training, with a question, not paused, its
Concept ACTIVE, and no paused Topic/Chapter/Course above it (spec §21, §50). Never unstudied,
inactive or paused material.

Intent decides the memory states a pool may draw from:
- LEARN: NEW items only (not encoded yet), in course order.
- SCHEDULED_REVIEW: encoded items that are due, most overdue first.
- PRACTICE: encoded items, by the chosen selection mode.
EXAM (Phase 15) is not available yet.
"""

import uuid
from datetime import datetime, timedelta

from sqlalchemy import Select, exists, func, select
from sqlalchemy.orm import Session

from app.core.errors import InvalidRequestError
from app.models.course import Chapter, Concept, Course, Topic
from app.models.enums import MemoryState, ReviewOutcome, SelectionMode, SessionIntent, StudyState
from app.models.learning import LearningItem, QuestionFormulation, ReviewState
from app.models.review import Answer

# Which selection modes each intent accepts; the first is the default.
MODES: dict[SessionIntent, tuple[SelectionMode, ...]] = {
    SessionIntent.LEARN: (SelectionMode.NEW, SelectionMode.SELECTED),
    SessionIntent.SCHEDULED_REVIEW: (SelectionMode.DUE,),
    SessionIntent.PRACTICE: (
        SelectionMode.COURSE_ORDER,
        SelectionMode.RANDOM,
        SelectionMode.WEAK,
        SelectionMode.RECENTLY_FAILED,
        SelectionMode.MARKED_HARD,
        SelectionMode.SELECTED,
    ),
    # Built by app/services/review/consolidation.py, never through select_pool.
    SessionIntent.CONSOLIDATION: (SelectionMode.CONSOLIDATION,),
}
RECENTLY_FAILED_WINDOW = timedelta(days=7)


def resolve_mode(intent: SessionIntent, requested: SelectionMode | None) -> SelectionMode:
    if intent is SessionIntent.EXAM:
        raise InvalidRequestError(
            "Exam sessions aren't available yet.", details={"reason": "exam_not_available"}
        )
    allowed = MODES[intent]
    if requested is None:
        return allowed[0]
    if requested not in allowed:
        raise InvalidRequestError(
            f"{intent.value} sessions can't use selection mode {requested.value}.",
            details={"reason": "mode_not_allowed", "allowed": [m.value for m in allowed]},
        )
    return requested


def eligible_items(course_id: uuid.UUID) -> Select[tuple[LearningItem]]:
    """Every item that may be asked at all in this Course, in course order."""
    return _eligible().where(LearningItem.course_id == course_id, Concept.course_id == course_id)


def eligible_items_for_user(user_id: uuid.UUID) -> Select[tuple[LearningItem]]:
    """The same eligibility across all of one user's Courses (dashboard aggregates)."""
    return _eligible().where(Course.user_id == user_id)


def _eligible() -> Select[tuple[LearningItem]]:
    return (
        select(LearningItem)
        .join(ReviewState, ReviewState.learning_item_id == LearningItem.id)
        .join(Concept, Concept.id == LearningItem.concept_id)
        .join(Topic, Topic.id == LearningItem.topic_id)
        .join(Chapter, Chapter.id == LearningItem.chapter_id)
        .join(Course, Course.id == LearningItem.course_id)
        .where(
            Concept.course_id == LearningItem.course_id,
            LearningItem.in_training.is_(True),
            LearningItem.paused.is_(False),
            Concept.study_state == StudyState.ACTIVE,
            Topic.paused.is_(False),
            Chapter.paused.is_(False),
            Course.paused.is_(False),
            exists().where(QuestionFormulation.learning_item_id == LearningItem.id),
        )
        .order_by(
            Chapter.order,
            Chapter.created_at,
            Topic.order,
            Topic.created_at,
            Concept.order,
            Concept.created_at,
            LearningItem.order,
            LearningItem.created_at,
        )
    )


def select_pool(
    db: Session,
    course_id: uuid.UUID,
    intent: SessionIntent,
    mode: SelectionMode,
    *,
    chapter_id: uuid.UUID | None,
    topic_id: uuid.UUID | None,
    concept_ids: list[uuid.UUID] | None,
    item_ids: list[uuid.UUID] | None,
    limit: int,
    now: datetime,
) -> list[uuid.UUID]:
    stmt = eligible_items(course_id)
    if chapter_id is not None:
        stmt = stmt.where(LearningItem.chapter_id == chapter_id)
    if topic_id is not None:
        stmt = stmt.where(LearningItem.topic_id == topic_id)
    if concept_ids:
        stmt = stmt.where(LearningItem.concept_id.in_(concept_ids))

    if intent is SessionIntent.LEARN:
        stmt = stmt.where(ReviewState.state == MemoryState.NEW)
    else:
        stmt = stmt.where(ReviewState.state != MemoryState.NEW)

    if mode is SelectionMode.DUE:
        stmt = stmt.where(ReviewState.due_at <= now, ReviewState.paused_at.is_(None))
        stmt = stmt.order_by(None).order_by(ReviewState.due_at, LearningItem.id)
    elif mode is SelectionMode.WEAK:
        stmt = stmt.where(
            (ReviewState.lapse_count > 0)
            | (ReviewState.failed_review_count > 0)
            | ReviewState.marked_hard.is_(True)
            | (ReviewState.state == MemoryState.RELEARNING)
        )
        stmt = stmt.order_by(None).order_by(
            ReviewState.lapse_count.desc(),
            ReviewState.failed_review_count.desc(),
            ReviewState.level,
            LearningItem.id,
        )
    elif mode is SelectionMode.MARKED_HARD:
        stmt = stmt.where(ReviewState.marked_hard.is_(True))
    elif mode is SelectionMode.RECENTLY_FAILED:
        last_failed = (
            select(Answer.learning_item_id, func.max(Answer.created_at).label("failed_at"))
            .where(
                Answer.course_id == course_id,
                Answer.final_outcome == ReviewOutcome.AGAIN,
                Answer.created_at >= now - RECENTLY_FAILED_WINDOW,
            )
            .group_by(Answer.learning_item_id)
            .subquery()
        )
        stmt = stmt.join(last_failed, last_failed.c.learning_item_id == LearningItem.id)
        stmt = stmt.order_by(None).order_by(last_failed.c.failed_at.desc(), LearningItem.id)
    elif mode is SelectionMode.SELECTED:
        wanted = list(dict.fromkeys(item_ids or []))
        if not wanted:
            raise InvalidRequestError(
                "Selection mode SELECTED needs learning_item_ids.",
                details={"reason": "no_items_selected"},
            )
        found = {item.id for item in db.scalars(stmt.where(LearningItem.id.in_(wanted)))}
        return [i for i in wanted if i in found][:limit]

    elif mode is SelectionMode.RANDOM:
        # random() exists in both SQLite and PostgreSQL. The drawn order is stored in the
        # session, so the pool stays reconstructible.
        stmt = stmt.order_by(None).order_by(func.random())
    return [item.id for item in db.scalars(stmt.limit(limit))]
