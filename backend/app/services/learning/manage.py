"""Managing a Course's questions: edit or delete one wording, and act on many Learning Items at
once (delete, pause, resume, move) (docs/API.md "Managing questions").

A "question" as the user sees it is a Learning Item: its wordings (QuestionFormulations) share
one memory state, and it sits under a Concept in a Topic of a Chapter. Moving it never touches
its memory state or history; only where it lives changes.
"""

import uuid
from collections import defaultdict
from dataclasses import dataclass

from sqlalchemy import func, select
from sqlalchemy.orm import Session, selectinload

from app.core.errors import ConflictError, InvalidRequestError, NotFoundError
from app.db.types import utc_now
from app.models.course import Chapter, Concept, Topic
from app.models.curriculum import ConceptSource
from app.models.enums import ItemGenerationStatus
from app.models.learning import LearningItem, LearningItemSource, QuestionFormulation
from app.schemas.learning import BulkItemAction, BulkItemResult, QuestionUpdate
from app.services.courses.service import get_owned_course
from app.services.scheduling.store import policy_for, snapshot_of, store

# --- One wording ---


def get_owned_question(
    db: Session, user_id: uuid.UUID, question_id: uuid.UUID
) -> QuestionFormulation:
    question = db.get(QuestionFormulation, question_id)
    if question is None:
        raise NotFoundError("Question not found")
    get_owned_course(db, user_id, question.course_id)
    return question


def update_question(
    db: Session, user_id: uuid.UUID, question_id: uuid.UUID, payload: QuestionUpdate
) -> QuestionFormulation:
    """Rewording keeps the item's memory state: it's still the same thing to remember."""
    question = get_owned_question(db, user_id, question_id)
    for field, value in payload.model_dump(exclude_unset=True).items():
        setattr(question, field, value)
    if "text" in payload.model_fields_set:
        question.hint = None  # rebuilt from the reference on the next reveal
    db.commit()
    db.refresh(question)
    return question


def delete_question(db: Session, user_id: uuid.UUID, question_id: uuid.UUID) -> None:
    """Deletes one wording. The last one can't go: delete the whole item instead (409)."""
    question = get_owned_question(db, user_id, question_id)
    remaining = db.scalar(
        select(func.count())
        .select_from(QuestionFormulation)
        .where(QuestionFormulation.learning_item_id == question.learning_item_id)
    )
    if (remaining or 0) <= 1:
        raise ConflictError(
            "This is the item's only question. Delete the whole item instead.",
            details={"reason": "last_question"},
        )
    db.delete(question)
    db.commit()


# --- The Course's items, for the management view ---


def list_course_items(db: Session, user_id: uuid.UUID, course_id: uuid.UUID) -> list[LearningItem]:
    get_owned_course(db, user_id, course_id)
    return list(
        db.scalars(
            select(LearningItem)
            .join(Concept, Concept.id == LearningItem.concept_id)
            .join(Topic, Topic.id == LearningItem.topic_id)
            .join(Chapter, Chapter.id == LearningItem.chapter_id)
            .where(LearningItem.course_id == course_id)
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
            .options(selectinload(LearningItem.questions), selectinload(LearningItem.review_state))
        )
    )


# --- Many items at once ---


@dataclass
class _Counts:
    affected: int = 0
    created_concepts: int = 0
    deleted_concepts: int = 0


def bulk(
    db: Session, user_id: uuid.UUID, course_id: uuid.UUID, payload: BulkItemAction
) -> BulkItemResult:
    """All or nothing: every id must be one of this Course's items (404 otherwise, identical to a
    missing id), and nothing changes unless the whole request is valid."""
    get_owned_course(db, user_id, course_id)
    wanted = list(dict.fromkeys(payload.item_ids))
    items = list(
        db.scalars(
            select(LearningItem).where(
                LearningItem.course_id == course_id, LearningItem.id.in_(wanted)
            )
        )
    )
    if len(items) != len(wanted):
        raise NotFoundError("Learning item not found")

    counts = _Counts(affected=len(items))
    touched_concepts = {item.concept_id for item in items}
    if payload.action == "delete":
        for item in items:
            db.delete(item)
        db.flush()
    elif payload.action in ("pause", "resume"):
        _set_paused(items, paused=payload.action == "pause")
    elif payload.action == "set_priority":
        if payload.priority is None:
            raise InvalidRequestError("Choose a priority: 1 Essential, 2 Important or 3 Extra.")
        for item in items:
            item.priority = payload.priority
    elif payload.action == "move":
        _move(db, course_id, items, payload, counts)
    if payload.action in ("delete", "move") and payload.delete_emptied_concepts:
        counts.deleted_concepts = _delete_empty(db, touched_concepts)
    db.commit()
    return BulkItemResult(
        affected=counts.affected,
        created_concepts=counts.created_concepts,
        deleted_concepts=counts.deleted_concepts,
    )


