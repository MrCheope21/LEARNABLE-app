"""Consolidation: "I have studied this concept" (docs/SCHEDULING.md §4a).

Reading a Concept isn't studying it until the user says so; activating it isn't either. When
they say so, its NEW Learning Items are consolidated in batches: each item's question three
times in a row, feedback after each round. A batch is a stored CONSOLIDATION session, so an
interruption resumes exactly where it stopped, and asking again resumes the unfinished batch
instead of starting over (rewarded rounds are never replayed).
"""

import uuid

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.errors import ConflictError
from app.db.types import utc_now
from app.models.course import Concept
from app.models.enums import MemoryState, SelectionMode, SessionIntent, StudyState
from app.models.learning import LearningItem, ReviewState
from app.models.review import ReviewSession
from app.schemas.review import ConsolidationPlan
from app.services.courses.service import get_owned_concept
from app.services.review import service
from app.services.review.pool import eligible_items
from app.services.rewards.policy import ROUNDS_PER_ITEM

# Items per batch: 5 items x 3 rounds = 15 answers, a sitting of reasonable length.
BATCH_ITEMS = 5


def plan(db: Session, user_id: uuid.UUID, concept_id: uuid.UUID) -> ConsolidationPlan:
    concept = get_owned_concept(db, user_id, concept_id)
    unfinished = _unfinished(db, user_id, concept)
    waiting = _new_items(db, concept, excluding=unfinished)
    batch = min(len(waiting), BATCH_ITEMS)
    db.commit()  # _unfinished may have closed sessions whose remaining items are gone
    return ConsolidationPlan(
        concept_id=concept.id,
        concept_active=concept.study_state is StudyState.ACTIVE,
        unfinished=service.session_read(db, unfinished) if unfinished else None,
        unfinished_items=len(set(unfinished.item_ids)) if unfinished else 0,
        new_items=len(waiting),
        batch_items=batch,
        rounds_per_item=ROUNDS_PER_ITEM,
        answers_in_batch=batch * ROUNDS_PER_ITEM,
        remaining_after_batch=len(waiting) - batch,
    )


def start(db: Session, user_id: uuid.UUID, concept_id: uuid.UUID) -> ReviewSession:
    """Resumes this Concept's unfinished batch if there is one; otherwise starts the next batch
    of NEW items. 409 when there's nothing left to consolidate."""
    concept = get_owned_concept(db, user_id, concept_id)
    unfinished = _unfinished(db, user_id, concept)
    if unfinished is not None:
        db.commit()
        return unfinished
    items = _new_items(db, concept, excluding=None)[:BATCH_ITEMS]
    if not items:
        db.commit()
        raise ConflictError(
            "Nothing in this concept is waiting to be consolidated.",
            details={
                "reason": "nothing_to_consolidate",
                "concept_active": concept.study_state is StudyState.ACTIVE,
            },
        )
    session = ReviewSession(
        user_id=user_id,
        course_id=concept.course_id,
        intent=SessionIntent.CONSOLIDATION,
        selection_mode=SelectionMode.CONSOLIDATION,
        affects_schedule=True,
        chapter_id=concept.chapter_id,
        topic_id=concept.topic_id,
        concept_ids=[str(concept.id)],
        # Three consecutive slots per item: its rounds in immediate succession.
        item_ids=[str(item_id) for item_id in items for _ in range(ROUNDS_PER_ITEM)],
        started_at=utc_now(),
    )
    db.add(session)
    db.commit()
    db.refresh(session)
    return session


def _unfinished(db: Session, user_id: uuid.UUID, concept: Concept) -> ReviewSession | None:
    candidates = db.scalars(
        select(ReviewSession)
        .where(
            ReviewSession.user_id == user_id,
            ReviewSession.course_id == concept.course_id,
            ReviewSession.intent == SessionIntent.CONSOLIDATION,
            ReviewSession.ended_at.is_(None),
        )
        .order_by(ReviewSession.started_at.desc())
    )
    for session in candidates:
        if str(concept.id) not in (session.concept_ids or []):
            continue
        # Advances past items that can't be asked anymore, and ends the session if none can.
        if service.current_item(db, session) is not None:
            return session
    return None


def _new_items(db: Session, concept: Concept, excluding: ReviewSession | None) -> list[uuid.UUID]:
    """The Concept's items waiting for consolidation: NEW, in training, askable, in course
    order. An unfinished batch's items are its own."""
    skip = {uuid.UUID(i) for i in excluding.item_ids} if excluding else set()
    stmt = (
        eligible_items(concept.course_id)
        .where(LearningItem.concept_id == concept.id, ReviewState.state == MemoryState.NEW)
        .with_only_columns(LearningItem.id)
    )
    return [item_id for item_id in db.scalars(stmt) if item_id not in skip]
