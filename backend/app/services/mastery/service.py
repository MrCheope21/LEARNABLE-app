"""Progress, mastery estimates and review load (docs/PROJECT_SPEC.md §52-54, §68).

Curriculum progress (study states) and memory progress (Learning Item memory states) are kept
separate at every level, never merged into one score (spec §54). Mastery is an explicit
estimate from memory state; it is not a measurement of memory.

Everything is computed on read from the items' ReviewStates, so it can't drift from the
schedule. A Course has at most a few thousand items: a handful of queries, aggregated here.
"""

import uuid
from collections import defaultdict
from collections.abc import Iterable
from datetime import UTC, datetime, timedelta, timezone

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.db.types import utc_now
from app.models.course import Chapter, Concept, Course, Topic
from app.models.enums import MemoryState, StudyState
from app.models.learning import LearningItem, ReviewState
from app.models.review import Answer, Evaluation
from app.schemas.progress import (
    ChapterProgress,
    ConceptProgress,
    CourseProgress,
    CourseSummary,
    CurriculumProgress,
    HomeSummary,
    MemoryProgress,
    ReviewLoad,
    TopicProgress,
    WeakConcept,
)
from app.services.courses.service import get_owned_course
from app.services.review.pool import eligible_items
from app.services.scheduling.store import policy_for, snapshot_of

MISCONCEPTIONS_PER_CONCEPT = 5


def course_progress(
    db: Session, user_id: uuid.UUID, course_id: uuid.UUID, utc_offset_minutes: int = 0
) -> CourseProgress:
    get_owned_course(db, user_id, course_id)
    chapters = db.scalars(
        select(Chapter)
        .where(Chapter.course_id == course_id)
        .order_by(Chapter.order, Chapter.created_at)
    ).all()
    topics = db.scalars(
        select(Topic).where(Topic.course_id == course_id).order_by(Topic.order, Topic.created_at)
    ).all()
    concepts = db.scalars(
        select(Concept)
        .where(Concept.course_id == course_id)
        .order_by(Concept.order, Concept.created_at)
    ).all()
    trained = (
        db.execute(
            select(LearningItem, ReviewState)
            .join(ReviewState, ReviewState.learning_item_id == LearningItem.id)
            .where(LearningItem.course_id == course_id, LearningItem.in_training.is_(True))
        )
        .tuples()
        .all()
    )

    items_by_concept: dict[uuid.UUID, list[ReviewState]] = defaultdict(list)
    for item, state in trained:
        items_by_concept[item.concept_id].append(state)
    misconceptions = _misconceptions(db, course_id)

    concepts_by_topic: dict[uuid.UUID, list[Concept]] = defaultdict(list)
    for concept in concepts:
        concepts_by_topic[concept.topic_id].append(concept)
    topics_by_chapter: dict[uuid.UUID, list[Topic]] = defaultdict(list)
    for topic in topics:
        topics_by_chapter[topic.chapter_id].append(topic)

    def states_of(concept_list: Iterable[Concept]) -> list[ReviewState]:
        return [s for c in concept_list for s in items_by_concept[c.id]]

    chapter_nodes = []
    for chapter in chapters:
        topic_nodes = []
        chapter_concepts: list[Concept] = []
        for topic in topics_by_chapter[chapter.id]:
            topic_concepts = concepts_by_topic[topic.id]
            chapter_concepts.extend(topic_concepts)
            topic_nodes.append(
                TopicProgress(
                    id=topic.id,
                    title=topic.title,
                    curriculum=_curriculum(topic_concepts),
                    memory=_memory(states_of(topic_concepts)),
                    concepts=[
                        ConceptProgress(
                            id=c.id,
                            title=c.title,
                            study_state=c.study_state,
                            memory=_memory(items_by_concept[c.id]),
                            misconceptions=misconceptions.get(c.id, []),
                        )
                        for c in topic_concepts
                    ],
                )
            )
        chapter_nodes.append(
            ChapterProgress(
                id=chapter.id,
                title=chapter.title,
                curriculum=_curriculum(chapter_concepts),
                memory=_memory(states_of(chapter_concepts)),
                topics=topic_nodes,
            )
        )
    return CourseProgress(
        course_id=course_id,
        curriculum=_curriculum(concepts),
        memory=_memory([state for _, state in trained]),
        review_load=_review_load(db, course_id, utc_offset_minutes),
        chapters=chapter_nodes,
    )


def review_load(
    db: Session, user_id: uuid.UUID, course_id: uuid.UUID, utc_offset_minutes: int = 0
) -> ReviewLoad:
    get_owned_course(db, user_id, course_id)
    return _review_load(db, course_id, utc_offset_minutes)


WEAK_CONCEPTS_SHOWN = 3


def home_summary(db: Session, user_id: uuid.UUID, utc_offset_minutes: int = 0) -> HomeSummary:
    courses = db.scalars(
        select(Course).where(Course.user_id == user_id).order_by(Course.created_at)
    ).all()
    summaries = [_course_summary(db, course, utc_offset_minutes) for course in courses]
    fields = list(ReviewLoad.model_fields)
    totals = ReviewLoad(**{f: sum(getattr(s.review_load, f) for s in summaries) for f in fields})
    return HomeSummary(totals=totals, courses=summaries)