def _set_paused(items: list[LearningItem], *, paused: bool) -> None:
    """Through the SchedulingPolicy, like the single-item pause: resuming restores the interval
    that was left instead of making the item overdue."""
    now = utc_now()
    for item in items:
        if item.paused == paused:
            continue
        state = item.review_state
        policy = policy_for(state)
        snapshot = snapshot_of(state)
        store(state, policy.pause(snapshot, now) if paused else policy.resume(snapshot, now))
        item.paused = paused


def _move(
    db: Session,
    course_id: uuid.UUID,
    items: list[LearningItem],
    payload: BulkItemAction,
    counts: _Counts,
) -> None:
    if (payload.target_concept_id is None) == (payload.target_topic_id is None):
        raise InvalidRequestError(
            "Moving needs exactly one destination: a concept or a topic.",
            details={"reason": "move_target"},
        )
    if payload.target_concept_id is not None:
        target = db.get(Concept, payload.target_concept_id)
        if target is None or target.course_id != course_id:
            raise NotFoundError("Concept not found")
        _into_concept(db, items, target)
        return
    topic = db.get(Topic, payload.target_topic_id)
    if topic is None or topic.course_id != course_id:
        raise NotFoundError("Topic not found")
    _into_topic(db, items, topic, counts)


def _into_concept(db: Session, items: list[LearningItem], target: Concept) -> None:
    """The items join the target Concept, after its own items. The Concept gains the items'
    source passages, so "View source" on it still covers them."""
    order = _next_item_order(db, target.id)
    for item in items:
        if item.concept_id == target.id:
            continue
        item.concept_id = target.id
        item.topic_id = target.topic_id
        item.chapter_id = target.chapter_id
        item.order = order
        order += 1
    db.flush()
    _link_sources(db, target, [item.id for item in items])


def _into_topic(db: Session, items: list[LearningItem], topic: Topic, counts: _Counts) -> None:
    """Each item keeps a Concept of its own kind in the target Topic. A Concept whose items are
    all selected moves as a whole (with its sources and state); from a Concept only partly
    selected, the selected items move into a new Concept with the same title and state (so a
    question bank's "one question, one concept" survives the move)."""
    by_concept: dict[uuid.UUID, list[LearningItem]] = defaultdict(list)
    for item in items:
        by_concept[item.concept_id].append(item)
    order = _next_concept_order(db, topic.id)
    for concept_id, moving in by_concept.items():
        concept = db.get(Concept, concept_id)
        if concept is None:
            continue
        total = db.scalar(
            select(func.count())
            .select_from(LearningItem)
            .where(LearningItem.concept_id == concept_id)
        )
        if total == len(moving):
            if concept.topic_id != topic.id:
                concept.topic_id = topic.id
                concept.chapter_id = topic.chapter_id
                concept.order = order
                order += 1
            for item in moving:
                item.topic_id = topic.id
                item.chapter_id = topic.chapter_id
            continue
        split = Concept(
            id=uuid.uuid4(),
            topic_id=topic.id,
            chapter_id=topic.chapter_id,
            course_id=concept.course_id,
            title=concept.title,
            description=concept.description,
            order=order,
            study_state=concept.study_state,
            item_generation_status=ItemGenerationStatus.READY,
        )
        order += 1
        db.add(split)
        db.flush()
        counts.created_concepts += 1
        for index, item in enumerate(moving):
            item.concept_id = split.id
            item.topic_id = topic.id
            item.chapter_id = topic.chapter_id
            item.order = index
        db.flush()
        _link_sources(db, split, [item.id for item in moving])


def _link_sources(db: Session, concept: Concept, item_ids: list[uuid.UUID]) -> None:
    chunk_ids = set(
        db.scalars(
            select(LearningItemSource.chunk_id).where(
                LearningItemSource.learning_item_id.in_(item_ids)
            )
        )
    )
    existing = set(
        db.scalars(select(ConceptSource.chunk_id).where(ConceptSource.concept_id == concept.id))
    )
    for chunk_id in chunk_ids - existing:
        db.add(ConceptSource(concept_id=concept.id, chunk_id=chunk_id, course_id=concept.course_id))
    if chunk_ids:
        concept.needs_source_review = False


def _delete_empty(db: Session, concept_ids: set[uuid.UUID]) -> int:
    """Concepts that lost every item in this request go too: they only held those questions."""
    db.flush()
    deleted = 0
    for concept_id in concept_ids:
        left = db.scalar(
            select(func.count())
            .select_from(LearningItem)
            .where(LearningItem.concept_id == concept_id)
        )
        concept = db.get(Concept, concept_id)
        if concept is not None and not left:
            db.delete(concept)
            deleted += 1
    return deleted


def _next_item_order(db: Session, concept_id: uuid.UUID) -> int:
    last = db.scalar(
        select(func.max(LearningItem.order)).where(LearningItem.concept_id == concept_id)
    )
    return 0 if last is None else last + 1


def _next_concept_order(db: Session, topic_id: uuid.UUID) -> int:
    last = db.scalar(select(func.max(Concept.order)).where(Concept.topic_id == topic_id))
    return 0 if last is None else last + 1
