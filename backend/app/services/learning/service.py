"""Learning Items: generation, editing, training and pause (docs/PROJECT_SPEC.md §24-29, §56).

    Concept activated (or generation requested) → background: the Concept's own source passages
    → AIProvider → items grounded in those passages, each with its questions and a NEW memory
    state → LEARN sessions encode them → the SchedulingPolicy takes over.

The Concept is never scheduled: each Learning Item has its own ReviewState, shared by all of its
QuestionFormulations. Whether an item is trained is `in_training`, set from the AI's suggested
role and then the user's to change; removing an item from training keeps its sources,
questions and history.

Privacy (spec §70, §94): source text and AI output are never logged, only ids and error types.
"""

import logging
import uuid

from sqlalchemy import func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session, selectinload, sessionmaker

from app.ai.provider import AIProvider, LearningItemsResult
from app.ai.schemas import (
    LearningItemsRequest,
    ProposedLearningItem,
    QuestionsRequest,
    SourcePassage,
)
from app.core.errors import AINotConfiguredError, AppError, ConflictError, NotFoundError
from app.db.types import utc_now
from app.models.course import Chapter, Concept, Course, Topic
from app.models.curriculum import ConceptSource
from app.models.document import Document, DocumentChunk
from app.models.enums import TRAINABLE_ROLES, ItemGenerationStatus, QuestionType, default_priority
from app.models.learning import LearningItem, LearningItemSource, QuestionFormulation, ReviewState
from app.schemas.learning import (
    LearningItemCreate,
    LearningItemUpdate,
    QuestionCreate,
    QuestionGenerate,
)
from app.services.courses.service import get_owned_concept, get_owned_course
from app.services.recovery import STALE_JOB_AFTER
from app.services.scheduling.policy import get_policy
from app.services.scheduling.store import policy_for, snapshot_of, store

logger = logging.getLogger(__name__)

_NO_SOURCES = (
    "This concept has no source passages, so there is nothing to build learning items from. "
    "Add them by hand, or link material through a curriculum proposal."
)
_INSUFFICIENT = "The source material doesn't contain enough to build learning items from."
_UNEXPECTED_FAILURE = "The learning items couldn't be generated."

Status = ItemGenerationStatus


# --- Generation ---


def request_generation(
    db: Session, provider: AIProvider | None, user_id: uuid.UUID, concept_id: uuid.UUID
) -> tuple[Concept, AIProvider]:
    """Validates and marks the Concept GENERATING; the caller schedules `generate_items`."""
    concept = get_owned_concept(db, user_id, concept_id)
    if provider is None:
        raise AINotConfiguredError("AI features are not configured on this server.")
    reason = _cannot_generate(db, concept)
    if reason == "running":
        raise ConflictError(
            "Learning items are already being generated for this concept.",
            details={"reason": "generation_running"},
        )
    if reason == "items_exist":
        raise ConflictError(
            "This concept already has learning items.", details={"reason": "items_exist"}
        )
    if reason == "no_sources":
        raise ConflictError(_NO_SOURCES, details={"reason": "no_source_material"})
    _mark_generating(db, concept)
    return concept, provider


def start_generation_on_activation(
    db: Session, provider: AIProvider | None, concept: Concept
) -> AIProvider | None:
    """Activation leads to Learning Items (spec §21): when the Concept has none yet, has
    sources, and AI is configured, generation starts and the provider to schedule
    `generate_items` with is returned. Never fails the activation itself."""
    if provider is None or _cannot_generate(db, concept) is not None:
        return None
    _mark_generating(db, concept)
    return provider


def _cannot_generate(db: Session, concept: Concept) -> str | None:
    started = concept.item_generation_started_at
    if (
        concept.item_generation_status is Status.GENERATING
        and started is not None
        and utc_now() - started < STALE_JOB_AFTER
    ):
        return "running"
    if db.scalar(select(LearningItem.id).where(LearningItem.concept_id == concept.id).limit(1)):
        return "items_exist"
    if not _source_chunk_ids(db, concept):
        return "no_sources"
    return None


def _mark_generating(db: Session, concept: Concept) -> None:
    concept.item_generation_status = Status.GENERATING
    concept.item_generation_error = None
    concept.item_generation_started_at = utc_now()
    db.commit()
    db.refresh(concept)


def _source_chunk_ids(db: Session, concept: Concept) -> list[uuid.UUID]:
    return list(
        db.scalars(
            select(ConceptSource.chunk_id)
            .join(DocumentChunk, DocumentChunk.id == ConceptSource.chunk_id)
            .where(
                ConceptSource.concept_id == concept.id,
                ConceptSource.course_id == concept.course_id,
                DocumentChunk.course_id == concept.course_id,
            )
            .order_by(ConceptSource.created_at, DocumentChunk.position)
        )
    )