def _course_summary(db: Session, course: Course, utc_offset_minutes: int) -> CourseSummary:
    active = db.scalars(
        select(Concept).where(
            Concept.course_id == course.id, Concept.study_state == StudyState.ACTIVE
        )
    ).all()
    rows = (
        db.execute(
            select(LearningItem.concept_id, ReviewState)
            .join(ReviewState, ReviewState.learning_item_id == LearningItem.id)
            .where(LearningItem.course_id == course.id, LearningItem.in_training.is_(True))
        )
        .tuples()
        .all()
    )
    titles = {
        c.id: c.title for c in db.scalars(select(Concept).where(Concept.course_id == course.id))
    }
    weakness: dict[uuid.UUID, tuple[int, int]] = {}
    for concept_id, state in rows:
        lapses, hard = weakness.get(concept_id, (0, 0))
        weakness[concept_id] = (lapses + state.lapse_count, hard + (1 if state.marked_hard else 0))
    weak = sorted(
        ((cid, lapses, hard) for cid, (lapses, hard) in weakness.items() if lapses or hard),
        key=lambda w: (-(w[1] + w[2]), titles.get(w[0], "")),
    )[:WEAK_CONCEPTS_SHOWN]
    return CourseSummary(
        course_id=course.id,
        title=course.title,
        review_load=_review_load(db, course.id, utc_offset_minutes),
        active_concepts=len(active),
        mastery=_memory([state for _, state in rows]).mastery,
        weak_concepts=[
            WeakConcept(id=cid, title=titles.get(cid, ""), lapses=lapses, marked_hard=hard)
            for cid, lapses, hard in weak
        ],
    )


def _curriculum(concepts: Iterable[Concept]) -> CurriculumProgress:
    counts = dict.fromkeys(StudyState, 0)
    total = 0
    for concept in concepts:
        counts[concept.study_state] += 1
        total += 1
    return CurriculumProgress(
        concepts=total,
        not_studied=counts[StudyState.NOT_STUDIED],
        studied=counts[StudyState.STUDIED],
        active=counts[StudyState.ACTIVE],
        paused=counts[StudyState.PAUSED],
        completed=counts[StudyState.COMPLETED],
    )


def item_mastery(state: ReviewState) -> float:
    """The item's own policy interprets its own state (a level ladder here, stability in FSRS)."""
    return policy_for(state).mastery_estimate(snapshot_of(state))


def _memory(states: list[ReviewState]) -> MemoryProgress:
    counts = dict.fromkeys(MemoryState, 0)
    for state in states:
        counts[state.state] += 1
    return MemoryProgress(
        items_trained=len(states),
        new=counts[MemoryState.NEW],
        learning=counts[MemoryState.LEARNING],
        review=counts[MemoryState.REVIEW],
        relearning=counts[MemoryState.RELEARNING],
        mastered=counts[MemoryState.MASTERED],
        marked_hard=sum(1 for s in states if s.marked_hard),
        mastery=round(sum(item_mastery(s) for s in states) / len(states), 3) if states else None,
    )


def _review_load(db: Session, course_id: uuid.UUID, utc_offset_minutes: int) -> ReviewLoad:
    rows = db.execute(
        eligible_items(course_id)
        .order_by(None)
        .with_only_columns(ReviewState.state, ReviewState.due_at, ReviewState.paused_at)
    ).all()
    now = utc_now()
    local = timezone(timedelta(minutes=utc_offset_minutes))
    start_of_today = now.astimezone(local).replace(hour=0, minute=0, second=0, microsecond=0)
    end_today = start_of_today + timedelta(days=1)
    end_tomorrow = end_today + timedelta(days=1)
    end_week = end_today + timedelta(days=7)
    load = {
        "due_now": 0,
        "overdue": 0,
        "later_today": 0,
        "tomorrow": 0,
        "next_7_days": 0,
        "later": 0,
    }
    new = 0
    for state, due_at, paused_at in rows:
        if state is MemoryState.NEW:
            new += 1
            continue
        if due_at is None or paused_at is not None:
            continue
        due = _aware(due_at)
        if due <= now:
            load["due_now"] += 1
            if due < start_of_today:
                load["overdue"] += 1
        elif due < end_today:
            load["later_today"] += 1
        elif due < end_tomorrow:
            load["tomorrow"] += 1
        elif due < end_week:
            load["next_7_days"] += 1
        else:
            load["later"] += 1
    return ReviewLoad(**load, new_to_learn=new)


def _aware(value: datetime) -> datetime:
    return value if value.tzinfo else value.replace(tzinfo=UTC)


def _misconceptions(db: Session, course_id: uuid.UUID) -> dict[uuid.UUID, list[str]]:
    rows = db.execute(
        select(LearningItem.concept_id, Evaluation.misconceptions)
        .join(Answer, Answer.id == Evaluation.answer_id)
        .join(LearningItem, LearningItem.id == Answer.learning_item_id)
        .where(
            Evaluation.course_id == course_id,
            LearningItem.course_id == course_id,
            Evaluation.user_argument.is_(None),
        )
        .order_by(Evaluation.created_at.desc())
        .limit(500)
    ).tuples()
    found: dict[uuid.UUID, list[str]] = defaultdict(list)
    for concept_id, items in rows:
        for text in items or []:
            bucket = found[concept_id]
            if text not in bucket and len(bucket) < MISCONCEPTIONS_PER_CONCEPT:
                bucket.append(text)
    return dict(found)
