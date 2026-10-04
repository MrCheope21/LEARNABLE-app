"""Review sessions: the learning loop (docs/PROJECT_SPEC.md §42, §49-51, §83-86).

    answer → Evaluation (AI evidence, kept as written) → ReviewOutcomeResolver (deterministic)
    → resolved outcome → [user override] → final outcome → SchedulingPolicy → Review row

Session intent decides what an answer may change:
- LEARN: encodes NEW items. Success initializes the schedule; AGAIN leaves the item NEW and
  asks it again later in the same session (up to MAX_LEARN_ATTEMPTS).
- SCHEDULED_REVIEW: due items; every final outcome goes through the SchedulingPolicy.
- PRACTICE: deliberate practice; answers are evaluated and kept but never touch memory state,
  unless the session was created with `update_schedule`.
- EXAM: not available yet (Phase 15); it must never affect the schedule by accident.

- CONSOLIDATION: "I have studied this concept". Each selected NEW item is asked three times in
  a row (three rounds, feedback after each); only the last round moves the schedule, once, as
  an encoding (docs/SCHEDULING.md §4a).

When an evaluation can't decide (AI failed or not configured, insufficient context, uncertain),
the answer is kept with no outcome and the item stays current: the user retries the evaluation,
grades it themselves, or skips it. An answer is never lost (spec §79).

The first final outcome of an answer also records its XP and the day's activity
(app/services/rewards), in the same transaction.
"""

import logging
import uuid
from dataclasses import replace

from sqlalchemy import func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.ai.provider import AIProvider
from app.ai.schemas import (
    DrawingEvaluationRequest,
    DrawingImage,
    EvaluationOutput,
    EvaluationRequest,
    SourcePassage,
)
from app.core.errors import AppError, ConflictError, InvalidRequestError, NotFoundError
from app.db.types import utc_now
from app.models.course import Chapter, Concept, Course, Topic
from app.models.document import Document, DocumentChunk
from app.models.enums import (
    EvaluationClassification,
    EvaluationStatus,
    MemoryState,
    ReviewOutcome,
    SessionIntent,
)
from app.models.learning import LearningItem, LearningItemSource, QuestionFormulation
from app.models.review import Answer, Evaluation, Review, ReviewSession
from app.models.rewards import HintReveal
from app.models.user import User
from app.schemas.curriculum import ProposalSource
from app.schemas.review import (
    AnswerCreate,
    AnswerDetail,
    AnswerResult,
    Card,
    CardQuestion,
    DisputeCreate,
    EvaluationRead,
    HintState,
    Introduction,
    OverrideCreate,
    PotentialXp,
    Reference,
    ScheduleChange,
    SessionCard,
    SessionCreate,
    SessionRead,
    XpResult,
)
from app.services import drawings
from app.services.courses.service import get_owned_course
from app.services.evaluation.resolver import RESOLVER_VERSION, resolve_outcome
from app.services.review import pool
from app.services.rewards import service as rewards
from app.services.rewards.hints import build_hint
from app.services.scheduling.policy import SchedulingError, Transition
from app.services.scheduling.store import (
    policy_for,
    snapshot_from_json,
    snapshot_of,
    snapshot_to_json,
    store,
)
from app.storage.documents import DocumentStorage, StoredFileMissingError

logger = logging.getLogger(__name__)

# A NEW item answered AGAIN in a LEARN session is asked again at the end, at most this often.
MAX_LEARN_ATTEMPTS = 3
# Source text sent with one evaluation.
EVALUATION_CONTEXT_CHARS = 12_000

_NOT_CONFIGURED = "AI evaluation isn't configured on this server. Grade this answer yourself."
_UNEXPECTED_FAILURE = "The answer couldn't be evaluated. Try again, or grade it yourself."


# --- Sessions ---


