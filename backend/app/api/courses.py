"""Course hierarchy + Concept activation endpoints.

Handlers stay thin: authentication via `get_current_user`, then delegate to the service. Service
errors (NotFoundError → 404, InvalidStateTransitionError → 409) are translated centrally by
app/api/errors.py.
"""

import uuid

from fastapi import APIRouter, BackgroundTasks, Depends, status
from sqlalchemy.orm import Session, sessionmaker

from app.ai.factory import get_ai_provider
from app.ai.provider import AIProvider
from app.api.curriculum import get_max_context_chars
from app.auth.dependencies import get_current_user
from app.db.session import get_db, get_session_factory
from app.models.course import Chapter, Concept, Course, Topic
from app.models.user import User
from app.schemas.courses import (
    ChapterCreate,
    ChapterRead,
    ChapterUpdate,
    ConceptCreate,
    ConceptRead,
    ConceptUpdate,
    CourseCreate,
    CourseRead,
    CourseUpdate,
    OrderUpdate,
    TopicCreate,
    TopicRead,
    TopicUpdate,
)
from app.services.courses import service
from app.services.documents.service import delete_course_files
from app.services.learning import service as learning_service
from app.storage.documents import DocumentStorage, get_document_storage

router = APIRouter(tags=["courses"])

CurrentUser = Depends(get_current_user)
DB = Depends(get_db)


# --- Courses ---


@router.post("/courses", response_model=CourseRead, status_code=status.HTTP_201_CREATED)
def create_course(payload: CourseCreate, db: Session = DB, user: User = CurrentUser) -> Course:
    return service.create_course(db, user.id, payload)


@router.get("/courses", response_model=list[CourseRead])
def list_courses(db: Session = DB, user: User = CurrentUser) -> list[Course]:
    return service.list_courses(db, user.id)


@router.get("/courses/{course_id}", response_model=CourseRead)
def get_course(course_id: uuid.UUID, db: Session = DB, user: User = CurrentUser) -> Course:
    return service.get_owned_course(db, user.id, course_id)


@router.patch("/courses/{course_id}", response_model=CourseRead)
def update_course(
    course_id: uuid.UUID, payload: CourseUpdate, db: Session = DB, user: User = CurrentUser
) -> Course:
    return service.update_course(db, user.id, course_id, payload)


@router.delete("/courses/{course_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_course(
    course_id: uuid.UUID,
    db: Session = DB,
    user: User = CurrentUser,
    storage: DocumentStorage = Depends(get_document_storage),
) -> None:
    delete_course_files(storage, service.delete_course(db, user.id, course_id))


# --- Chapters ---


@router.post(
    "/courses/{course_id}/chapters",
    response_model=ChapterRead,
    status_code=status.HTTP_201_CREATED,
)
def create_chapter(
    course_id: uuid.UUID, payload: ChapterCreate, db: Session = DB, user: User = CurrentUser
) -> Chapter:
    return service.create_chapter(db, user.id, course_id, payload)


@router.patch("/chapters/{chapter_id}", response_model=ChapterRead)
def update_chapter(
    chapter_id: uuid.UUID, payload: ChapterUpdate, db: Session = DB, user: User = CurrentUser
) -> Chapter:
    return service.update_chapter(db, user.id, chapter_id, payload)


@router.put("/courses/{course_id}/chapter-order", status_code=status.HTTP_204_NO_CONTENT)
def reorder_chapters(
    course_id: uuid.UUID, payload: OrderUpdate, db: Session = DB, user: User = CurrentUser
) -> None:
    service.reorder_chapters(db, user.id, course_id, payload.ids)


