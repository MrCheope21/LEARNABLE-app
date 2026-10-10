"""The study dashboard in one read (docs/XP_AND_ACTIVITY.md §6-7).

A fixed number of queries whatever the number of Courses (no per-Course round trips), all
scoped to the signed-in user, all computed against one `as_of` timestamp so the planner, due
counts and the next step agree. Due counts use the same eligibility as a SCHEDULED_REVIEW
session (app/services/review/pool.py), so "12 due" is 12 items a review would ask.
"""

import uuid
from collections import defaultdict
from collections.abc import Sequence
from dataclasses import dataclass
from datetime import UTC, date, datetime, timedelta

from sqlalchemy import case, func, select
from sqlalchemy.orm import Session

from app.db.types import utc_now
from app.models.course import Chapter, Concept, Course, Topic
from app.models.enums import EvaluationStatus, MemoryState, SessionIntent, StudyState
from app.models.learning import LearningItem, ReviewState
from app.models.marketplace import MarketplaceListing
from app.models.review import Answer, Evaluation, ReviewSession
from app.models.rewards import DailyActivity
from app.models.user import User
from app.schemas.dashboard import (
    Activity,
    ActivityDay,
    CourseCard,
    DailyGoal,
    Dashboard,
    LearnAction,
    NextConcept,
    NextStep,
    Planner,
    PlannerHorizon,
    Streak,
    StreakDay,
    WeakConcept,
    WeakMisconception,
    WeakSpots,
    XpSummary,
)
from app.services.courses.service import get_owned_course
from app.services.review.pool import eligible_items_for_user
from app.services.rewards.service import local_day, zone

DEFAULT_ACTIVITY_WEEKS = 12
MAX_ACTIVITY_WEEKS = 53
# A streak longer than this is reported as this; bounds the scan.
MAX_STREAK_DAYS = 400
PLANNER_HORIZONS: tuple[tuple[str, timedelta], ...] = (
    ("now", timedelta(0)),
    ("1h", timedelta(hours=1)),
    ("4h", timedelta(hours=4)),
    # Rolling windows from now, not calendar days: "in 1 day" = the next 24 hours.
    ("1d", timedelta(days=1)),
    ("3d", timedelta(days=3)),
    ("7d", timedelta(days=7)),
)


def dashboard(db: Session, user: User, weeks: int = DEFAULT_ACTIVITY_WEEKS) -> Dashboard:
    as_of = utc_now()
    today = local_day(user.timezone, as_of)
    cards = _course_cards(db, user, as_of, course_id=None)
    unfinished = _unfinished_consolidations(db, user.id)
    reviewable = _reviewable_due_dates(db, user.id)
    xp_total = int(
        db.scalar(
            select(func.coalesce(func.sum(DailyActivity.xp), 0)).where(
                DailyActivity.user_id == user.id
            )
        )
        or 0
    )
    today_row = db.scalar(
        select(DailyActivity).where(DailyActivity.user_id == user.id, DailyActivity.day == today)
    )
    return Dashboard(
        as_of=as_of,
        timezone=zone(user.timezone).key,
        today=today,
        next_step=_next_step(cards, unfinished),
        courses=cards,
        xp=XpSummary(total=xp_total, today=today_row.xp if today_row else 0),
        streak=_streak(db, user.id, today),
        goal=DailyGoal(target=user.daily_goal, done=today_row.attempts if today_row else 0),
        planner=_planner(reviewable, as_of),
        activity=activity(db, user, weeks, today=today),
    )


def course_card(db: Session, user: User, course_id: uuid.UUID) -> CourseCard:
    get_owned_course(db, user.id, course_id)
    [card] = _course_cards(db, user, utc_now(), course_id=course_id)
    return card


WEAK_SPOT_LOOKBACK = timedelta(days=90)
WEAK_SPOT_EVALUATIONS_PER_ITEM = 3
WEAK_SPOT_CONCEPTS = 20
WEAK_SPOT_MISCONCEPTIONS = 5