def create_session(
    db: Session, user_id: uuid.UUID, course_id: uuid.UUID, payload: SessionCreate
) -> ReviewSession:
    get_owned_course(db, user_id, course_id)
    if payload.intent is SessionIntent.CONSOLIDATION:
        raise InvalidRequestError(
            "Start consolidation from its Concept: POST /concepts/{id}/consolidation.",
            details={"reason": "use_concept_consolidation"},
        )
    mode = pool.resolve_mode(payload.intent, payload.selection_mode)
    if payload.update_schedule and payload.intent is not SessionIntent.PRACTICE:
        raise InvalidRequestError(
            "update_schedule applies to PRACTICE sessions only.",
            details={"reason": "update_schedule_not_allowed"},
        )
    _check_scope(db, course_id, payload)
    now = utc_now()
    item_ids = pool.select_pool(
        db,
        course_id,
        payload.intent,
        mode,
        chapter_id=payload.chapter_id,
        topic_id=payload.topic_id,
        concept_ids=payload.concept_ids,
        item_ids=payload.learning_item_ids,
        limit=payload.limit,
        now=now,
    )
    if not item_ids:
        raise ConflictError(
            "There is nothing to study in this selection right now.",
            details={"reason": "empty_pool"},
        )
    session = ReviewSession(
        user_id=user_id,
        course_id=course_id,
        intent=payload.intent,
        selection_mode=mode,
        affects_schedule=payload.intent in (SessionIntent.LEARN, SessionIntent.SCHEDULED_REVIEW)
        or payload.update_schedule,
        chapter_id=payload.chapter_id,
        topic_id=payload.topic_id,
        concept_ids=[str(c) for c in payload.concept_ids] if payload.concept_ids else None,
        item_ids=[str(i) for i in item_ids],
        started_at=now,
    )
    db.add(session)
    db.commit()
    db.refresh(session)
    return session


def _check_scope(db: Session, course_id: uuid.UUID, payload: SessionCreate) -> None:
    """Scope ids must be this Course's: anything else is a 404, identical to a missing id."""
    if payload.chapter_id is not None:
        chapter = db.get(Chapter, payload.chapter_id)
        if chapter is None or chapter.course_id != course_id:
            raise NotFoundError("Chapter not found")
    if payload.topic_id is not None:
        topic = db.get(Topic, payload.topic_id)
        if topic is None or topic.course_id != course_id:
            raise NotFoundError("Topic not found")
    if payload.concept_ids:
        found = set(
            db.scalars(
                select(Concept.id).where(
                    Concept.course_id == course_id, Concept.id.in_(payload.concept_ids)
                )
            )
        )
        if found != set(payload.concept_ids):
            raise NotFoundError("Concept not found")


def get_owned_session(db: Session, user_id: uuid.UUID, session_id: uuid.UUID) -> ReviewSession:
    session = db.get(ReviewSession, session_id)
    if session is None or session.user_id != user_id:
        raise NotFoundError("Review session not found")
    get_owned_course(db, user_id, session.course_id)
    return session


def session_read(db: Session, session: ReviewSession) -> SessionRead:
    return SessionRead(
        id=session.id,
        course_id=session.course_id,
        intent=session.intent,
        selection_mode=session.selection_mode,
        affects_schedule=session.affects_schedule,
        chapter_id=session.chapter_id,
        topic_id=session.topic_id,
        concept_ids=[uuid.UUID(c) for c in session.concept_ids] if session.concept_ids else None,
        total=len(session.item_ids),
        position=session.position,
        xp_earned=rewards.session_xp(db, session.id),
        started_at=session.started_at,
        ended_at=session.ended_at,
    )


def next_card(db: Session, user_id: uuid.UUID, session_id: uuid.UUID) -> SessionCard:
    session = get_owned_session(db, user_id, session_id)
    item = current_item(db, session)
    if item is None:
        db.commit()  # position/ended_at may have moved past items that are gone
        return SessionCard(session=session_read(db, session), done=True, card=None)
    question = _pick_question(item)
    pending = _pending_answer(db, session, item)
    concept = db.get(Concept, item.concept_id)
    introduction = None
    if session.intent is SessionIntent.LEARN:
        introduction = Introduction(
            title=item.title,
            objective=item.objective,
            expected_knowledge=item.expected_knowledge,
            essential_points=list(item.essential_points),
            sources=_item_sources(db, item),
            drawing=item.answer_format == "DRAWING",
        )
    round_number, rounds_total = _round(session, item)
    potential = rewards.potential(db, session, item, utc_now())
    hint = _hint_state(db, session, item, question)
    db.commit()
    return SessionCard(
        session=session_read(db, session),
        done=False,
        card=Card(
            learning_item_id=item.id,
            answer_format=item.answer_format,
            concept_id=item.concept_id,
            concept_title=concept.title if concept else "",
            question=CardQuestion(
                id=question.id, question_type=question.question_type, text=question.text
            ),
            introduction=introduction,
            pending_answer_id=pending.id if pending else None,
            round=round_number,
            rounds_total=rounds_total,
            potential_xp=PotentialXp(
                eligible=potential.eligible,
                ordinal=potential.ordinal,
                xp=potential.xp,
                xp_with_hint=potential.xp_with_hint,
            ),
            hint=hint,
        ),
    )


