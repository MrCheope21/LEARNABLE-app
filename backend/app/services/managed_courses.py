"""Marketplace courses are read-only for the people who acquired them.

A course reached through the marketplace mirrors its author's content: the author edits it and
every acquirer's copy follows (services/marketplace.py syncs it). The acquirer studies it with
their own state (activation, pauses, schedule, answers, XP) but can't change the content.

Enforced once, before every flush, instead of in each of the many services that edit content:
adding, deleting or editing content rows of such a course is refused (409 `managed_course`),
whichever code path tries. Only the marketplace sync, which runs with `syncing(db)`, may.
"""

import uuid
from collections.abc import Iterator
from contextlib import contextmanager
from typing import Any

from sqlalchemy import event, inspect, select
from sqlalchemy.orm import Session

from app.core.errors import ConflictError
from app.models.course import Chapter, Concept, Course, Topic
from app.models.curriculum import ConceptSource, CurriculumProposal
from app.models.document import Document
from app.models.learning import LearningItem, LearningItemSource, QuestionFormulation

_SYNC_FLAG = "marketplace_sync"

# Content columns per model: what the author owns. Anything else (pauses, study state, training
# choice, priority, counters) is the acquirer's own and stays editable.
_CONTENT: dict[type, frozenset[str]] = {
    Course: frozenset(
        {"title", "description", "language", "marketplace_listing_id", "marketplace_version"}
    ),
    Chapter: frozenset({"title", "description", "order", "origin_key"}),
    Topic: frozenset({"title", "description", "order", "chapter_id", "origin_key"}),
    Concept: frozenset({"title", "description", "order", "topic_id", "chapter_id", "origin_key"}),
    LearningItem: frozenset(
        {
            "title",
            "objective",
            "expected_knowledge",
            "essential_points",
            "role",
            "difficulty",
            # `priority` is the user's own; the author's is `origin_priority`.
            "origin_priority",
            "origin_key",
            "answer_format",
            "reference_drawing_type",
            "order",
            "concept_id",
            "topic_id",
            "chapter_id",
        }
    ),
    QuestionFormulation: frozenset({"text", "question_type", "learning_item_id"}),
}
# Rows that are content as a whole: never added or removed in a managed course.
_CONTENT_ROWS = (
    Chapter,
    Topic,
    Concept,
    LearningItem,
    QuestionFormulation,
    Document,
    LearningItemSource,
    ConceptSource,
    CurriculumProposal,
)


def managed_error() -> ConflictError:
    return ConflictError(
        "This course comes from the marketplace: its content is kept up to date by its author "
        "and can't be changed here.",
        details={"reason": "managed_course"},
    )


def ensure_editable(course: Course) -> None:
    """For paths that write files before the database (drawings, uploads): refuse up front, so a
    managed course's files are never touched."""
    if course.marketplace_listing_id is not None:
        raise managed_error()


@contextmanager
def syncing(db: Session) -> Iterator[None]:
    """Lets the marketplace write a managed course's content (acquiring and syncing)."""
    db.info[_SYNC_FLAG] = True
    try:
        yield
    finally:
        db.info.pop(_SYNC_FLAG, None)


def _course_id(obj: Any) -> uuid.UUID | None:
    if isinstance(obj, Course):
        return obj.id
    return getattr(obj, "course_id", None)


def _managed(db: Session, course_ids: set[uuid.UUID]) -> set[uuid.UUID]:
    if not course_ids:
        return set()
    with db.no_autoflush:
        return set(
            db.scalars(
                select(Course.id).where(
                    Course.id.in_(course_ids), Course.marketplace_listing_id.is_not(None)
                )
            )
        )


@event.listens_for(Session, "before_flush")
def _refuse_content_changes(db: Session, _context: Any, _instances: Any) -> None:
    if db.info.get(_SYNC_FLAG):
        return
    added = [o for o in db.new if isinstance(o, _CONTENT_ROWS)]
    removed = [o for o in db.deleted if isinstance(o, _CONTENT_ROWS)]
    edited = [
        o
        for o in db.dirty
        if type(o) in _CONTENT
        and any(
            attr.key in _CONTENT[type(o)] and attr.history.has_changes()
            for attr in inspect(o).attrs
        )
    ]
    # A Course being deleted takes everything with it: that's the acquirer giving up access.
    deleting_courses = {o.id for o in db.deleted if isinstance(o, Course)}
    candidates = {
        cid
        for o in (*added, *removed, *edited)
        if (cid := _course_id(o)) is not None and cid not in deleting_courses
    }
    if _managed(db, candidates):
        raise managed_error()
