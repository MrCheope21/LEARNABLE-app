from typing import Annotated, Literal
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field

from app.models.enums import LearningItemRole, MemoryState, QuestionType
from app.schemas.common import InputModel, PatchModel, UTCTimestamp
from app.schemas.courses import Description, Order, Title

ExpectedKnowledge = Annotated[str, Field(max_length=5000)]
EssentialPoints = Annotated[
    list[Annotated[str, Field(min_length=1, max_length=500)]], Field(max_length=10)
]
Difficulty = Annotated[int, Field(ge=1, le=5)]
# 1 Essential, 2 Important, 3 Extra.
Priority = Annotated[int, Field(ge=1, le=3)]
QuestionText = Annotated[str, Field(min_length=1, max_length=2000)]


class QuestionCreate(InputModel):
    question_type: QuestionType
    text: QuestionText


class QuestionGenerate(InputModel):
    """Ask the AI for more formulations of one Learning Item (spec §27-29)."""

    count: int = Field(default=3, ge=1, le=5)
    # Empty: explanation, application and scenario questions.
    question_types: list[QuestionType] | None = Field(default=None, min_length=1, max_length=5)


class QuestionRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    question_type: QuestionType
    text: str
    times_asked: int
    last_asked_at: UTCTimestamp | None


class MemoryRead(BaseModel):
    """The item's memory state (spec §23, §48). Read-only: only the SchedulingPolicy moves it."""

    model_config = ConfigDict(from_attributes=True)

    state: MemoryState
    level: int
    due_at: UTCTimestamp | None
    last_reviewed_at: UTCTimestamp | None
    review_count: int
    successful_review_count: int
    failed_review_count: int
    lapse_count: int
    hard_count: int
    marked_hard: bool


class LearningItemRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    # TEXT or DRAWING (answered by drawing, against a reference drawing).
    answer_format: str
    priority: int
    concept_id: UUID
    topic_id: UUID
    chapter_id: UUID
    course_id: UUID
    title: str
    objective: str
    expected_knowledge: str
    essential_points: list[str]
    role: LearningItemRole
    in_training: bool
    difficulty: int
    order: int
    paused: bool
    review_state: MemoryRead
    questions: list[QuestionRead]
    ai_provider: str | None
    ai_model: str | None
    prompt_version: str | None
    created_at: UTCTimestamp
    updated_at: UTCTimestamp


class LearningItemCreate(InputModel):
    """A Learning Item the user writes by hand, e.g. for a Concept with no source material."""

    title: Title
    objective: Description = ""
    expected_knowledge: ExpectedKnowledge = ""
    essential_points: EssentialPoints = Field(default_factory=list)
    role: LearningItemRole = LearningItemRole.CORE_TRAINABLE
    difficulty: Difficulty = 3
    # None: from the role (CORE_TRAINABLE → Essential, ...).
    priority: Priority | None = None
    questions: list[QuestionCreate] = Field(default_factory=list, max_length=5)


class LearningItemUpdate(PatchModel):
    title: Title | None = None
    objective: Description | None = None
    expected_knowledge: ExpectedKnowledge | None = None
    essential_points: EssentialPoints | None = None
    role: LearningItemRole | None = None
    difficulty: Difficulty | None = None
    priority: Priority | None = None
    order: Order | None = None


class QuestionUpdate(PatchModel):
    question_type: QuestionType | None = None
    text: QuestionText | None = None


class BulkItemAction(InputModel):
    """One action on many Learning Items of a Course (all or nothing)."""

    item_ids: list[UUID] = Field(min_length=1, max_length=500)
    action: Literal["delete", "pause", "resume", "move", "set_priority"]
    # set_priority only.
    priority: Priority | None = None
    # move: exactly one destination. Into a concept: the items join it. Into a topic: each item
    # keeps a concept of its own there (whole concepts move; partly selected ones are split).
    target_concept_id: UUID | None = None
    target_topic_id: UUID | None = None
    # delete/move: concepts left without any item by this request are deleted too.
    delete_emptied_concepts: bool = True


class BulkItemResult(BaseModel):
    affected: int
    created_concepts: int
    deleted_concepts: int