def _round(session: ReviewSession, item: LearningItem) -> tuple[int | None, int | None]:
    """CONSOLIDATION: which of the item's consecutive slots is current ("Round 2 of 3")."""
    if session.intent is not SessionIntent.CONSOLIDATION:
        return None, None
    key = str(item.id)
    done = session.item_ids[: session.position + 1].count(key)
    return done, session.item_ids.count(key)


def _hint_state(
    db: Session, session: ReviewSession, item: LearningItem, question: QuestionFormulation
) -> HintState:
    revealed = rewards.hint_for_slot(db, session.id, session.position)
    if revealed is not None:
        return HintState(available=True, revealed=True, text=revealed.text)
    available = session.intent is not SessionIntent.LEARN and bool(
        question.hint or build_hint(list(item.essential_points), item.expected_knowledge)
    )
    return HintState(available=available, revealed=False, text=None)


def reveal_hint(db: Session, user_id: uuid.UUID, session_id: uuid.UUID) -> HintState:
    """Shows the hint for the current question slot. Stored before it's returned, so the answer
    to this slot is hint-assisted whatever the client does next; asking again returns the same
    hint. Nothing is recorded when there's no hint to show."""
    session = get_owned_session(db, user_id, session_id)
    item = current_item(db, session)
    if item is None:
        db.commit()
        raise ConflictError("This session is finished.", details={"reason": "session_finished"})
    existing = rewards.hint_for_slot(db, session.id, session.position)
    if existing is not None:
        return HintState(available=True, revealed=True, text=existing.text)
    if _pending_answer(db, session, item) is not None:
        raise ConflictError(
            "This question has already been answered.", details={"reason": "answer_pending"}
        )
    if session.intent is SessionIntent.LEARN:
        # The reference answer is on screen before recall in LEARN: a hint means nothing there.
        raise ConflictError(
            "Hints aren't used when learning with the answer shown.",
            details={"reason": "hint_unavailable"},
        )
    question = _pick_question(item)
    text = question.hint or build_hint(list(item.essential_points), item.expected_knowledge)
    if not text:
        raise ConflictError(
            "There's no hint for this question.", details={"reason": "hint_unavailable"}
        )
    question.hint = text
    db.add(
        HintReveal(
            user_id=user_id,
            course_id=session.course_id,
            session_id=session.id,
            slot=session.position,
            learning_item_id=item.id,
            question_formulation_id=question.id,
            text=text,
        )
    )
    try:
        db.commit()
    except IntegrityError:
        # A concurrent reveal of the same slot won: show that one.
        db.rollback()
        existing = rewards.hint_for_slot(db, session.id, session.position)
        if existing is None:
            raise
        return HintState(available=True, revealed=True, text=existing.text)
    return HintState(available=True, revealed=True, text=text)


def current_item(db: Session, session: ReviewSession) -> LearningItem | None:
    """The item at `position`, skipping items that can no longer be asked in this session
    (deleted, taken out of training, paused, or already encoded when learning)."""
    if session.ended_at is not None:
        return None
    while session.position < len(session.item_ids):
        item = db.get(LearningItem, uuid.UUID(session.item_ids[session.position]))
        if item is not None and _still_askable(session, item):
            return item
        session.position += 1
    session.ended_at = utc_now()
    return None


def _still_askable(session: ReviewSession, item: LearningItem) -> bool:
    if item.course_id != session.course_id or not item.in_training or item.paused:
        return False
    if not item.questions:
        return False
    is_new = item.review_state.state is MemoryState.NEW
    if session.intent in (SessionIntent.LEARN, SessionIntent.CONSOLIDATION):
        return is_new
    return not is_new


def _pick_question(item: LearningItem) -> QuestionFormulation:
    """Rotate wording (spec §27, §58): the least asked, then least recently asked, formulation.
    All of them share the item's one memory state."""
    return min(
        item.questions,
        key=lambda q: (
            q.times_asked,
            q.last_asked_at.timestamp() if q.last_asked_at else 0.0,
            q.created_at.timestamp(),
        ),
    )


def _pending_answer(db: Session, session: ReviewSession, item: LearningItem) -> Answer | None:
    """This session's answer to the current item that still has no outcome."""
    return db.scalar(
        select(Answer)
        .where(
            Answer.session_id == session.id,
            Answer.learning_item_id == item.id,
            Answer.final_outcome.is_(None),
            Answer.created_at >= session.started_at,
        )
        .order_by(Answer.created_at.desc())
        .limit(1)
    )


def skip(db: Session, user_id: uuid.UUID, session_id: uuid.UUID) -> SessionCard:
    """Moves past the current item without an outcome; its memory state is untouched."""
    session = get_owned_session(db, user_id, session_id)
    if current_item(db, session) is not None:
        session.position += 1
    db.commit()
    return next_card(db, user_id, session_id)