def generate_items(
    session_factory: sessionmaker[Session],
    provider: AIProvider,
    concept_id: uuid.UUID,
    max_context_chars: int,
) -> None:
    """Background task. As for curriculum generation, the AI call holds no database session."""
    with session_factory() as db:
        concept = db.get(Concept, concept_id)
        if concept is None or concept.item_generation_status is not Status.GENERATING:
            return
        topic = db.get(Topic, concept.topic_id)
        chapter = db.get(Chapter, concept.chapter_id)
        course = db.get(Course, concept.course_id)
        if topic is None or chapter is None or course is None:
            return
        passages, chunk_refs = _collect_passages(db, concept, max_context_chars)
        request = LearningItemsRequest(
            course_title=course.title,
            chapter_title=chapter.title,
            topic_title=topic.title,
            concept_title=concept.title,
            concept_description=concept.description,
            language=course.language,
            passages=passages,
        )

    result: LearningItemsResult | None = None
    failure: str | None = _INSUFFICIENT if not passages else None
    if passages:
        try:
            result = provider.generate_learning_items(request)
        except AppError as exc:
            failure = exc.message
        except Exception:
            logger.exception("Unexpected failure generating learning items for %s", concept_id)
            failure = _UNEXPECTED_FAILURE

    with session_factory() as db:
        concept = db.get(Concept, concept_id)
        if concept is None or concept.item_generation_status is not Status.GENERATING:
            return
        if result is None:
            concept.item_generation_status = (
                Status.INSUFFICIENT_CONTEXT if failure == _INSUFFICIENT else Status.FAILED
            )
            concept.item_generation_error = failure
        else:
            _store_items(db, concept, result, chunk_refs)
        try:
            db.commit()
        except IntegrityError:
            db.rollback()  # the Concept was deleted meanwhile


def _collect_passages(
    db: Session, concept: Concept, max_chars: int
) -> tuple[list[SourcePassage], dict[str, uuid.UUID]]:
    rows = db.execute(
        select(DocumentChunk, Document.filename)
        .join(ConceptSource, ConceptSource.chunk_id == DocumentChunk.id)
        .join(Document, Document.id == DocumentChunk.document_id)
        .where(
            ConceptSource.concept_id == concept.id,
            ConceptSource.course_id == concept.course_id,
            DocumentChunk.course_id == concept.course_id,
            Document.course_id == concept.course_id,
        )
        .order_by(ConceptSource.created_at, DocumentChunk.position)
    ).all()
    passages: list[SourcePassage] = []
    refs: dict[str, uuid.UUID] = {}
    used = 0
    for chunk, filename in rows:
        if passages and used + len(chunk.text) > max_chars:
            break
        ref = f"S{len(passages) + 1}"
        passages.append(
            SourcePassage(
                ref=ref,
                document_name=filename,
                page_number=chunk.page_number,
                page_end=chunk.page_end,
                section=chunk.section,
                text=chunk.text,
            )
        )
        refs[ref] = chunk.id
        used += len(chunk.text)
    return passages, refs


def _store_items(
    db: Session, concept: Concept, result: LearningItemsResult, chunk_refs: dict[str, uuid.UUID]
) -> None:
    """Grounding in code (spec §19): an item citing no passage that was sent is dropped."""
    if db.scalar(select(LearningItem.id).where(LearningItem.concept_id == concept.id).limit(1)):
        concept.item_generation_status = Status.READY  # someone added items meanwhile
        return
    info = result.info
    created = 0
    dropped = 0
    if result.output.context_sufficient:
        for proposed in result.output.items:
            chunk_ids = list(
                dict.fromkeys(chunk_refs[r] for r in proposed.source_refs if r in chunk_refs)
            )
            if not chunk_ids:
                dropped += 1
                continue
            item = new_item(db, concept, proposed, order=created)
            item.ai_provider = info.provider[:50]
            item.ai_model = info.model[:200]
            item.ai_model_version = info.model_version[:200]
            item.prompt_version = info.prompt_version[:100]
            db.add_all(
                LearningItemSource(
                    learning_item_id=item.id, chunk_id=chunk_id, course_id=concept.course_id
                )
                for chunk_id in chunk_ids
            )
            created += 1
    if created:
        concept.item_generation_status = Status.READY
        concept.item_generation_error = None
    else:
        concept.item_generation_status = Status.INSUFFICIENT_CONTEXT
        concept.item_generation_error = _INSUFFICIENT
    if dropped:
        logger.info("learning_items concept=%s dropped_uncited=%d", concept.id, dropped)