@router.delete("/chapters/{chapter_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_chapter(chapter_id: uuid.UUID, db: Session = DB, user: User = CurrentUser) -> None:
    service.delete_chapter(db, user.id, chapter_id)


# --- Topics ---


@router.post(
    "/chapters/{chapter_id}/topics",
    response_model=TopicRead,
    status_code=status.HTTP_201_CREATED,
)
def create_topic(
    chapter_id: uuid.UUID, payload: TopicCreate, db: Session = DB, user: User = CurrentUser
) -> Topic:
    return service.create_topic(db, user.id, chapter_id, payload)


@router.put("/chapters/{chapter_id}/topic-order", status_code=status.HTTP_204_NO_CONTENT)
def reorder_topics(
    chapter_id: uuid.UUID, payload: OrderUpdate, db: Session = DB, user: User = CurrentUser
) -> None:
    service.reorder_topics(db, user.id, chapter_id, payload.ids)


@router.patch("/topics/{topic_id}", response_model=TopicRead)
def update_topic(
    topic_id: uuid.UUID, payload: TopicUpdate, db: Session = DB, user: User = CurrentUser
) -> Topic:
    return service.update_topic(db, user.id, topic_id, payload)


@router.delete("/topics/{topic_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_topic(topic_id: uuid.UUID, db: Session = DB, user: User = CurrentUser) -> None:
    service.delete_topic(db, user.id, topic_id)


# --- Concepts ---


@router.post(
    "/topics/{topic_id}/concepts",
    response_model=ConceptRead,
    status_code=status.HTTP_201_CREATED,
)
def create_concept(
    topic_id: uuid.UUID, payload: ConceptCreate, db: Session = DB, user: User = CurrentUser
) -> Concept:
    return service.create_concept(db, user.id, topic_id, payload)


@router.get("/concepts/{concept_id}", response_model=ConceptRead)
def get_concept(concept_id: uuid.UUID, db: Session = DB, user: User = CurrentUser) -> Concept:
    """One Concept, e.g. to follow its Learning Item generation after activation."""
    return service.get_owned_concept(db, user.id, concept_id)


@router.put("/topics/{topic_id}/concept-order", status_code=status.HTTP_204_NO_CONTENT)
def reorder_concepts(
    topic_id: uuid.UUID, payload: OrderUpdate, db: Session = DB, user: User = CurrentUser
) -> None:
    service.reorder_concepts(db, user.id, topic_id, payload.ids)


@router.put("/concepts/{concept_id}/learning-item-order", status_code=status.HTTP_204_NO_CONTENT)
def reorder_learning_items(
    concept_id: uuid.UUID, payload: OrderUpdate, db: Session = DB, user: User = CurrentUser
) -> None:
    service.reorder_learning_items(db, user.id, concept_id, payload.ids)


@router.patch("/concepts/{concept_id}", response_model=ConceptRead)
def update_concept(
    concept_id: uuid.UUID, payload: ConceptUpdate, db: Session = DB, user: User = CurrentUser
) -> Concept:
    return service.update_concept(db, user.id, concept_id, payload)


@router.delete("/concepts/{concept_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_concept(concept_id: uuid.UUID, db: Session = DB, user: User = CurrentUser) -> None:
    service.delete_concept(db, user.id, concept_id)


# --- Concept study state (docs/PROJECT_SPEC.md §21, §22, §60) ---
# Which state each action may start from lives in service.CONCEPT_TRANSITIONS.


@router.post("/concepts/{concept_id}/mark-studied", response_model=ConceptRead)
def mark_concept_studied(
    concept_id: uuid.UUID, db: Session = DB, user: User = CurrentUser
) -> Concept:
    return service.transition_concept(db, user.id, concept_id, "mark_studied")


@router.post("/concepts/{concept_id}/activate", response_model=ConceptRead)
def activate_concept(
    concept_id: uuid.UUID,
    background_tasks: BackgroundTasks,
    db: Session = DB,
    user: User = CurrentUser,
    provider: AIProvider | None = Depends(get_ai_provider),
    session_factory: sessionmaker[Session] = Depends(get_session_factory),
    max_context_chars: int = Depends(get_max_context_chars),
) -> Concept:
    """Activating a Concept with sources and no Learning Items yet also starts generating them
    in the background (`item_generation_status: GENERATING`)."""
    concept = service.transition_concept(db, user.id, concept_id, "activate")
    started_with = learning_service.start_generation_on_activation(db, provider, concept)
    if started_with is not None:
        background_tasks.add_task(
            learning_service.generate_items,
            session_factory,
            started_with,
            concept.id,
            max_context_chars,
        )
    return concept


@router.post("/concepts/{concept_id}/pause", response_model=ConceptRead)
def pause_concept(concept_id: uuid.UUID, db: Session = DB, user: User = CurrentUser) -> Concept:
    return service.transition_concept(db, user.id, concept_id, "pause")


@router.post("/concepts/{concept_id}/resume", response_model=ConceptRead)
def resume_concept(concept_id: uuid.UUID, db: Session = DB, user: User = CurrentUser) -> Concept:
    return service.transition_concept(db, user.id, concept_id, "resume")


@router.post("/concepts/{concept_id}/deactivate", response_model=ConceptRead)
def deactivate_concept(
    concept_id: uuid.UUID, db: Session = DB, user: User = CurrentUser
) -> Concept:
    return service.transition_concept(db, user.id, concept_id, "deactivate")


@router.post("/concepts/{concept_id}/complete", response_model=ConceptRead)
def complete_concept(concept_id: uuid.UUID, db: Session = DB, user: User = CurrentUser) -> Concept:
    return service.transition_concept(db, user.id, concept_id, "complete")


# --- Pausing whole sections (docs/PROJECT_SPEC.md §56) ---


@router.post("/courses/{course_id}/pause", response_model=CourseRead)
def pause_course(course_id: uuid.UUID, db: Session = DB, user: User = CurrentUser) -> Course:
    return service.set_course_paused(db, user.id, course_id, paused=True)


@router.post("/courses/{course_id}/resume", response_model=CourseRead)
def resume_course(course_id: uuid.UUID, db: Session = DB, user: User = CurrentUser) -> Course:
    return service.set_course_paused(db, user.id, course_id, paused=False)


@router.post("/chapters/{chapter_id}/pause", response_model=ChapterRead)
def pause_chapter(chapter_id: uuid.UUID, db: Session = DB, user: User = CurrentUser) -> Chapter:
    return service.set_chapter_paused(db, user.id, chapter_id, paused=True)


@router.post("/chapters/{chapter_id}/resume", response_model=ChapterRead)
def resume_chapter(chapter_id: uuid.UUID, db: Session = DB, user: User = CurrentUser) -> Chapter:
    return service.set_chapter_paused(db, user.id, chapter_id, paused=False)


@router.post("/topics/{topic_id}/pause", response_model=TopicRead)
def pause_topic(topic_id: uuid.UUID, db: Session = DB, user: User = CurrentUser) -> Topic:
    return service.set_topic_paused(db, user.id, topic_id, paused=True)


@router.post("/topics/{topic_id}/resume", response_model=TopicRead)
def resume_topic(topic_id: uuid.UUID, db: Session = DB, user: User = CurrentUser) -> Topic:
    return service.set_topic_paused(db, user.id, topic_id, paused=False)
