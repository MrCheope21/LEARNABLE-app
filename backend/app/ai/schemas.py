"""Inputs and structured outputs of AIProvider operations (docs/AI.md §2, §5).

Output models are the JSON schema every provider response is validated against; nothing reads a
provider's free-form prose (docs/PROJECT_SPEC.md §36). Limits mirror the column sizes the output
is eventually stored in, and cap how much a single response can create.
"""

from dataclasses import dataclass
from typing import Annotated

from pydantic import BaseModel, ConfigDict, Field

from app.models.enums import EvaluationClassification, LearningItemRole, QuestionType

AITitle = Annotated[str, Field(min_length=1, max_length=200)]
AIDescription = Annotated[str, Field(max_length=2000)]


class AIOutputModel(BaseModel):
    # Extra keys are ignored rather than rejected: a model adding a harmless field shouldn't cost
    # a retry. Everything the app reads is still required and validated.
    model_config = ConfigDict(str_strip_whitespace=True, extra="ignore")


# --- Curriculum generation (docs/PROJECT_SPEC.md §20) ---


@dataclass(frozen=True)
class SourcePassage:
    """One Course passage sent to the model. `ref` is a short label ("S1") the model cites
    instead of a UUID, which is cheaper and harder to garble."""

    ref: str
    document_name: str
    page_number: int | None
    section: str | None
    text: str
    page_end: int | None = None


@dataclass(frozen=True)
class CurriculumRequest:
    course_title: str
    # The Course's language code; generated titles and descriptions are written in it.
    language: str
    passages: list[SourcePassage]


class ProposedConcept(AIOutputModel):
    title: AITitle
    description: AIDescription = ""
    # Refs of the passages this Concept is grounded in. Refs that weren't in the request are
    # dropped by the caller, and a Concept left with none is dropped (spec §19).
    source_refs: list[str] = Field(default_factory=list, max_length=20)


class ProposedTopic(AIOutputModel):
    title: AITitle
    description: AIDescription = ""
    concepts: list[ProposedConcept] = Field(default_factory=list, max_length=100)


class ProposedChapter(AIOutputModel):
    title: AITitle
    description: AIDescription = ""
    topics: list[ProposedTopic] = Field(default_factory=list, max_length=50)


class CurriculumOutput(AIOutputModel):
    # False when the passages don't contain enough to build a curriculum from (spec §19:
    # INSUFFICIENT_CONTEXT instead of inventing one).
    context_sufficient: bool
    chapters: list[ProposedChapter] = Field(default_factory=list, max_length=50)


# --- Chapter curriculum: Topics → Concepts for one Chapter, merged with what it has ---


@dataclass(frozen=True)
class ExistingConcept:
    ref: str  # "C1"
    title: str


@dataclass(frozen=True)
class ExistingTopic:
    ref: str  # "T1"
    title: str
    concepts: list[ExistingConcept]


@dataclass(frozen=True)
class ChapterCurriculumRequest:
    course_title: str
    chapter_title: str
    language: str
    # What the Chapter already contains, so new material is placed into it instead of
    # duplicating it.
    existing_topics: list[ExistingTopic]
    passages: list[SourcePassage]


class ProposedChapterConcept(ProposedConcept):
    # Set when the passages teach an existing Concept: the caller links the passages to it
    # instead of creating a duplicate. Refs that don't exist are treated as new.
    existing_concept_ref: str | None = None


class ProposedChapterTopic(AIOutputModel):
    title: AITitle
    description: AIDescription = ""
    # Set to place the concepts into an existing Topic.
    existing_topic_ref: str | None = None
    concepts: list[ProposedChapterConcept] = Field(default_factory=list, max_length=100)


class ChapterCurriculumOutput(AIOutputModel):
    context_sufficient: bool
    topics: list[ProposedChapterTopic] = Field(default_factory=list, max_length=50)


# --- Learning Items + questions for one Concept (docs/PROJECT_SPEC.md §24-29) ---


@dataclass(frozen=True)
class LearningItemsRequest:
    course_title: str
    chapter_title: str
    topic_title: str
    concept_title: str
    concept_description: str
    language: str
    # The Concept's own source passages (its concept_sources), nothing else from the Course.
    passages: list[SourcePassage]


class ProposedQuestion(AIOutputModel):
    question_type: QuestionType
    text: Annotated[str, Field(min_length=1, max_length=2000)]


class ProposedLearningItem(AIOutputModel):
    title: AITitle
    objective: AIDescription = ""
    # The reference answer, from the passages only.
    expected_knowledge: Annotated[str, Field(min_length=1, max_length=5000)]
    essential_points: list[Annotated[str, Field(min_length=1, max_length=500)]] = Field(
        default_factory=list, max_length=10
    )
    role: LearningItemRole
    difficulty: int = Field(default=3, ge=1, le=5)
    source_refs: list[str] = Field(default_factory=list, max_length=20)
    questions: list[ProposedQuestion] = Field(default_factory=list, max_length=5)


class LearningItemsOutput(AIOutputModel):
    context_sufficient: bool
    items: list[ProposedLearningItem] = Field(default_factory=list, max_length=12)


# --- Question generation for one Learning Item (docs/PROJECT_SPEC.md §27-29) ---


@dataclass(frozen=True)
class QuestionsRequest:
    course_title: str
    concept_title: str
    item_title: str
    objective: str
    expected_knowledge: str
    essential_points: list[str]
    question_types: list[QuestionType]
    count: int
    language: str
    # The item's own source passages only (its learning_item_sources).
    passages: list[SourcePassage]
    existing_questions: list[str]


class QuestionsOutput(AIOutputModel):
    context_sufficient: bool
    questions: list[ProposedQuestion] = Field(default_factory=list, max_length=10)


# --- Answer evaluation (docs/PROJECT_SPEC.md §37-41) ---


@dataclass(frozen=True)
class EvaluationRequest:
    language: str
    question: str
    objective: str
    # The reference answer and the points a correct answer must contain, from the sources.
    expected_knowledge: str
    essential_points: list[str]
    # The Learning Item's own source passages: the authority for this evaluation (spec §19).
    passages: list[SourcePassage]
    answer: str


Score = Annotated[float, Field(ge=0.0, le=1.0)]
Point = Annotated[str, Field(max_length=500)]


class EvaluationOutput(AIOutputModel):
    """Semantic evidence only. Deliberately no review outcome (AGAIN/HARD/GOOD/EASY): that is
    decided by the deterministic ReviewOutcomeResolver, so no model's quirks can drive the
    schedule (spec §42; this supersedes the `outcome` field in spec §37)."""

    classification: EvaluationClassification
    correctness: Score
    completeness: Score
    conceptual_understanding: Score
    precision: Score
    # How sure the evaluator is of this judgement.
    confidence: Score
    correct_points: list[Point] = Field(default_factory=list, max_length=20)
    missing_points: list[Point] = Field(default_factory=list, max_length=20)
    misconceptions: list[Point] = Field(default_factory=list, max_length=20)
    # Where the answer contradicts the course material, with what the material says.
    source_corrections: list[Point] = Field(default_factory=list, max_length=20)
    # False when the passages don't let the answer be judged (spec §19): never guessed.
    context_sufficient: bool
    feedback: Annotated[str, Field(max_length=3000)] = ""
