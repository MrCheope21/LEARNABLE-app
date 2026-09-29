"""Learning Items and their questions (docs/PROJECT_SPEC.md §24-29, §56)."""

import uuid

from fastapi import APIRouter, BackgroundTasks, Depends, status
from sqlalchemy.orm import Session, sessionmaker

from app.ai.factory import get_ai_provider
from app.ai.provider import AIProvider
from app.api.curriculum import get_max_context_chars
from app.auth.dependencies import get_current_user
from app.db.session import get_db, get_session_factory
from app.models.course import Concept
from app.models.document import DocumentChunk
from app.models.learning import LearningItem, QuestionFormulation
from app.models.user import User
from app.schemas.courses import ConceptRead
from app.schemas.documents import ChunkRead
from app.schemas.learning import (
    BulkItemAction,
    BulkItemResult,
    LearningItemCreate,
    LearningItemRead,
    LearningItemUpdate,
    QuestionCreate,
    QuestionGenerate,
    QuestionRead,
    QuestionUpdate,
)
from app.services.learning import manage, service

router = APIRouter(tags=["learning-items"])

CurrentUser = Depends(get_current_user)
DB = Depends(get_db)


@router.post(
    "/concepts/{concept_id}/learning-items/generate",
    response_model=ConceptRead,
    status_code=status.HTTP_202_ACCEPTED,
)
def generate_learning_items(
    concept_id: uuid.UUID,
    background_tasks: BackgroundTasks,
    db: Session = DB,
    user: User = CurrentUser,
    provider: AIProvider | None = Depends(get_ai_provider),
    session_factory: sessionmaker[Session] = Depends(get_session_factory),
    max_context_chars: int = Depends(get_max_context_chars),
) -> Concept:
    """Starts generation in the background (202, `item_generation_status: GENERATING`); poll
    the Concept or its item list. Activation starts it automatically when possible."""
    concept, ready = service.request_generation(db, provider, user.id, concept_id)
    background_tasks.add_task(
        service.generate_items, session_factory, ready, concept.id, max_context_chars
    )
    return concept


@router.get("/concepts/{concept_id}/learning-items", response_model=list[LearningItemRead])
def list_learning_items(
    concept_id: uuid.UUID, db: Session = DB, user: User = CurrentUser
) -> list[LearningItem]:
    return service.list_items(db, user.id, concept_id)


@router.post(
    "/concepts/{concept_id}/learning-items",
    response_model=LearningItemRead,
    status_code=status.HTTP_201_CREATED,
)
def create_learning_item(
    concept_id: uuid.UUID,
    payload: LearningItemCreate,
    db: Session = DB,
    user: User = CurrentUser,
) -> LearningItem:
    return service.create_item(db, user.id, concept_id, payload)


@router.get("/learning-items/{item_id}", response_model=LearningItemRead)
def get_learning_item(
    item_id: uuid.UUID, db: Session = DB, user: User = CurrentUser
) -> LearningItem:
    return service.get_owned_item(db, user.id, item_id)


@router.patch("/learning-items/{item_id}", response_model=LearningItemRead)
def update_learning_item(
    item_id: uuid.UUID, payload: LearningItemUpdate, db: Session = DB, user: User = CurrentUser
) -> LearningItem:
    return service.update_item(db, user.id, item_id, payload)


@router.delete("/learning-items/{item_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_learning_item(item_id: uuid.UUID, db: Session = DB, user: User = CurrentUser) -> None:
    service.delete_item(db, user.id, item_id)


@router.post("/learning-items/{item_id}/train", response_model=LearningItemRead)
def train_learning_item(
    item_id: uuid.UUID, db: Session = DB, user: User = CurrentUser
) -> LearningItem:
    """Puts the item into spaced repetition (e.g. promoting informational content)."""
    return service.set_in_training(db, user.id, item_id, in_training=True)


@router.post("/learning-items/{item_id}/untrain", response_model=LearningItemRead)
def untrain_learning_item(
    item_id: uuid.UUID, db: Session = DB, user: User = CurrentUser
) -> LearningItem:
    """Takes the item out of spaced repetition, keeping its sources, questions and history."""
    return service.set_in_training(db, user.id, item_id, in_training=False)


@router.post("/learning-items/{item_id}/pause", response_model=LearningItemRead)
def pause_learning_item(
    item_id: uuid.UUID, db: Session = DB, user: User = CurrentUser
) -> LearningItem:
    return service.set_paused(db, user.id, item_id, paused=True)


@router.post("/learning-items/{item_id}/resume", response_model=LearningItemRead)
def resume_learning_item(
    item_id: uuid.UUID, db: Session = DB, user: User = CurrentUser
) -> LearningItem:
    return service.set_paused(db, user.id, item_id, paused=False)


@router.post(
    "/learning-items/{item_id}/questions",
    response_model=QuestionRead,
    status_code=status.HTTP_201_CREATED,
)
def add_question(
    item_id: uuid.UUID, payload: QuestionCreate, db: Session = DB, user: User = CurrentUser
) -> QuestionFormulation:
    return service.add_question(db, user.id, item_id, payload)


@router.post(
    "/learning-items/{item_id}/questions/generate",
    response_model=list[QuestionRead],
    status_code=status.HTTP_201_CREATED,
)
def generate_questions(
    item_id: uuid.UUID,
    payload: QuestionGenerate,
    db: Session = DB,
    user: User = CurrentUser,
    provider: AIProvider | None = Depends(get_ai_provider),
    max_context_chars: int = Depends(get_max_context_chars),
) -> list[QuestionFormulation]:
    """AI-written new formulations of this item, from its own passages (201, the new ones).
    409 when the item has no sources or they aren't enough; 503/502 on AI failure."""
    return service.generate_questions(db, provider, user.id, item_id, payload, max_context_chars)


@router.get("/learning-items/{item_id}/sources", response_model=list[ChunkRead])
def list_learning_item_sources(
    item_id: uuid.UUID, db: Session = DB, user: User = CurrentUser
) -> list[DocumentChunk]:
    return service.list_item_sources(db, user.id, item_id)


# --- Managing a Course's questions ---


@router.get("/courses/{course_id}/learning-items", response_model=list[LearningItemRead])
def list_course_items(
    course_id: uuid.UUID, db: Session = DB, user: User = CurrentUser
) -> list[LearningItem]:
    """Every Learning Item of the Course with its questions, in course order."""
    return manage.list_course_items(db, user.id, course_id)


@router.post("/courses/{course_id}/learning-items/bulk", response_model=BulkItemResult)
def bulk_items(
    course_id: uuid.UUID, payload: BulkItemAction, db: Session = DB, user: User = CurrentUser
) -> BulkItemResult:
    """Delete, pause, resume or move many items at once; all or nothing (404 if any id isn't one
    of this Course's items). Moving keeps each item's memory state and history."""
    return manage.bulk(db, user.id, course_id, payload)


@router.patch("/questions/{question_id}", response_model=QuestionRead)
def update_question(
    question_id: uuid.UUID, payload: QuestionUpdate, db: Session = DB, user: User = CurrentUser
) -> QuestionFormulation:
    """Rewords one question; its item's memory state is kept."""
    return manage.update_question(db, user.id, question_id, payload)


@router.delete("/questions/{question_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_question(question_id: uuid.UUID, db: Session = DB, user: User = CurrentUser) -> None:
    """Deletes one wording (409 `last_question` for the item's only one: delete the item)."""
    manage.delete_question(db, user.id, question_id)