def end_session(db: Session, user_id: uuid.UUID, session_id: uuid.UUID) -> SessionRead:
    session = get_owned_session(db, user_id, session_id)
    if session.ended_at is None:
        session.ended_at = utc_now()
    db.commit()
    return session_read(db, session)


# --- Answers ---


def submit_answer(
    db: Session,
    provider: AIProvider | None,
    storage: DocumentStorage,
    user_id: uuid.UUID,
    session_id: uuid.UUID,
    payload: AnswerCreate,
) -> AnswerResult:
    session = get_owned_session(db, user_id, session_id)
    item = current_item(db, session)
    if item is None:
        db.commit()
        raise ConflictError("This session is finished.", details={"reason": "session_finished"})
    question = next((q for q in item.questions if q.id == payload.question_formulation_id), None)
    if question is None:
        raise ConflictError(
            "That question isn't the current one in this session.",
            details={"reason": "not_current_question"},
        )
    pending = _pending_answer(db, session, item)
    if pending is not None:
        raise ConflictError(
            "The previous answer to this question still needs an outcome.",
            details={"reason": "answer_pending", "answer_id": str(pending.id)},
        )

    drawing = _drawn_answer(item, payload)
    now = utc_now()
    round_number, _ = _round(session, item)
    answer = Answer(
        id=uuid.uuid4(),
        user_id=user_id,
        course_id=session.course_id,
        session_id=session.id,
        learning_item_id=item.id,
        question_formulation_id=question.id,
        intent=session.intent,
        method=payload.method,
        text=payload.text,
        created_at=now,
        consolidation_round=round_number,
        # Decided by the server from the stored reveal, never by the client.
        hint_used=rewards.hint_for_slot(db, session.id, session.position) is not None,
        drawing_type=drawing[1] if drawing else None,
    )
    if drawing:
        # Stored before the row is committed: an answer never points at a missing drawing.
        storage.save(drawings.answer_key(answer), drawing[0])
    question.times_asked += 1
    question.last_asked_at = now
    db.add(answer)
    # Committed before the AI call: the answer is safe whatever happens next, and no
    # transaction is held open while the model thinks.
    db.commit()

    transition = _evaluate_and_apply(db, provider, storage, session, item, answer, question)
    _commit_finalization(db)
    return _result(db, answer, session, item, transition)


def _drawn_answer(item: LearningItem, payload: AnswerCreate) -> tuple[bytes, str] | None:
    """The drawing of a drawing question; nothing for a text question, which needs words."""
    if item.answer_format == "DRAWING":
        if not payload.drawing:
            raise InvalidRequestError("This question is answered by drawing: send the drawing.")
        return drawings.decode_data_url(payload.drawing)
    if payload.drawing is not None:
        raise InvalidRequestError("This question is answered in words, not by drawing.")
    if not payload.text.strip():
        raise InvalidRequestError("Write an answer first.")
    return None


def _commit_finalization(db: Session) -> None:
    """Commits an answer's outcome, schedule change and award together. A concurrent duplicate
    (e.g. the same evaluation retried twice at once) loses on the database's unique constraints
    and is rolled back whole: the caller then reports the state the winner stored."""
    try:
        db.commit()
    except IntegrityError:
        db.rollback()
        logger.info("finalization_conflict: a concurrent request already finalized this answer")


def retry_evaluation(
    db: Session,
    provider: AIProvider | None,
    storage: DocumentStorage,
    user_id: uuid.UUID,
    answer_id: uuid.UUID,
) -> AnswerResult:
    answer, session, item = _owned_answer(db, user_id, answer_id)
    if answer.final_outcome is not None:
        raise ConflictError(
            "This answer already has an outcome.", details={"reason": "already_graded"}
        )
    latest = _latest_evaluation(db, answer)
    if latest is not None and latest.status is EvaluationStatus.COMPLETED:
        raise ConflictError(
            "This answer was evaluated but the result was inconclusive: grade it yourself.",
            details={"reason": "evaluation_inconclusive"},
        )
    transition = _evaluate_and_apply(
        db, provider, storage, session, item, answer, _question_of(db, answer)
    )
    _commit_finalization(db)
    return _result(db, answer, session, item, transition)


MAX_SECOND_OPINIONS = 3