@dataclass
class _Seen:
    text: str
    last_seen: datetime
    count: int = 0


def weak_spots(db: Session, user: User, course_id: uuid.UUID) -> WeakSpots:
    get_owned_course(db, user.id, course_id)
    # The latest few evaluations of each item, newest first (the cap is applied in SQL).
    recent = (
        select(
            Answer.learning_item_id.label("item_id"),
            Evaluation.misconceptions.label("misconceptions"),
            Evaluation.created_at.label("created_at"),
            func.row_number()
            .over(partition_by=Answer.learning_item_id, order_by=Evaluation.created_at.desc())
            .label("rank"),
        )
        .join(Answer, Answer.id == Evaluation.answer_id)
        .where(
            Evaluation.course_id == course_id,
            Evaluation.status == EvaluationStatus.COMPLETED,
            Evaluation.user_argument.is_(None),
            Evaluation.created_at >= utc_now() - WEAK_SPOT_LOOKBACK,
        )
        .subquery()
    )
    rows = db.execute(
        select(
            Concept.id,
            Concept.title,
            Topic.title,
            Chapter.title,
            recent.c.misconceptions,
            recent.c.created_at,
        )
        .join(LearningItem, LearningItem.id == recent.c.item_id)
        .join(Concept, Concept.id == LearningItem.concept_id)
        .join(Topic, Topic.id == Concept.topic_id)
        .join(Chapter, Chapter.id == Concept.chapter_id)
        .where(recent.c.rank <= WEAK_SPOT_EVALUATIONS_PER_ITEM)
        .order_by(recent.c.created_at.desc())
    ).all()

    titles: dict[uuid.UUID, tuple[str, str, str]] = {}
    found: dict[uuid.UUID, dict[str, _Seen]] = defaultdict(dict)
    for concept_id, concept, topic, chapter, misconceptions, created_at in rows:
        for text in misconceptions:
            titles[concept_id] = (concept, topic, chapter)
            # Rows come newest first, so the first sighting is the latest.
            seen = found[concept_id].setdefault(
                " ".join(text.casefold().split()), _Seen(text, created_at)
            )
            seen.count += 1

    concepts = []
    for concept_id, entries in found.items():
        top = sorted(entries.values(), key=lambda e: (-e.count, -e.last_seen.timestamp()))
        concept, topic, chapter = titles[concept_id]
        concepts.append(
            WeakConcept(
                concept_id=concept_id,
                concept_title=concept,
                topic_title=topic,
                chapter_title=chapter,
                total=sum(e.count for e in entries.values()),
                misconceptions=[
                    WeakMisconception(text=e.text, count=e.count, last_seen=e.last_seen)
                    for e in top[:WEAK_SPOT_MISCONCEPTIONS]
                ],
            )
        )
    concepts.sort(key=lambda c: (-c.total, c.concept_title))
    return WeakSpots(concepts=concepts[:WEAK_SPOT_CONCEPTS])


def activity(
    db: Session, user: User, weeks: int = DEFAULT_ACTIVITY_WEEKS, *, today: date | None = None
) -> Activity:
    weeks = max(1, min(weeks, MAX_ACTIVITY_WEEKS))
    today = today or local_day(user.timezone, utc_now())
    end = today + timedelta(days=6 - today.weekday())  # Sunday of this week
    start = end - timedelta(days=7 * weeks - 1)  # a Monday
    rows = db.scalars(
        select(DailyActivity)
        .where(
            DailyActivity.user_id == user.id,
            DailyActivity.day >= start,
            DailyActivity.day <= end,
        )
        .order_by(DailyActivity.day)
    ).all()
    return Activity(
        start=start,
        end=end,
        today=today,
        days=[ActivityDay(date=r.day, attempts=r.attempts, xp=r.xp) for r in rows],
    )


# --- Courses ---


@dataclass
class _ConceptRow:
    id: uuid.UUID
    course_id: uuid.UUID
    title: str
    state: StudyState


