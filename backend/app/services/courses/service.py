"""Course hierarchy CRUD + ownership/isolation enforcement (docs/PROJECT_SPEC.md §10, §81).

Every `get_owned_*` function is the single point where a resource's Course scope is verified
against the requesting user — API handlers never touch models directly, and no query here trusts
a client-supplied id without checking it traces back to a Course the caller owns.
"""

import uuid
from collections.abc import Sequence
from typing import Protocol

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.errors import InvalidRequestError, InvalidStateTransitionError, NotFoundError
from app.models.course import Chapter, Concept, Course, CourseSettings, Topic
from app.models.document import Document
from app.models.enums import StudyState
from app.models.learning import LearningItem
from app.schemas.courses import (
    ChapterCreate,
    ChapterUpdate,
    ConceptCreate,
    ConceptUpdate,
    CourseCreate,
    CourseUpdate,
    CurriculumDelete,
    CurriculumDeleteResult,
    TopicCreate,
    TopicUpdate,
)

# --- Course ---


def create_course(db: Session, user_id: uuid.UUID, payload: CourseCreate) -> Course:
    course = Course(
        user_id=user_id,
        title=payload.title,
        description=payload.description,
        language=payload.language,
    )
    course.settings = CourseSettings()
    db.add(course)
    db.commit()
    db.refresh(course)
    return course


def list_courses(db: Session, user_id: uuid.UUID) -> list[Course]:
    stmt = select(Course).where(Course.user_id == user_id).order_by(Course.created_at)
    return list(db.scalars(stmt).all())


def get_owned_course(db: Session, user_id: uuid.UUID, course_id: uuid.UUID) -> Course:
    course = db.get(Course, course_id)
    if course is None or course.user_id != user_id:
        raise NotFoundError("Course not found")
    return course


def update_course(
    db: Session, user_id: uuid.UUID, course_id: uuid.UUID, payload: CourseUpdate
) -> Course:
    course = get_owned_course(db, user_id, course_id)
    for field, value in payload.model_dump(exclude_unset=True).items():
        setattr(course, field, value)
    db.commit()
    db.refresh(course)
    return course


def delete_course(db: Session, user_id: uuid.UUID, course_id: uuid.UUID) -> list[str]:
    """Deletes the Course and everything under it; returns the storage keys of its
    documents, whose files the caller must remove (rows cascade, files don't)."""
    course = get_owned_course(db, user_id, course_id)
    keys = list(
        db.scalars(select(Document.storage_key).where(Document.course_id == course_id)).all()
    )
    db.delete(course)
    db.commit()
    return keys


# --- Chapter ---


def create_chapter(
    db: Session, user_id: uuid.UUID, course_id: uuid.UUID, payload: ChapterCreate
) -> Chapter:
    get_owned_course(db, user_id, course_id)
    chapter = Chapter(
        course_id=course_id,
        title=payload.title,
        description=payload.description,
        order=payload.order,
    )
    db.add(chapter)
    db.commit()
    db.refresh(chapter)
    return chapter


def get_owned_chapter(db: Session, user_id: uuid.UUID, chapter_id: uuid.UUID) -> Chapter:
    chapter = db.get(Chapter, chapter_id)
    if chapter is None:
        raise NotFoundError("Chapter not found")
    get_owned_course(db, user_id, chapter.course_id)
    return chapter


def update_chapter(
    db: Session, user_id: uuid.UUID, chapter_id: uuid.UUID, payload: ChapterUpdate
) -> Chapter:
    chapter = get_owned_chapter(db, user_id, chapter_id)
    for field, value in payload.model_dump(exclude_unset=True).items():
        setattr(chapter, field, value)
    db.commit()
    db.refresh(chapter)
    return chapter


def delete_chapter(db: Session, user_id: uuid.UUID, chapter_id: uuid.UUID) -> None:
    """Deletes the Chapter and its Topics/Concepts. Its documents stay in the Course, unassigned
    and marked not analyzed, since what was built from them is gone."""
    chapter = get_owned_chapter(db, user_id, chapter_id)
    for document in db.scalars(select(Document).where(Document.chapter_id == chapter.id)):
        document.chapter_id = None
        document.analyzed_at = None
    db.delete(chapter)
    db.commit()