def dispute(
    db: Session,
    provider: AIProvider | None,
    storage: DocumentStorage,
    user_id: uuid.UUID,
    answer_id: uuid.UUID,
    payload: DisputeCreate,
) -> AnswerResult:
    """Asks the evaluator again with the student's objection. The result is stored and shown
    beside the first evaluation; it never changes the outcome, the schedule or XP: if the
    student agrees with it, they grade the answer themselves (override)."""
    answer, session, item = _owned_answer(db, user_id, answer_id)
    first = _latest_evaluation(db, answer)
    if first is None or first.status is not EvaluationStatus.COMPLETED:
        raise ConflictError(
            "There is no completed evaluation to dispute yet.",
            details={"reason": "nothing_to_dispute"},
        )
    asked = db.scalar(
        select(func.count())
        .select_from(Evaluation)
        .where(Evaluation.answer_id == answer.id, Evaluation.user_argument.is_not(None))
    )
    if (asked or 0) >= MAX_SECOND_OPINIONS:
        raise ConflictError(
            "This answer already had the maximum number of second opinions.",
            details={"reason": "dispute_limit"},
        )
    question = _question_of(db, answer)
    db.add(
        _evaluate(db, provider, storage, item, answer, question, argument=payload.argument.strip())
    )
    db.commit()
    return _result(db, answer, session, item, None)


def override(
    db: Session, user_id: uuid.UUID, answer_id: uuid.UUID, payload: OverrideCreate
) -> AnswerResult:
    """The user's own grade (task §5.6). The AI evaluation and the resolved outcome are kept as
    they were. If the answer already moved the schedule, the transition is replayed from the
    stored previous state with the new outcome, as a new history row superseding the old one;
    allowed only while it is the item's latest review, so later history is never rewritten."""
    answer, session, item = _owned_answer(db, user_id, answer_id)
    if answer.final_outcome == payload.outcome:
        return _result(db, answer, session, item, None)

    transition: Transition | None = None
    if answer.final_outcome is None:
        _set_override(answer, payload)
        # The user's grade completes the attempt, but it can't create correctness XP.
        transition = _apply_outcome(db, session, item, answer, payload.outcome, classification=None)
    else:
        applied = db.scalar(
            select(Review).where(Review.answer_id == answer.id, Review.superseded.is_(False))
        )
        if applied is not None:
            latest = db.scalar(
                select(Review)
                .where(Review.learning_item_id == item.id, Review.superseded.is_(False))
                .order_by(Review.created_at.desc())
                .limit(1)
            )
            if latest is None or latest.id != applied.id:
                raise ConflictError(
                    "This item has been reviewed again since; that answer can't be regraded.",
                    details={"reason": "later_reviews_exist"},
                )
            transition = _replay(db, item, answer, applied, payload.outcome)
        # A regrade after the fact changes the schedule, never the XP already decided.
        _set_override(answer, payload)
    _commit_finalization(db)
    return _result(db, answer, session, item, transition)


def _set_override(answer: Answer, payload: OverrideCreate) -> None:
    answer.override_outcome = payload.outcome
    answer.override_note = payload.note
    answer.overridden_at = utc_now()
    answer.final_outcome = payload.outcome


def _evaluate_and_apply(
    db: Session,
    provider: AIProvider | None,
    storage: DocumentStorage,
    session: ReviewSession,
    item: LearningItem,
    answer: Answer,
    question: QuestionFormulation,
) -> Transition | None:
    evaluation = _evaluate(db, provider, storage, item, answer, question)
    db.add(evaluation)
    if evaluation.status is not EvaluationStatus.COMPLETED:
        return None
    outcome = resolve_outcome(_evidence(evaluation))
    answer.resolved_outcome = outcome
    answer.resolver_version = RESOLVER_VERSION
    if outcome is None:
        return None  # inconclusive: the user grades it
    answer.final_outcome = outcome
    return _apply_outcome(
        db, session, item, answer, outcome, classification=evaluation.classification
    )