def _course_cards(
    db: Session, user: User, as_of: datetime, course_id: uuid.UUID | None
) -> list[CourseCard]:
    course_filter = [Course.user_id == user.id]
    if course_id is not None:
        course_filter.append(Course.id == course_id)
    courses = db.scalars(select(Course).where(*course_filter).order_by(Course.created_at)).all()
    if not courses:
        return []
    ids = [c.id for c in courses]

    # Concepts in course order (Chapter → Topic → Concept), one query.
    concepts = [
        _ConceptRow(cid, course, title, state)
        for cid, course, title, state in db.execute(
            select(Concept.id, Concept.course_id, Concept.title, Concept.study_state)
            .join(Topic, Topic.id == Concept.topic_id)
            .join(Chapter, Chapter.id == Concept.chapter_id)
            .where(Concept.course_id.in_(ids))
            .order_by(
                Chapter.order,
                Chapter.created_at,
                Topic.order,
                Topic.created_at,
                Concept.order,
                Concept.created_at,
            )
        ).tuples()
    ]

    # Trained items per Concept: how many, and how many still NEW (any eligibility).
    trained: dict[uuid.UUID, tuple[int, int]] = {}
    for concept_id, total, new in db.execute(
        select(
            LearningItem.concept_id,
            func.count(),
            func.sum(case((ReviewState.state == MemoryState.NEW, 1), else_=0)),
        )
        .join(ReviewState, ReviewState.learning_item_id == LearningItem.id)
        .where(LearningItem.course_id.in_(ids), LearningItem.in_training.is_(True))
        .group_by(LearningItem.concept_id)
    ).tuples():
        trained[concept_id] = (int(total), int(new or 0))

    # Reviewable items (session eligibility): due now, and NEW ones ready per Concept.
    due_now: dict[uuid.UUID, int] = defaultdict(int)
    new_ready: dict[uuid.UUID, int] = defaultdict(int)
    new_ready_concept: dict[uuid.UUID, int] = defaultdict(int)
    rows = db.execute(
        eligible_items_for_user(user.id)
        .where(LearningItem.course_id.in_(ids))
        .order_by(None)
        .with_only_columns(
            LearningItem.course_id,
            LearningItem.concept_id,
            ReviewState.state,
            ReviewState.due_at,
            ReviewState.paused_at,
        )
    ).tuples()
    for item_course, concept_id, state, due_at, paused_at in rows:
        if state is MemoryState.NEW:
            new_ready[item_course] += 1
            new_ready_concept[concept_id] += 1
        elif due_at is not None and paused_at is None and _aware(due_at) <= as_of:
            due_now[item_course] += 1

    last_studied = dict(
        db.execute(
            select(Answer.course_id, func.max(Answer.finalized_at))
            .where(Answer.user_id == user.id, Answer.course_id.in_(ids))
            .group_by(Answer.course_id)
        )
        .tuples()
        .all()
    )
    unfinished = {s.course_id: s for s in _unfinished_consolidations(db, user.id)}

    authors = _marketplace_authors(db, courses)

    by_course: dict[uuid.UUID, list[_ConceptRow]] = defaultdict(list)
    for concept in concepts:
        by_course[concept.course_id].append(concept)

    cards = []
    for course in courses:
        course_concepts = by_course[course.id]
        studied = sum(
            1
            for c in course_concepts
            if c.id in trained and trained[c.id][0] > 0 and trained[c.id][1] == 0
        )
        items_total = sum(trained[c.id][0] for c in course_concepts if c.id in trained)
        items_new = sum(trained[c.id][1] for c in course_concepts if c.id in trained)
        cards.append(
            CourseCard(
                id=course.id,
                title=course.title,
                description=course.description,
                language=course.language,
                paused=course.paused,
                marketplace_author=authors.get(course.id),
                archived_at=course.archived_at,
                created_at=course.created_at,
                last_studied_at=last_studied.get(course.id),
                concepts_total=len(course_concepts),
                concepts_studied=studied,
                items_trained=items_total,
                items_introduced=items_total - items_new,
                due_now=due_now[course.id],
                new_ready=new_ready[course.id],
                learn=_learn_action(course_concepts, new_ready_concept, unfinished.get(course.id)),
            )
        )
    return cards