def delete_curriculum(
    db: Session, user_id: uuid.UUID, course_id: uuid.UUID, payload: CurriculumDelete
) -> CurriculumDeleteResult:
    """Deletes chapters, topics, concepts and questions in one transaction. Every id must belong
    to this Course (404 otherwise, as for a missing id) or nothing changes. What sits inside a
    selected group is deleted with it. Documents of a deleted chapter stay, unassigned and marked
    not analyzed, as with a single chapter delete."""
    get_owned_course(db, user_id, course_id)

    def fetch[T: Chapter | Topic | Concept | LearningItem](
        model: type[T], ids: list[uuid.UUID]
    ) -> dict[uuid.UUID, T]:
        wanted = set(ids)
        rows = {
            row.id: row
            for row in db.scalars(
                select(model).where(model.course_id == course_id, model.id.in_(wanted))
            )
        }
        if len(rows) != len(wanted):
            raise NotFoundError(f"{model.__name__} not found")
        return rows

    chapters = fetch(Chapter, payload.chapter_ids)
    topics = fetch(Topic, payload.topic_ids)
    concepts = fetch(Concept, payload.concept_ids)
    items = fetch(LearningItem, payload.item_ids)

    # Only the outermost selections are deleted; the database removes what is inside them.
    topics_left = {t.id: t for t in topics.values() if t.chapter_id not in chapters}
    concepts_left = {
        c.id: c
        for c in concepts.values()
        if c.chapter_id not in chapters and c.topic_id not in topics
    }
    homes = {
        c.id: c
        for c in db.scalars(
            select(Concept).where(Concept.id.in_({i.concept_id for i in items.values()}))
        )
    }
    items_left = [
        i
        for i in items.values()
        if i.concept_id not in concepts
        and homes[i.concept_id].topic_id not in topics
        and homes[i.concept_id].chapter_id not in chapters
    ]
    for chapter in chapters.values():
        for document in db.scalars(select(Document).where(Document.chapter_id == chapter.id)):
            document.chapter_id = None
            document.analyzed_at = None
    for row in [*items_left, *concepts_left.values(), *topics_left.values(), *chapters.values()]:
        db.delete(row)
    db.commit()
    return CurriculumDeleteResult(
        chapters=len(chapters), topics=len(topics), concepts=len(concepts), items=len(items)
    )


# --- Topic ---


def create_topic(
    db: Session, user_id: uuid.UUID, chapter_id: uuid.UUID, payload: TopicCreate
) -> Topic:
    chapter = get_owned_chapter(db, user_id, chapter_id)
    topic = Topic(
        chapter_id=chapter.id,
        course_id=chapter.course_id,
        title=payload.title,
        description=payload.description,
        order=payload.order,
    )
    db.add(topic)
    db.commit()
    db.refresh(topic)
    return topic


def get_owned_topic(db: Session, user_id: uuid.UUID, topic_id: uuid.UUID) -> Topic:
    topic = db.get(Topic, topic_id)
    if topic is None:
        raise NotFoundError("Topic not found")
    get_owned_course(db, user_id, topic.course_id)
    return topic


def update_topic(
    db: Session, user_id: uuid.UUID, topic_id: uuid.UUID, payload: TopicUpdate
) -> Topic:
    topic = get_owned_topic(db, user_id, topic_id)
    for field, value in payload.model_dump(exclude_unset=True).items():
        setattr(topic, field, value)
    db.commit()
    db.refresh(topic)
    return topic


def delete_topic(db: Session, user_id: uuid.UUID, topic_id: uuid.UUID) -> None:
    topic = get_owned_topic(db, user_id, topic_id)
    db.delete(topic)
    db.commit()


# --- Concept ---


def create_concept(
    db: Session, user_id: uuid.UUID, topic_id: uuid.UUID, payload: ConceptCreate
) -> Concept:
    topic = get_owned_topic(db, user_id, topic_id)
    concept = Concept(
        topic_id=topic.id,
        chapter_id=topic.chapter_id,
        course_id=topic.course_id,
        title=payload.title,
        description=payload.description,
        order=payload.order,
    )
    db.add(concept)
    db.commit()
    db.refresh(concept)
    return concept


def get_owned_concept(db: Session, user_id: uuid.UUID, concept_id: uuid.UUID) -> Concept:
    concept = db.get(Concept, concept_id)
    if concept is None:
        raise NotFoundError("Concept not found")
    get_owned_course(db, user_id, concept.course_id)
    return concept


def update_concept(
    db: Session, user_id: uuid.UUID, concept_id: uuid.UUID, payload: ConceptUpdate
) -> Concept:
    concept = get_owned_concept(db, user_id, concept_id)
    for field, value in payload.model_dump(exclude_unset=True).items():
        setattr(concept, field, value)
    db.commit()
    db.refresh(concept)
    return concept


def delete_concept(db: Session, user_id: uuid.UUID, concept_id: uuid.UUID) -> None:
    concept = get_owned_concept(db, user_id, concept_id)
    db.delete(concept)
    db.commit()


# --- Concept study-state machine (docs/PROJECT_SPEC.md §21, §22, §56, §60) ---
# Study State does NOT represent memory strength — it only gates whether a Concept is eligible
# to enter the (not-yet-built) SRS review system at all. The user drives every transition.

