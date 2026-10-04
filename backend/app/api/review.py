"""Review sessions, answers, evaluation and history (docs/PROJECT_SPEC.md §42, §49-51, §83-86)."""

import uuid

from fastapi import APIRouter, Depends, status
from sqlalchemy.orm import Session

from app.ai.factory import get_ai_provider
from app.ai.provider import AIProvider
from app.auth.dependencies import get_current_user
from app.core.rate_limit import per_user
from app.db.session import get_db
from app.models.review import Review
from app.models.user import User
from app.schemas.review import (
    AnswerCreate,
    AnswerDetail,
    AnswerResult,
    ConsolidationPlan,
    DisputeCreate,
    HintState,
    OverrideCreate,
    ReviewRead,
    SessionCard,
    SessionCreate,
    SessionRead,
)
from app.services.review import consolidation, service

router = APIRouter(tags=["review"])

CurrentUser = Depends(get_current_user)
DB = Depends(get_db)
Provider = Depends(get_ai_provider)


@router.post(
    "/courses/{course_id}/review-sessions",
    response_model=SessionRead,
    status_code=status.HTTP_201_CREATED,
)
def create_session(
    course_id: uuid.UUID, payload: SessionCreate, db: Session = DB, user: User = CurrentUser
) -> SessionRead:
    """Builds the pool now and stores it (409 `empty_pool` when nothing qualifies)."""
    return service.session_read(db, service.create_session(db, user.id, course_id, payload))


@router.get("/review-sessions/{session_id}", response_model=SessionRead)
def get_session(session_id: uuid.UUID, db: Session = DB, user: User = CurrentUser) -> SessionRead:
    return service.session_read(db, service.get_owned_session(db, user.id, session_id))


@router.get("/concepts/{concept_id}/consolidation", response_model=ConsolidationPlan)
def consolidation_plan(
    concept_id: uuid.UUID, db: Session = DB, user: User = CurrentUser
) -> ConsolidationPlan:
    """What "I have studied this concept" would do: resume an unfinished batch, or start the
    next batch (item count, rounds and answers, shown before starting)."""
    return consolidation.plan(db, user.id, concept_id)


@router.post("/concepts/{concept_id}/consolidation", response_model=SessionRead)
def start_consolidation(
    concept_id: uuid.UUID, db: Session = DB, user: User = CurrentUser
) -> SessionRead:
    """ "I have studied this concept": resumes the unfinished batch, or starts the next one
    (each item asked three times in a row). 409 `nothing_to_consolidate` when no NEW item is
    waiting. Answer it through the usual review-session endpoints."""
    return service.session_read(db, consolidation.start(db, user.id, concept_id))


@router.post("/review-sessions/{session_id}/hint", response_model=HintState)
def reveal_hint(session_id: uuid.UUID, db: Session = DB, user: User = CurrentUser) -> HintState:
    """Reveals the hint for the current question. Stored before it is returned: the answer to
    this question earns half XP, whatever the client does next. 409 `hint_unavailable` when the
    question has no hint (nothing is recorded then)."""
    return service.reveal_hint(db, user.id, session_id)


@router.get("/review-sessions/{session_id}/next", response_model=SessionCard)
def next_card(session_id: uuid.UUID, db: Session = DB, user: User = CurrentUser) -> SessionCard:
    """The current question; the same one until it has an outcome or is skipped."""
    return service.next_card(db, user.id, session_id)


@router.post(
    "/review-sessions/{session_id}/answers",
    response_model=AnswerResult,
    status_code=status.HTTP_201_CREATED,
    dependencies=[Depends(per_user("answers", 600, 3600))],
)
def submit_answer(
    session_id: uuid.UUID,
    payload: AnswerCreate,
    db: Session = DB,
    user: User = CurrentUser,
    provider: AIProvider | None = Provider,
) -> AnswerResult:
    """Stores the answer, evaluates it, resolves the outcome and applies it. Always 201 once
    the answer is stored, even if evaluation failed (`needs_self_grade`)."""
    return service.submit_answer(db, provider, user.id, session_id, payload)


@router.post("/review-sessions/{session_id}/skip", response_model=SessionCard)
def skip(session_id: uuid.UUID, db: Session = DB, user: User = CurrentUser) -> SessionCard:
    return service.skip(db, user.id, session_id)


@router.post("/review-sessions/{session_id}/end", response_model=SessionRead)
def end_session(session_id: uuid.UUID, db: Session = DB, user: User = CurrentUser) -> SessionRead:
    return service.end_session(db, user.id, session_id)


@router.get("/answers/{answer_id}", response_model=AnswerDetail)
def get_answer(answer_id: uuid.UUID, db: Session = DB, user: User = CurrentUser) -> AnswerDetail:
    return service.get_answer(db, user.id, answer_id)


@router.post(
    "/answers/{answer_id}/evaluate",
    response_model=AnswerResult,
    dependencies=[Depends(per_user("evaluate", 60, 3600))],
)
def retry_evaluation(
    answer_id: uuid.UUID,
    db: Session = DB,
    user: User = CurrentUser,
    provider: AIProvider | None = Provider,
) -> AnswerResult:
    """Evaluates again after a failed (or unconfigured) attempt."""
    return service.retry_evaluation(db, provider, user.id, answer_id)


@router.post(
    "/answers/{answer_id}/dispute",
    response_model=AnswerResult,
    dependencies=[Depends(per_user("dispute", 30, 3600))],
)
def dispute(
    answer_id: uuid.UUID,
    payload: DisputeCreate,
    db: Session = DB,
    user: User = CurrentUser,
    provider: AIProvider | None = Provider,
) -> AnswerResult:
    """A second opinion: the evaluator sees the student's objection. Changes no grade."""
    return service.dispute(db, provider, user.id, answer_id, payload)


@router.post("/answers/{answer_id}/override", response_model=AnswerResult)
def override(
    answer_id: uuid.UUID, payload: OverrideCreate, db: Session = DB, user: User = CurrentUser
) -> AnswerResult:
    """The user's own grade. Keeps the AI evaluation; see docs/API.md for replay rules."""
    return service.override(db, user.id, answer_id, payload)


@router.get("/learning-items/{item_id}/reviews", response_model=list[ReviewRead])
def list_reviews(item_id: uuid.UUID, db: Session = DB, user: User = CurrentUser) -> list[Review]:
    return service.list_item_reviews(db, user.id, item_id)