def _marketplace_authors(db: Session, courses: Sequence[Course]) -> dict[uuid.UUID, str]:
    """Courses from the marketplace → their author's display name."""
    listing_ids = {c.marketplace_listing_id for c in courses if c.marketplace_listing_id}
    if not listing_ids:
        return {}
    names = dict(
        db.execute(
            select(MarketplaceListing.id, User.display_name)
            .join(User, User.id == MarketplaceListing.author_id)
            .where(MarketplaceListing.id.in_(listing_ids))
        )
        .tuples()
        .all()
    )
    return {
        c.id: names.get(c.marketplace_listing_id) or "A LEARNABLE user"
        for c in courses
        if c.marketplace_listing_id
    }


def _learn_action(
    concepts: list[_ConceptRow],
    new_ready: dict[uuid.UUID, int],
    unfinished: ReviewSession | None,
) -> LearnAction:
    """Resume first (an unfinished batch holds rewarded rounds); then the first concept, in
    course order, with material ready; then the first concept still to activate. A course
    without concepts needs setting up; "none" means everything there has been learned."""
    if unfinished is not None:
        concept_id = uuid.UUID(unfinished.concept_ids[0]) if unfinished.concept_ids else None
        concept = next((c for c in concepts if c.id == concept_id), None)
        return LearnAction(kind="resume", concept=_next_concept(concept), session_id=unfinished.id)
    ready = next((c for c in concepts if new_ready.get(c.id, 0) > 0), None)
    if ready is not None:
        return LearnAction(kind="study", concept=_next_concept(ready), session_id=None)
    to_activate = next(
        (c for c in concepts if c.state in (StudyState.NOT_STUDIED, StudyState.STUDIED)), None
    )
    if to_activate is not None:
        return LearnAction(kind="activate", concept=_next_concept(to_activate), session_id=None)
    if not concepts:
        return LearnAction(kind="setup", concept=None, session_id=None)
    return LearnAction(kind="none", concept=None, session_id=None)


def _next_concept(concept: _ConceptRow | None) -> NextConcept | None:
    if concept is None:
        return None
    return NextConcept(id=concept.id, title=concept.title, study_state=concept.state)


def _unfinished_consolidations(db: Session, user_id: uuid.UUID) -> list[ReviewSession]:
    """Open consolidation batches with slots left, most recent first. Read-only: a batch whose
    remaining items were deleted meanwhile is closed when it's next opened."""
    sessions = db.scalars(
        select(ReviewSession)
        .where(
            ReviewSession.user_id == user_id,
            ReviewSession.intent == SessionIntent.CONSOLIDATION,
            ReviewSession.ended_at.is_(None),
        )
        .order_by(ReviewSession.started_at.desc())
    ).all()
    return [s for s in sessions if s.position < len(s.item_ids)]


# --- Next step ---


