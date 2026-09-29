"""Course hierarchy CRUD + ownership/isolation enforcement (docs/PROJECT_SPEC.md §10, §81).

Every `get_owned_*` function is the single point where a resource's Course scope is verified
against the requesting user — API handlers never touch models directly, and no query here trusts
a client-supplied id without checking it traces back to a Course the caller owns.
"""

import uuid

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.errors import InvalidStateTransitionError, NotFoundError
from app.models.course import Chapter, Concept, Course, CourseSettings, Topic
from app.models.document import Document
from app.models.enums import StudyState
from app.schemas.courses import (
    ChapterCreate,
    ChapterUpdate,
    ConceptCreate,
    ConceptUpdate,
    CourseCreate,
    CourseUpdate,
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