def _evaluate(
    db: Session,
    provider: AIProvider | None,
    storage: DocumentStorage,
    item: LearningItem,
    answer: Answer,
    question: QuestionFormulation,
    argument: str | None = None,
) -> Evaluation:
    base = Evaluation(answer_id=answer.id, course_id=answer.course_id, user_argument=argument)
    if provider is None:
        base.status = EvaluationStatus.NOT_CONFIGURED
        base.error_message = _NOT_CONFIGURED
        return base
    course = db.get(Course, item.course_id)
    language = course.language if course else "en"
    try:
        if answer.drawing_type is not None:
            result = provider.evaluate_drawing(
                _drawing_request(storage, item, answer, question, language, argument)
            )
        else:
            result = provider.evaluate_answer(
                EvaluationRequest(
                    language=language,
                    question=question.text,
                    objective=item.objective,
                    expected_knowledge=item.expected_knowledge,
                    essential_points=list(item.essential_points),
                    passages=_item_passages(db, item),
                    answer=answer.text,
                    user_argument=argument,
                )
            )
    except AppError as exc:
        base.status = EvaluationStatus.FAILED
        base.error_message = exc.message[:500]
        return base
    except Exception:
        logger.exception("Unexpected failure evaluating answer %s", answer.id)
        base.status = EvaluationStatus.FAILED
        base.error_message = _UNEXPECTED_FAILURE
        return base
    out, info = result.output, result.info
    base.status = EvaluationStatus.COMPLETED
    base.classification = out.classification
    base.correctness = out.correctness
    base.completeness = out.completeness
    base.conceptual_understanding = out.conceptual_understanding
    base.precision = out.precision
    base.confidence = out.confidence
    base.correct_points = list(out.correct_points)
    base.missing_points = list(out.missing_points)
    base.misconceptions = list(out.misconceptions)
    base.source_corrections = list(out.source_corrections)
    base.context_sufficient = out.context_sufficient
    base.feedback = out.feedback
    base.ai_provider = info.provider[:50]
    base.ai_model = info.model[:200]
    base.ai_model_version = info.model_version[:200]
    base.prompt_version = info.prompt_version[:100]
    return base


def _drawing_request(
    storage: DocumentStorage,
    item: LearningItem,
    answer: Answer,
    question: QuestionFormulation,
    language: str,
    argument: str | None,
) -> DrawingEvaluationRequest:
    if item.reference_drawing_type is None or answer.drawing_type is None:
        raise InvalidRequestError("This question has no reference drawing to compare with.")
    try:
        reference = storage.load(drawings.reference_key(item))
        drawing = storage.load(drawings.answer_key(answer))
    except StoredFileMissingError as exc:
        raise InvalidRequestError("A drawing file is missing.") from exc
    return DrawingEvaluationRequest(
        language=language,
        question=question.text,
        objective=item.objective,
        expected_knowledge=item.expected_knowledge,
        reference=DrawingImage(reference, item.reference_drawing_type),
        drawing=DrawingImage(drawing, answer.drawing_type),
        note=answer.text,
        user_argument=argument,
    )


def _evidence(evaluation: Evaluation) -> EvaluationOutput:
    """The stored evaluation, as the resolver's input."""
    if evaluation.classification is None:
        raise ValueError("only a completed evaluation can be resolved")
    return EvaluationOutput(
        classification=evaluation.classification,
        correctness=evaluation.correctness or 0.0,
        completeness=evaluation.completeness or 0.0,
        conceptual_understanding=evaluation.conceptual_understanding or 0.0,
        precision=evaluation.precision or 0.0,
        confidence=evaluation.confidence or 0.0,
        context_sufficient=bool(evaluation.context_sufficient),
    )


def _apply_outcome(
    db: Session,
    session: ReviewSession,
    item: LearningItem,
    answer: Answer,
    outcome: ReviewOutcome,
    *,
    classification: EvaluationClassification | None,
) -> Transition | None:
    """Final outcome known for the first time: the attempt is complete. Schedule (if this
    session may), record XP and activity, and move the session on. `classification` is the AI
    evaluation's; None when the user graded it themselves (no correctness XP then)."""
    now = utc_now()
    answer.finalized_at = now
    state_before, due_before = item.review_state.state, item.review_state.due_at
    transition = None
    if session.affects_schedule and _moves_schedule(session, item):
        transition = _schedule(db, item, answer, outcome, session.intent)
    user = db.get(User, session.user_id)
    if user is not None:
        occasion = rewards.occasion_for(
            db, session, item, state_before=state_before, due_before=due_before, at=now
        )
        if session.intent is SessionIntent.SCHEDULED_REVIEW and transition is None:
            occasion = None  # the policy refused the review: nothing was reviewed
        rewards.record_attempt(
            db,
            user,
            session,
            item,
            answer,
            occasion=occasion,
            classification=classification,
            at=now,
        )
    current = current_item(db, session)
    if current is not None and current.id == item.id:
        if (
            session.intent is SessionIntent.LEARN
            and item.review_state.state is MemoryState.NEW
            and session.item_ids.count(str(item.id)) < MAX_LEARN_ATTEMPTS
        ):
            # Not encoded yet: ask again after the rest (initial retrieval until it sticks).
            session.item_ids = [*session.item_ids, str(item.id)]
        session.position += 1
        if session.position >= len(session.item_ids):
            session.ended_at = utc_now()
    return transition