def new_item(
    db: Session,
    concept: Concept,
    proposed: ProposedLearningItem | LearningItemCreate,
    order: int,
) -> LearningItem:
    item = LearningItem(
        id=uuid.uuid4(),
        concept_id=concept.id,
        topic_id=concept.topic_id,
        chapter_id=concept.chapter_id,
        course_id=concept.course_id,
        title=proposed.title,
        objective=proposed.objective,
        expected_knowledge=proposed.expected_knowledge,
        essential_points=list(proposed.essential_points),
        role=proposed.role,
        priority=getattr(proposed, "priority", None) or default_priority(proposed.role),
        # An item can only be trained if there is something to ask.
        in_training=proposed.role in TRAINABLE_ROLES and bool(proposed.questions),
        difficulty=proposed.difficulty,
        order=order,
    )
    policy = get_policy()
    item.review_state = ReviewState(
        course_id=concept.course_id,
        scheduling_policy=policy.name,
        scheduling_policy_version=policy.version,
    )
    item.questions = [
        QuestionFormulation(course_id=concept.course_id, question_type=q.question_type, text=q.text)
        for q in proposed.questions
    ]
    db.add(item)
    db.flush()
    return item


# --- Reading and editing ---


def get_owned_item(db: Session, user_id: uuid.UUID, item_id: uuid.UUID) -> LearningItem:
    item = db.get(LearningItem, item_id)
    if item is None:
        raise NotFoundError("Learning item not found")
    get_owned_course(db, user_id, item.course_id)
    return item


def list_items(db: Session, user_id: uuid.UUID, concept_id: uuid.UUID) -> list[LearningItem]:
    concept = get_owned_concept(db, user_id, concept_id)
    return list(
        db.scalars(
            select(LearningItem)
            .where(LearningItem.concept_id == concept.id)
            .order_by(LearningItem.order, LearningItem.created_at)
            .options(selectinload(LearningItem.questions), selectinload(LearningItem.review_state))
        )
    )


def create_item(
    db: Session, user_id: uuid.UUID, concept_id: uuid.UUID, payload: LearningItemCreate
) -> LearningItem:
    concept = get_owned_concept(db, user_id, concept_id)
    last = db.scalar(
        select(func.max(LearningItem.order)).where(LearningItem.concept_id == concept.id)
    )
    item = new_item(db, concept, payload, order=0 if last is None else last + 1)
    db.commit()
    db.refresh(item)
    return item


def update_item(
    db: Session, user_id: uuid.UUID, item_id: uuid.UUID, payload: LearningItemUpdate
) -> LearningItem:
    """Edits content. Memory state is untouched: rewording an item doesn't reset what the user
    remembers (and only the SchedulingPolicy moves it anyway)."""
    item = get_owned_item(db, user_id, item_id)
    for field, value in payload.model_dump(exclude_unset=True).items():
        setattr(item, field, value)
    db.commit()
    db.refresh(item)
    return item


def delete_item(db: Session, user_id: uuid.UUID, item_id: uuid.UUID) -> None:
    """Deletes the item with its questions, memory state and history. To stop training it but
    keep everything, use `set_in_training(False)`."""
    item = get_owned_item(db, user_id, item_id)
    db.delete(item)
    db.commit()


def set_in_training(
    db: Session, user_id: uuid.UUID, item_id: uuid.UUID, in_training: bool
) -> LearningItem:
    """Promote informational content into training, or take an item out of it (spec §24).
    Nothing is deleted either way; memory state and history are kept."""
    item = get_owned_item(db, user_id, item_id)
    if in_training and not item.questions:
        raise ConflictError(
            "Add at least one question before training this item.",
            details={"reason": "no_questions"},
        )
    item.in_training = in_training
    db.commit()
    db.refresh(item)
    return item


def set_paused(db: Session, user_id: uuid.UUID, item_id: uuid.UUID, paused: bool) -> LearningItem:
    """Item-level pause (spec §56), through the SchedulingPolicy so resuming restores the
    remaining interval instead of making the item overdue."""
    item = get_owned_item(db, user_id, item_id)
    state = item.review_state
    policy = policy_for(state)
    now = utc_now()
    snapshot = snapshot_of(state)
    store(state, policy.pause(snapshot, now) if paused else policy.resume(snapshot, now))
    item.paused = paused
    db.commit()
    db.refresh(item)
    return item


