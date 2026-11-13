"""Reviewing without a network (docs/OFFLINE.md).

`pack`: the questions of a course that are due now or within the next days, with their
reference answers, for the app to keep on the device. Offline there is no AI: the student reads
the question, may write an answer, sees the reference and grades themselves.

`sync`: when the device is back online it sends those self-graded answers with the moment each
was given. Each one is applied as a scheduled review at that moment, exactly like a self-graded
answer online (schedule, history, XP, the day's activity). An item reviewed in the meantime on
another device, or no longer reviewable, is skipped and reported, never applied twice: the
client's `client_id` makes a resend harmless.
"""

import uuid
from datetime import UTC, datetime, timedelta

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.errors import InvalidRequestError
from app.db.types import utc_now
from app.models.enums import AnswerMethod, MemoryState, SelectionMode, SessionIntent
from app.models.learning import LearningItem, ReviewState
from app.models.review import Answer, ReviewSession
from app.models.user import User
from app.schemas.review import OfflineAnswer, OfflineCard, OfflinePack, OfflineSyncResult
from app.services.courses.service import get_owned_course
from app.services.review import service as review
from app.services.review.pool import eligible_items
from app.services.rewards import service as rewards
from app.services.scheduling.policy import SchedulingError
from app.services.scheduling.store import policy_for, snapshot_of, store

PACK_DAYS = 7
PACK_MAX = 500
SYNC_MAX = 500
# An answer can't claim to be from the future, nor older than a pack can be.
MAX_AGE = timedelta(days=30)
OFFLINE_NOTE = "offline"


def _aware(value: datetime) -> datetime:
    return value if value.tzinfo else value.replace(tzinfo=UTC)


def pack(
    db: Session, user_id: uuid.UUID, course_id: uuid.UUID, days: int = PACK_DAYS
) -> OfflinePack:
    course = get_owned_course(db, user_id, course_id)
    now = utc_now()
    until = now + timedelta(days=days)
    items = db.scalars(
        eligible_items(course.id).where(
            ReviewState.state != MemoryState.NEW,
            ReviewState.paused_at.is_(None),
            ReviewState.due_at.is_not(None),
            ReviewState.due_at <= until,
        )
    ).all()
    cards = []
    for item in items[:PACK_MAX]:
        question = review._pick_question(item)
        cards.append(
            OfflineCard(
                learning_item_id=item.id,
                question_formulation_id=question.id,
                question=question.text,
                expected_knowledge=item.expected_knowledge,
                essential_points=list(item.essential_points),
                due_at=item.review_state.due_at or now,
                drawing=item.answer_format == "DRAWING",
            )
        )
    cards.sort(key=lambda card: card.due_at)
    return OfflinePack(
        course_id=course.id, title=course.title, created_at=now, until=until, cards=cards
    )


def sync(
    db: Session, user: User, course_id: uuid.UUID, answers: list[OfflineAnswer]
) -> OfflineSyncResult:
    course = get_owned_course(db, user.id, course_id)
    if len(answers) > SYNC_MAX:
        raise InvalidRequestError(f"At most {SYNC_MAX} answers at a time.")
    now = utc_now()
    seen = set(
        db.scalars(
            select(Answer.override_note).where(
                Answer.user_id == user.id,
                Answer.override_note.in_([f"{OFFLINE_NOTE}:{a.client_id}" for a in answers]),
            )
        )
    )
    session = ReviewSession(
        id=uuid.uuid4(),
        user_id=user.id,
        course_id=course.id,
        intent=SessionIntent.SCHEDULED_REVIEW,
        selection_mode=SelectionMode.SELECTED,
        affects_schedule=True,
        item_ids=[],
        position=0,
        started_at=min((_aware(a.answered_at) for a in answers), default=now),
        ended_at=now,
    )
    db.add(session)
    db.flush()
    applied, skipped = 0, 0
    for entry in sorted(answers, key=lambda a: _aware(a.answered_at)):
        note = f"{OFFLINE_NOTE}:{entry.client_id}"
        at = _aware(entry.answered_at)
        item = db.get(LearningItem, entry.learning_item_id)
        question = next(
            (q for q in (item.questions if item else []) if q.id == entry.question_formulation_id),
            None,
        )
        state = item.review_state if item else None
        if (
            note in seen
            or item is None
            or item.course_id != course.id
            or question is None
            or state is None
            or state.state is MemoryState.NEW
            or state.paused_at is not None
            or at > now + timedelta(minutes=5)
            or at < now - MAX_AGE
            # Reviewed since, on another device: that review stands.
            or (state.last_reviewed_at is not None and _aware(state.last_reviewed_at) >= at)
        ):
            skipped += 1
            continue
        at = min(at, now)
        session.item_ids = [*session.item_ids, str(item.id)]
        answer = Answer(
            id=uuid.uuid4(),
            user_id=user.id,
            course_id=course.id,
            session_id=session.id,
            learning_item_id=item.id,
            question_formulation_id=question.id,
            intent=SessionIntent.SCHEDULED_REVIEW,
            method=AnswerMethod.TEXT,
            text=entry.text,
            created_at=at,
            override_outcome=entry.outcome,
            override_note=note,
            overridden_at=at,
            final_outcome=entry.outcome,
            finalized_at=at,
        )
        db.add(answer)
        db.flush()
        state_before, due_before, level_before = state.state, state.due_at, state.level
        policy = policy_for(state)
        before = snapshot_of(state)
        try:
            transition = policy.process_review(before, entry.outcome, at)
        except SchedulingError:
            transition = None
        if transition is not None:
            store(state, transition.after)
            review._history(
                db,
                item,
                answer,
                SessionIntent.SCHEDULED_REVIEW,
                transition,
                policy.name,
                policy.version,
                None,
            )
        occasion = rewards.occasion_for(
            db, session, item, state_before=state_before, due_before=due_before, at=at
        )
        rewards.record_attempt(
            db,
            user,
            session,
            item,
            answer,
            occasion=occasion if transition is not None else None,
            classification=None,
            at=at,
            level=level_before,
            self_grade=entry.outcome,
        )
        seen.add(note)
        applied += 1
    session.position = len(session.item_ids)
    if applied == 0:
        db.rollback()
    else:
        db.commit()
    return OfflineSyncResult(applied=applied, skipped=skipped)