def _moves_schedule(session: ReviewSession, item: LearningItem) -> bool:
    """CONSOLIDATION: three answers seconds apart are one act of encoding, not three reviews.
    Only the item's last round goes through the policy (process_learning with that round's
    outcome), so the item starts at level 1 (4 hours) at most, like any first success; failing
    the last round leaves it NEW for the next batch. Earlier rounds are kept as answers."""
    if session.intent is not SessionIntent.CONSOLIDATION:
        return True
    return str(item.id) not in session.item_ids[session.position + 1 :]


def _schedule(
    db: Session,
    item: LearningItem,
    answer: Answer,
    outcome: ReviewOutcome,
    intent: SessionIntent,
) -> Transition | None:
    state = item.review_state
    policy = policy_for(state)
    before = snapshot_of(state)
    reviewed_at = utc_now()
    try:
        if before.state is MemoryState.NEW:
            transition = policy.process_learning(before, outcome, reviewed_at)
        else:
            transition = policy.process_review(before, outcome, reviewed_at)
    except SchedulingError:
        logger.warning("scheduling_refused item=%s intent=%s", item.id, intent)
        return None
    store(state, transition.after)
    _history(db, item, answer, intent, transition, policy.name, policy.version, None)
    return transition


def _replay(
    db: Session, item: LearningItem, answer: Answer, applied: Review, outcome: ReviewOutcome
) -> Transition | None:
    """Re-runs the original transition with the user's outcome, from the stored state and at
    the original review time."""
    state = item.review_state
    policy = policy_for(state)
    before = snapshot_from_json(applied.previous_snapshot)
    try:
        if before.state is MemoryState.NEW:
            transition = policy.process_learning(before, outcome, applied.reviewed_at)
        else:
            transition = policy.process_review(before, outcome, applied.reviewed_at)
    except SchedulingError:
        return None
    # A pause that happened since the answer is kept.
    after = transition.after
    if state.paused_at is not None and after.paused_at is None:
        after = replace(after, paused_at=state.paused_at)
    store(state, after)
    applied.superseded = True
    _history(db, item, answer, applied.intent, transition, policy.name, policy.version, applied)
    return transition


def _history(
    db: Session,
    item: LearningItem,
    answer: Answer,
    intent: SessionIntent,
    t: Transition,
    policy_name: str,
    policy_version: str,
    supersedes: Review | None,
) -> None:
    db.add(
        Review(
            course_id=item.course_id,
            learning_item_id=item.id,
            answer_id=answer.id,
            intent=intent,
            outcome=t.outcome,
            previous_state=t.before.state,
            previous_level=t.before.level,
            previous_due_at=t.before.due_at,
            next_state=t.after.state,
            next_level=t.after.level,
            next_due_at=t.after.due_at,
            reviewed_at=t.reviewed_at,
            lateness_seconds=int(t.lateness.total_seconds()),
            scheduling_policy=policy_name,
            scheduling_policy_version=policy_version,
            previous_snapshot=snapshot_to_json(t.before),
            supersedes_review_id=supersedes.id if supersedes else None,
        )
    )


# --- Reading answers and history ---


def _owned_answer(
    db: Session, user_id: uuid.UUID, answer_id: uuid.UUID
) -> tuple[Answer, ReviewSession, LearningItem]:
    answer = db.get(Answer, answer_id)
    if answer is None or answer.user_id != user_id:
        raise NotFoundError("Answer not found")
    get_owned_course(db, user_id, answer.course_id)
    session = db.get(ReviewSession, answer.session_id)
    item = db.get(LearningItem, answer.learning_item_id)
    if session is None or item is None:
        raise NotFoundError("Answer not found")
    return answer, session, item


def get_answer(db: Session, user_id: uuid.UUID, answer_id: uuid.UUID) -> AnswerDetail:
    answer, session, item = _owned_answer(db, user_id, answer_id)
    result = _result(db, answer, session, item, None)
    evaluations = db.scalars(
        select(Evaluation).where(Evaluation.answer_id == answer.id).order_by(Evaluation.created_at)
    ).all()
    return AnswerDetail(
        **result.model_dump(),
        evaluations=[EvaluationRead.model_validate(e) for e in evaluations],
        override_note=answer.override_note,
        overridden_at=answer.overridden_at,
        created_at=answer.created_at,
    )


def list_item_reviews(db: Session, user_id: uuid.UUID, item_id: uuid.UUID) -> list[Review]:
    item = db.get(LearningItem, item_id)
    if item is None:
        raise NotFoundError("Learning item not found")
    get_owned_course(db, user_id, item.course_id)
    return list(
        db.scalars(
            select(Review)
            .where(Review.learning_item_id == item.id, Review.course_id == item.course_id)
            .order_by(Review.created_at)
        )
    )