def add_question(
    db: Session, user_id: uuid.UUID, item_id: uuid.UUID, payload: QuestionCreate
) -> QuestionFormulation:
    """Another formulation of the same item: shares its one memory state (spec §27)."""
    item = get_owned_item(db, user_id, item_id)
    question = QuestionFormulation(
        learning_item_id=item.id,
        course_id=item.course_id,
        question_type=payload.question_type,
        text=payload.text,
    )
    db.add(question)
    db.commit()
    db.refresh(question)
    return question


_DEFAULT_QUESTION_TYPES = [
    QuestionType.EXPLANATION,
    QuestionType.APPLICATION,
    QuestionType.SCENARIO,
]


def generate_questions(
    db: Session,
    provider: AIProvider | None,
    user_id: uuid.UUID,
    item_id: uuid.UUID,
    payload: QuestionGenerate,
    max_context_chars: int,
) -> list[QuestionFormulation]:
    """New AI-written formulations of an existing Learning Item (spec §27-29). They test what
    the item already tests, from the item's own passages only, and share its memory state: no
    review state is created or changed."""
    item = get_owned_item(db, user_id, item_id)  # ownership first: an intruder gets 404
    if provider is None:
        raise AINotConfiguredError("AI is not configured on this server")
    passages = _item_passages(db, item, max_context_chars)
    if not passages:
        raise ConflictError(
            "This learning item has no source material to write questions from.",
            details={"reason": "no_sources"},
        )
    concept = db.get(Concept, item.concept_id)
    course = db.get(Course, item.course_id)
    if concept is None or course is None:
        raise NotFoundError("Learning item not found")
    request = QuestionsRequest(
        course_title=course.title,
        concept_title=concept.title,
        item_title=item.title,
        objective=item.objective,
        expected_knowledge=item.expected_knowledge,
        essential_points=list(item.essential_points),
        question_types=payload.question_types or _DEFAULT_QUESTION_TYPES,
        count=payload.count,
        language=course.language,
        passages=passages,
        existing_questions=[q.text for q in item.questions],
    )
    db.commit()  # no transaction held open during the AI call

    result = provider.generate_questions(request)
    if not result.output.context_sufficient:
        raise ConflictError(
            "The item's material isn't enough to write new questions.",
            details={"reason": "insufficient_context"},
        )
    item = get_owned_item(db, user_id, item_id)
    seen = {q.text.strip().lower() for q in item.questions}
    info = result.info
    created = []
    for proposed in result.output.questions[: payload.count]:
        key = proposed.text.strip().lower()
        if key in seen:
            continue
        seen.add(key)
        question = QuestionFormulation(
            learning_item_id=item.id,
            course_id=item.course_id,
            question_type=proposed.question_type,
            text=proposed.text,
            ai_provider=info.provider[:50],
            ai_model=info.model[:200],
            ai_model_version=info.model_version[:200],
            prompt_version=info.prompt_version[:100],
        )
        db.add(question)
        created.append(question)
    db.commit()
    for question in created:
        db.refresh(question)
    return created


def _item_passages(db: Session, item: LearningItem, max_chars: int) -> list[SourcePassage]:
    rows = db.execute(
        select(DocumentChunk, Document.filename)
        .join(LearningItemSource, LearningItemSource.chunk_id == DocumentChunk.id)
        .join(Document, Document.id == DocumentChunk.document_id)
        .where(
            LearningItemSource.learning_item_id == item.id,
            LearningItemSource.course_id == item.course_id,
            DocumentChunk.course_id == item.course_id,
            Document.course_id == item.course_id,
        )
        .order_by(LearningItemSource.created_at, DocumentChunk.position)
    ).all()
    passages: list[SourcePassage] = []
    used = 0
    for chunk, filename in rows:
        if passages and used + len(chunk.text) > max_chars:
            break
        passages.append(
            SourcePassage(
                ref=f"S{len(passages) + 1}",
                document_name=filename,
                page_number=chunk.page_number,
                page_end=chunk.page_end,
                section=chunk.section,
                text=chunk.text,
            )
        )
        used += len(chunk.text)
    return passages


def list_item_sources(db: Session, user_id: uuid.UUID, item_id: uuid.UUID) -> list[DocumentChunk]:
    item = get_owned_item(db, user_id, item_id)
    return list(
        db.scalars(
            select(DocumentChunk)
            .join(LearningItemSource, LearningItemSource.chunk_id == DocumentChunk.id)
            .where(
                LearningItemSource.learning_item_id == item.id,
                LearningItemSource.course_id == item.course_id,
                DocumentChunk.course_id == item.course_id,
            )
            .order_by(LearningItemSource.created_at, DocumentChunk.position)
        )
    )