_NS, _S, _A, _P, _C = (
    StudyState.NOT_STUDIED,
    StudyState.STUDIED,
    StudyState.ACTIVE,
    StudyState.PAUSED,
    StudyState.COMPLETED,
)

# action -> (states it may start from, resulting state). Staying in the target state is always
# allowed (idempotent) where the target is among the allowed sources.
CONCEPT_TRANSITIONS: dict[str, tuple[frozenset[StudyState], StudyState]] = {
    # "I've read this" — before deciding to train it.
    "mark_studied": (frozenset({_NS, _S}), _S),
    # Enter active learning. Allowed from COMPLETED so finished material can be revisited;
    # not from PAUSED, which must go through resume (restoring, not re-activating).
    "activate": (frozenset({_NS, _S, _A, _C}), _A),
    "pause": (frozenset({_A}), _P),
    "resume": (frozenset({_P}), _A),
    # Leave active learning without discarding history; back to "studied".
    "deactivate": (frozenset({_A, _P}), _S),
    "complete": (frozenset(StudyState), _C),
}


def transition_concept(
    db: Session, user_id: uuid.UUID, concept_id: uuid.UUID, action: str
) -> Concept:
    allowed_from, target = CONCEPT_TRANSITIONS[action]
    concept = get_owned_concept(db, user_id, concept_id)
    if concept.study_state not in allowed_from:
        raise InvalidStateTransitionError(
            f"Cannot {action.replace('_', ' ')} a concept that is {concept.study_state.value}",
            details={"current_state": concept.study_state.value, "action": action},
        )
    concept.study_state = target
    db.commit()
    db.refresh(concept)
    return concept


# --- Pausing whole curriculum sections (docs/PROJECT_SPEC.md §56) ---
# A flag on the Topic/Chapter/Course, not a rewrite of every Concept below it: resuming just
# clears the flag, so a Concept the user had paused individually stays paused ("unpause restores
# their previous state"). Concept.is_reviewable combines both.


def set_course_paused(
    db: Session, user_id: uuid.UUID, course_id: uuid.UUID, paused: bool
) -> Course:
    course = get_owned_course(db, user_id, course_id)
    course.paused = paused
    db.commit()
    db.refresh(course)
    return course


def set_chapter_paused(
    db: Session, user_id: uuid.UUID, chapter_id: uuid.UUID, paused: bool
) -> Chapter:
    chapter = get_owned_chapter(db, user_id, chapter_id)
    chapter.paused = paused
    db.commit()
    db.refresh(chapter)
    return chapter


def set_topic_paused(db: Session, user_id: uuid.UUID, topic_id: uuid.UUID, paused: bool) -> Topic:
    topic = get_owned_topic(db, user_id, topic_id)
    topic.paused = paused
    db.commit()
    db.refresh(topic)
    return topic


# --- Order (drag and drop) ---


class _Ordered(Protocol):
    id: uuid.UUID
    order: int


def _apply_order[T: _Ordered](children: Sequence[T], ids: list[uuid.UUID]) -> None:
    """Numbers the children 0..n-1 in the order of `ids`, which must name each child exactly once:
    a client working from a stale list gets a 422 instead of a half-applied order."""
    by_id = {child.id: child for child in children}
    if len(ids) != len(by_id) or set(ids) != set(by_id):
        raise InvalidRequestError(
            "The list changed since it was loaded. Reload and try again.",
            details={"reason": "order_mismatch"},
        )
    for index, child_id in enumerate(ids):
        by_id[child_id].order = index


def reorder_chapters(
    db: Session, user_id: uuid.UUID, course_id: uuid.UUID, ids: list[uuid.UUID]
) -> None:
    get_owned_course(db, user_id, course_id)
    _apply_order(db.scalars(select(Chapter).where(Chapter.course_id == course_id)).all(), ids)
    db.commit()


def reorder_topics(
    db: Session, user_id: uuid.UUID, chapter_id: uuid.UUID, ids: list[uuid.UUID]
) -> None:
    get_owned_chapter(db, user_id, chapter_id)
    _apply_order(db.scalars(select(Topic).where(Topic.chapter_id == chapter_id)).all(), ids)
    db.commit()


def reorder_concepts(
    db: Session, user_id: uuid.UUID, topic_id: uuid.UUID, ids: list[uuid.UUID]
) -> None:
    get_owned_topic(db, user_id, topic_id)
    _apply_order(db.scalars(select(Concept).where(Concept.topic_id == topic_id)).all(), ids)
    db.commit()


def reorder_learning_items(
    db: Session, user_id: uuid.UUID, concept_id: uuid.UUID, ids: list[uuid.UUID]
) -> None:
    get_owned_concept(db, user_id, concept_id)
    items = db.scalars(select(LearningItem).where(LearningItem.concept_id == concept_id)).all()
    _apply_order(items, ids)
    db.commit()
