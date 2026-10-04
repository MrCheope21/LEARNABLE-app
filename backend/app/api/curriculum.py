"""AI curriculum proposals and the Course outline (docs/PROJECT_SPEC.md §20, §18)."""

import uuid

from fastapi import APIRouter, BackgroundTasks, Depends, status
from sqlalchemy.orm import Session, sessionmaker

from app.ai.factory import get_ai_provider
from app.ai.provider import AIProvider
from app.auth.dependencies import get_current_user
from app.core.config import get_settings
from app.core.rate_limit import per_user
from app.db.session import get_db, get_session_factory
from app.models.course import Chapter
from app.models.document import DocumentChunk
from app.models.user import User
from app.schemas.curriculum import (
    ChapterOutline,
    CurriculumApply,
    CurriculumGenerate,
    CurriculumProposalRead,
)
from app.schemas.documents import ChunkRead
from app.services.curriculum import service

router = APIRouter(tags=["curriculum"])

CurrentUser = Depends(get_current_user)
DB = Depends(get_db)


def get_max_context_chars() -> int:
    """A dependency so tests can shrink the budget instead of uploading 60,000 characters."""
    return get_settings().ai_max_context_chars


@router.post(
    "/courses/{course_id}/curriculum-proposals",
    response_model=CurriculumProposalRead,
    status_code=status.HTTP_202_ACCEPTED,
    dependencies=[Depends(per_user("generation", 30, 3600))],
)
def generate_curriculum(
    course_id: uuid.UUID,
    background_tasks: BackgroundTasks,
    payload: CurriculumGenerate | None = None,
    db: Session = DB,
    user: User = CurrentUser,
    provider: AIProvider | None = Depends(get_ai_provider),
    session_factory: sessionmaker[Session] = Depends(get_session_factory),
    max_context_chars: int = Depends(get_max_context_chars),
) -> CurriculumProposalRead:
    """Returns immediately (202) with status GENERATING; poll GET /curriculum-proposals/{id}
    until it is READY, INSUFFICIENT_CONTEXT or FAILED. With `chapter_id`, proposes Topics →
    Concepts for that Chapter; by default only material not analyzed yet is sent."""
    job = service.request_proposal(
        db, provider, user.id, course_id, payload or CurriculumGenerate()
    )
    background_tasks.add_task(
        service.generate_proposal,
        session_factory,
        job.provider,
        job.proposal.id,
        job.document_ids,
        max_context_chars,
    )
    return service.to_read(db, job.proposal)


@router.get(
    "/courses/{course_id}/curriculum-proposals", response_model=list[CurriculumProposalRead]
)
def list_proposals(
    course_id: uuid.UUID, db: Session = DB, user: User = CurrentUser
) -> list[CurriculumProposalRead]:
    return [service.to_read(db, p) for p in service.list_proposals(db, user.id, course_id)]


@router.get("/curriculum-proposals/{proposal_id}", response_model=CurriculumProposalRead)
def get_proposal(
    proposal_id: uuid.UUID, db: Session = DB, user: User = CurrentUser
) -> CurriculumProposalRead:
    return service.to_read(db, service.get_owned_proposal(db, user.id, proposal_id))


@router.delete("/curriculum-proposals/{proposal_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_proposal(proposal_id: uuid.UUID, db: Session = DB, user: User = CurrentUser) -> None:
    service.delete_proposal(db, user.id, proposal_id)


@router.post(
    "/curriculum-proposals/{proposal_id}/apply",
    response_model=list[ChapterOutline],
    status_code=status.HTTP_201_CREATED,
)
def apply_proposal(
    proposal_id: uuid.UUID, payload: CurriculumApply, db: Session = DB, user: User = CurrentUser
) -> list[Chapter]:
    """Creates the reviewed curriculum and returns the Course's full outline."""
    return service.apply_proposal(db, user.id, proposal_id, payload)


@router.get("/courses/{course_id}/outline", response_model=list[ChapterOutline])
def get_outline(course_id: uuid.UUID, db: Session = DB, user: User = CurrentUser) -> list[Chapter]:
    return service.get_outline(db, user.id, course_id)


@router.get("/concepts/{concept_id}/sources", response_model=list[ChunkRead])
def list_concept_sources(
    concept_id: uuid.UUID, db: Session = DB, user: User = CurrentUser
) -> list[DocumentChunk]:
    return service.list_concept_sources(db, user.id, concept_id)