def _latest_evaluation(
    db: Session, answer: Answer, *, second_opinion: bool = False
) -> Evaluation | None:
    """The latest first-line evaluation, or with `second_opinion` the latest one asked for
    after an objection. The two never stand in for each other."""
    marker = Evaluation.user_argument
    return db.scalar(
        select(Evaluation)
        .where(
            Evaluation.answer_id == answer.id,
            marker.is_not(None) if second_opinion else marker.is_(None),
        )
        .order_by(Evaluation.created_at.desc())
        .limit(1)
    )


def _question_of(db: Session, answer: Answer) -> QuestionFormulation:
    question = db.get(QuestionFormulation, answer.question_formulation_id)
    if question is None:
        raise NotFoundError("Question not found")
    return question


def _result(
    db: Session,
    answer: Answer,
    session: ReviewSession,
    item: LearningItem,
    transition: Transition | None,
) -> AnswerResult:
    latest = _latest_evaluation(db, answer)
    second = _latest_evaluation(db, answer, second_opinion=True)
    schedule = None
    if transition is not None:
        schedule = ScheduleChange(
            previous_state=transition.before.state,
            previous_level=transition.before.level,
            previous_due_at=transition.before.due_at,
            next_state=transition.after.state,
            next_level=transition.after.level,
            next_due_at=transition.after.due_at,
            lateness_seconds=int(transition.lateness.total_seconds()),
        )
    return AnswerResult(
        answer_id=answer.id,
        learning_item_id=answer.learning_item_id,
        question_formulation_id=answer.question_formulation_id,
        intent=answer.intent,
        text=answer.text,
        evaluation=EvaluationRead.model_validate(latest) if latest else None,
        second_opinion=EvaluationRead.model_validate(second) if second else None,
        resolved_outcome=answer.resolved_outcome,
        resolver_version=answer.resolver_version,
        override_outcome=answer.override_outcome,
        final_outcome=answer.final_outcome,
        needs_self_grade=answer.final_outcome is None,
        schedule=schedule,
        reference=Reference(
            expected_knowledge=item.expected_knowledge,
            essential_points=list(item.essential_points),
            sources=_item_sources(db, item),
            drawing=item.answer_format == "DRAWING",
        ),
        session=session_read(db, session),
        consolidation_round=answer.consolidation_round,
        hint_used=answer.hint_used,
        xp=_xp_result(db, answer),
        has_drawing=answer.drawing_type is not None,
    )


def _xp_result(db: Session, answer: Answer) -> XpResult | None:
    """The award decided when the answer was finalized; null before that, and for attempts
    that weren't XP-eligible (learning with the answer shown, practice)."""
    award = rewards.award_for(db, answer.id)
    if award is None:
        return None
    return XpResult(
        reason=award.reason,
        correct=award.correct,
        ordinal=award.ordinal,
        base_xp=award.base_xp,
        hint_used=award.hint_used,
        xp=award.xp,
    )


# --- Sources ---


def _item_source_rows(db: Session, item: LearningItem) -> list[tuple[DocumentChunk, str]]:
    return [
        (chunk, filename)
        for chunk, filename in db.execute(
            select(DocumentChunk, Document.filename)
            .join(LearningItemSource, LearningItemSource.chunk_id == DocumentChunk.id)
            .join(Document, Document.id == DocumentChunk.document_id)
            .where(
                LearningItemSource.learning_item_id == item.id,
                LearningItemSource.course_id == item.course_id,
                DocumentChunk.course_id == item.course_id,
            )
            .order_by(LearningItemSource.created_at, DocumentChunk.position)
        ).tuples()
    ]


def _item_sources(db: Session, item: LearningItem) -> list[ProposalSource]:
    return [
        ProposalSource(
            chunk_id=chunk.id,
            document_id=chunk.document_id,
            document_name=filename,
            page_number=chunk.page_number,
            page_end=chunk.page_end,
            section=chunk.section,
        )
        for chunk, filename in _item_source_rows(db, item)
    ]


def _item_passages(db: Session, item: LearningItem) -> list[SourcePassage]:
    """The item's own passages, Course-scoped, within a budget: the evaluation's authority."""
    passages: list[SourcePassage] = []
    used = 0
    for chunk, filename in _item_source_rows(db, item):
        if passages and used + len(chunk.text) > EVALUATION_CONTEXT_CHARS:
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
