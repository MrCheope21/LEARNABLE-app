from typing import Annotated
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field

from app.models.enums import (
    AnswerMethod,
    EvaluationClassification,
    EvaluationStatus,
    MemoryState,
    QuestionType,
    ReviewOutcome,
    SelectionMode,
    SessionIntent,
    XpReason,
)
from app.schemas.common import InputModel, UTCTimestamp
from app.schemas.curriculum import ProposalSource


class SessionCreate(InputModel):
    intent: SessionIntent
    # Defaults per intent: LEARN → NEW, SCHEDULED_REVIEW → DUE, PRACTICE → COURSE_ORDER.
    selection_mode: SelectionMode | None = None
    chapter_id: UUID | None = None
    topic_id: UUID | None = None
    concept_ids: list[UUID] | None = Field(default=None, min_length=1, max_length=200)
    # For selection_mode SELECTED.
    learning_item_ids: list[UUID] | None = Field(default=None, min_length=1, max_length=100)
    limit: int = Field(default=20, ge=1, le=100)
    # PRACTICE only: let answers move the schedule. Off by default: practice never changes
    # memory state unless the user asks for it.
    update_schedule: bool = False


class SessionRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    course_id: UUID
    intent: SessionIntent
    selection_mode: SelectionMode
    affects_schedule: bool
    chapter_id: UUID | None
    topic_id: UUID | None
    concept_ids: list[UUID] | None = None
    total: int
    position: int
    # XP awarded for this session's answers so far.
    xp_earned: int = 0
    started_at: UTCTimestamp
    ended_at: UTCTimestamp | None


class CardQuestion(BaseModel):
    id: UUID
    question_type: QuestionType
    text: str


class Introduction(BaseModel):
    """LEARN only: what to encode, shown before the first retrieval."""

    title: str
    objective: str
    expected_knowledge: str
    essential_points: list[str]
    sources: list[ProposalSource]


class PotentialXp(BaseModel):
    """What a correct answer to this card would earn, decided by the server (never sent back
    by the client). Not eligible: learning with the answer shown, practice, a review of an item
    that isn't due, or an item past its three XP-eligible consolidation rounds."""

    eligible: bool
    # The item's next success ordinal (n in min(10n, 150)).
    ordinal: int
    xp: int
    xp_with_hint: int


class HintState(BaseModel):
    # Whether a hint exists for this question (a cue can be cut from its reference answer).
    available: bool
    # Revealed for this question slot: the answer earns half XP. Stored on the server.
    revealed: bool
    text: str | None


class Card(BaseModel):
    learning_item_id: UUID
    concept_id: UUID
    concept_title: str
    question: CardQuestion
    introduction: Introduction | None
    # An answer to this item that still has no outcome (evaluation failed or undecided):
    # retry its evaluation, grade it yourself, or skip.
    pending_answer_id: UUID | None
    # CONSOLIDATION: "Round {round} of {rounds_total}" for this item; null otherwise.
    round: int | None = None
    rounds_total: int | None = None
    potential_xp: PotentialXp | None = None
    hint: HintState | None = None


class SessionCard(BaseModel):
    session: SessionRead
    done: bool
    card: Card | None


class AnswerCreate(InputModel):
    question_formulation_id: UUID
    text: Annotated[str, Field(min_length=1, max_length=10_000)]
    method: AnswerMethod = AnswerMethod.TEXT


class OverrideCreate(InputModel):
    outcome: ReviewOutcome
    note: Annotated[str, Field(max_length=500)] | None = None


class EvaluationRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    status: EvaluationStatus
    error_message: str | None
    classification: EvaluationClassification | None
    correctness: float | None
    completeness: float | None
    conceptual_understanding: float | None
    precision: float | None
    confidence: float | None
    correct_points: list[str]
    missing_points: list[str]
    misconceptions: list[str]
    source_corrections: list[str]
    context_sufficient: bool | None
    feedback: str
    ai_provider: str | None
    ai_model: str | None
    ai_model_version: str | None
    prompt_version: str | None
    created_at: UTCTimestamp


class ScheduleChange(BaseModel):
    previous_state: MemoryState
    previous_level: int
    previous_due_at: UTCTimestamp | None
    next_state: MemoryState
    next_level: int
    next_due_at: UTCTimestamp | None
    lateness_seconds: int


class Reference(BaseModel):
    """The correct answer and where it comes from, shown with the feedback (spec §41, §66)."""

    expected_knowledge: str
    essential_points: list[str]
    sources: list[ProposalSource]


class XpResult(BaseModel):
    """The XP decision for this answer, made once when it was first finalized."""

    reason: XpReason
    correct: bool
    ordinal: int | None
    base_xp: int
    hint_used: bool
    xp: int


class AnswerResult(BaseModel):
    answer_id: UUID
    learning_item_id: UUID
    question_formulation_id: UUID
    intent: SessionIntent
    text: str
    # The latest evaluation attempt; `evaluations` on GET /answers/{id} has all of them.
    evaluation: EvaluationRead | None
    resolved_outcome: ReviewOutcome | None
    resolver_version: str | None
    override_outcome: ReviewOutcome | None
    final_outcome: ReviewOutcome | None
    # No outcome yet: the user must grade it (POST /answers/{id}/override) or retry evaluation.
    needs_self_grade: bool
    # Null when the answer didn't move the schedule (practice, or no outcome yet).
    schedule: ScheduleChange | None
    reference: Reference
    session: SessionRead
    consolidation_round: int | None = None
    hint_used: bool = False
    # Null when the attempt wasn't XP-eligible, or has no final outcome yet.
    xp: XpResult | None = None


class AnswerDetail(AnswerResult):
    evaluations: list[EvaluationRead]
    override_note: str | None
    overridden_at: UTCTimestamp | None
    created_at: UTCTimestamp


class ReviewRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    learning_item_id: UUID
    answer_id: UUID
    intent: SessionIntent
    outcome: ReviewOutcome
    previous_state: MemoryState
    previous_level: int
    previous_due_at: UTCTimestamp | None
    next_state: MemoryState
    next_level: int
    next_due_at: UTCTimestamp | None
    reviewed_at: UTCTimestamp
    lateness_seconds: int
    scheduling_policy: str
    scheduling_policy_version: str
    supersedes_review_id: UUID | None
    superseded: bool


class ConsolidationPlan(BaseModel):
    """What "I have studied this concept" would start, shown before starting (items, rounds,
    answers), or the unfinished batch it would resume."""

    concept_id: UUID
    concept_active: bool
    # A batch left unfinished: starting again resumes it, never resets its rounds.
    unfinished: SessionRead | None
    unfinished_items: int
    # NEW items waiting outside the unfinished batch.
    new_items: int
    batch_items: int
    rounds_per_item: int
    answers_in_batch: int
    # Left for later batches after the next one.
    remaining_after_batch: int