def _next_step(cards: list[CourseCard], unfinished: list[ReviewSession]) -> NextStep:
    """One recommendation, by a fixed priority (docs/XP_AND_ACTIVITY.md §6):
    1. resume an unfinished consolidation batch (its rounds are immediate: waiting loses them);
    2. review due items (the course with most due);
    3. continue new learning (the most recently studied course with something to learn);
    4. a course with no material yet: set it up (the most recently created);
    5. no course yet: create one; otherwise all caught up."""
    # Courses put away are out of the recommendation (an archived course is also paused, so it
    # has nothing due either).
    cards = [c for c in cards if c.archived_at is None]
    titles = {c.id: c.title for c in cards}
    unfinished = [s for s in unfinished if s.course_id in titles]
    if unfinished:
        session = unfinished[0]
        key = session.item_ids[session.position]
        card = next((c for c in cards if c.id == session.course_id), None)
        concept = card.learn.concept if card and card.learn.session_id == session.id else None
        return NextStep(
            kind="resume_consolidation",
            course_id=session.course_id,
            course_title=titles.get(session.course_id),
            concept_id=concept.id if concept else None,
            concept_title=concept.title if concept else None,
            session_id=session.id,
            count=len(session.item_ids) - session.position,
            round=session.item_ids[: session.position + 1].count(key),
            rounds_total=session.item_ids.count(key),
        )
    due = max(cards, key=lambda c: c.due_now, default=None)
    if due is not None and due.due_now > 0:
        return NextStep(kind="review", course_id=due.id, course_title=due.title, count=due.due_now)
    learnable = [c for c in cards if c.learn.kind in ("study", "activate")]
    if learnable:
        oldest = datetime.min.replace(tzinfo=UTC)
        card = max(
            learnable,
            key=lambda c: (c.learn.kind == "study", _aware(c.last_studied_at or oldest)),
        )
        concept = card.learn.concept
        return NextStep(
            kind="learn" if card.learn.kind == "study" else "activate",
            course_id=card.id,
            course_title=card.title,
            concept_id=concept.id if concept else None,
            concept_title=concept.title if concept else None,
        )
    empty = [c for c in cards if c.learn.kind == "setup"]
    if empty:
        newest = max(empty, key=lambda c: _aware(c.created_at))
        return NextStep(kind="setup_course", course_id=newest.id, course_title=newest.title)
    if not cards:
        return NextStep(kind="create_course")
    return NextStep(kind="all_caught_up")


# --- Streak, planner ---


def current_streak(db: Session, user_id: uuid.UUID, today: date) -> int:
    """Consecutive days with a completed answer (see `Streak.current`)."""
    return _streak(db, user_id, today).current


def _streak(db: Session, user_id: uuid.UUID, today: date) -> Streak:
    days = set(
        db.scalars(
            select(DailyActivity.day)
            .where(
                DailyActivity.user_id == user_id,
                DailyActivity.attempts > 0,
                DailyActivity.day <= today,
                DailyActivity.day > today - timedelta(days=MAX_STREAK_DAYS),
            )
            .order_by(DailyActivity.day.desc())
        )
    )
    today_complete = today in days
    # Yesterday's streak is still alive before today's first answer.
    cursor = today if today_complete else today - timedelta(days=1)
    current = 0
    while cursor in days:
        current += 1
        cursor -= timedelta(days=1)
    week = [today - timedelta(days=offset) for offset in range(6, -1, -1)]
    return Streak(
        current=current,
        today_complete=today_complete,
        last_7_days=[StreakDay(date=d, active=d in days) for d in week],
    )


def _reviewable_due_dates(db: Session, user_id: uuid.UUID) -> list[datetime]:
    """Due dates of every encoded, reviewable, unpaused item: what reviews will ask."""
    rows = db.execute(
        eligible_items_for_user(user_id)
        .order_by(None)
        .where(
            ReviewState.state != MemoryState.NEW,
            ReviewState.due_at.is_not(None),
            ReviewState.paused_at.is_(None),
        )
        .with_only_columns(ReviewState.due_at)
    ).scalars()
    return [_aware(due) for due in rows if due is not None]


def _planner(due_dates: list[datetime], as_of: datetime) -> Planner:
    horizons = []
    for key, delta in PLANNER_HORIZONS:
        due_by = as_of + delta
        horizons.append(
            PlannerHorizon(
                key=key,  # type: ignore[arg-type]
                due_by=due_by,
                items=sum(1 for due in due_dates if due <= due_by),
            )
        )
    return Planner(as_of=as_of, horizons=horizons)


def _aware(value: datetime) -> datetime:
    return value if value.tzinfo else value.replace(tzinfo=UTC)
