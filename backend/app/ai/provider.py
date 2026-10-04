"""The AIProvider interface and its model-backed implementation (docs/AI.md §2).

Services depend on `AIProvider` only. Which implementation runs, which vendor serves it and which
model answers are configuration (docs/PROJECT_SPEC.md §33, §35); nothing here depends on the coding
agent that wrote it.

Operations arrive with the phase that needs them: `generate_curriculum` and
`generate_chapter_curriculum` now (Phase 6); learning items and questions (Phase 8), answer
evaluation and feedback (Phase 10) and exams (Phase 15) are added to this same interface.
"""

import json
import logging
import time
from dataclasses import dataclass
from enum import StrEnum
from typing import Protocol

from pydantic import BaseModel, ValidationError

from app.ai.failures import FailureKind
from app.ai.schemas import (
    ChapterCurriculumOutput,
    ChapterCurriculumRequest,
    CurriculumOutput,
    CurriculumRequest,
    DrawingEvaluationRequest,
    EvaluationOutput,
    EvaluationRequest,
    ExistingTopic,
    LearningItemsOutput,
    LearningItemsRequest,
    QuestionsOutput,
    QuestionsRequest,
    SourcePassage,
)
from app.ai.structured import response_schema
from app.ai.transport import ChatCompletion, ChatMessage, ChatTransport
from app.core.errors import AIInvalidOutputError
from app.prompts import answer_evaluation_v1 as evaluation_prompt
from app.prompts import chapter_curriculum_v1 as chapter_prompt
from app.prompts import curriculum_generation_v1 as curriculum_prompt
from app.prompts import drawing_evaluation_v1 as drawing_prompt
from app.prompts import learning_item_generation_v1 as items_prompt
from app.prompts import question_generation_v1 as questions_prompt

logger = logging.getLogger(__name__)


class AIOperation(StrEnum):
    GENERATE_CURRICULUM = "generate_curriculum"
    GENERATE_CHAPTER_CURRICULUM = "generate_chapter_curriculum"
    GENERATE_LEARNING_ITEMS = "generate_learning_items"
    GENERATE_QUESTIONS = "generate_questions"
    EVALUATE_ANSWER = "evaluate_answer"
    EVALUATE_DRAWING = "evaluate_drawing"


class StructuredOutput(StrEnum):
    """How a model is asked for machine-readable output. Whatever is asked, the answer is always
    validated locally against the application schema (docs/FREE_AI_ROUTING.md §6)."""

    NONE = "none"  # prompt instructions only
    JSON_OBJECT = "json_object"  # response_format json_object
    JSON_SCHEMA = "json_schema"  # the schema, best effort
    JSON_SCHEMA_STRICT = "json_schema_strict"  # constrained decoding to the schema


class ModelGroup(StrEnum):
    """Which AI_MODEL_<GROUP> setting an operation uses (spec §34)."""

    EXTRACTION = "extraction"
    GENERATION = "generation"
    EVALUATION = "evaluation"
    EXAM = "exam"


OPERATION_MODEL_GROUP = {
    AIOperation.GENERATE_CURRICULUM: ModelGroup.GENERATION,
    AIOperation.GENERATE_CHAPTER_CURRICULUM: ModelGroup.GENERATION,
    AIOperation.GENERATE_LEARNING_ITEMS: ModelGroup.GENERATION,
    AIOperation.GENERATE_QUESTIONS: ModelGroup.GENERATION,
    AIOperation.EVALUATE_ANSWER: ModelGroup.EVALUATION,
    AIOperation.EVALUATE_DRAWING: ModelGroup.EVALUATION,
}


@dataclass(frozen=True)
class AICallInfo:
    """What produced a result, stored alongside it (spec §73, §74)."""

    provider: str
    model: str
    # The model the provider reports serving; falls back to `model` when it doesn't say.
    model_version: str
    prompt_version: str
    latency_ms: int
    attempts: int
    # Position of the candidate that answered in its operation's route (0 = first choice).
    fallback_index: int = 0


@dataclass(frozen=True)
class CurriculumResult:
    output: CurriculumOutput
    info: AICallInfo


@dataclass(frozen=True)
class ChapterCurriculumResult:
    output: ChapterCurriculumOutput
    info: AICallInfo


@dataclass(frozen=True)
class LearningItemsResult:
    output: LearningItemsOutput
    info: AICallInfo


@dataclass(frozen=True)
class QuestionsResult:
    output: QuestionsOutput
    info: AICallInfo


@dataclass(frozen=True)
class EvaluationResult:
    output: EvaluationOutput
    info: AICallInfo


class AIProvider(Protocol):
    def generate_curriculum(self, request: CurriculumRequest) -> CurriculumResult: ...

    def generate_chapter_curriculum(
        self, request: ChapterCurriculumRequest
    ) -> ChapterCurriculumResult: ...

    def generate_learning_items(self, request: LearningItemsRequest) -> LearningItemsResult: ...

    def generate_questions(self, request: QuestionsRequest) -> QuestionsResult: ...

    def evaluate_answer(self, request: EvaluationRequest) -> EvaluationResult: ...

    def evaluate_drawing(self, request: DrawingEvaluationRequest) -> EvaluationResult: ...


@dataclass(frozen=True)
class ModelSettings:
    default_model: str
    group_models: dict[ModelGroup, str]
    temperature: float
    max_tokens: int
    json_mode: bool
    # None: JSON_OBJECT when json_mode, else NONE (the pre-routing behavior).
    structured: StructuredOutput | None = None

    @property
    def structured_output(self) -> StructuredOutput:
        if self.structured is not None:
            return self.structured
        return StructuredOutput.JSON_OBJECT if self.json_mode else StructuredOutput.NONE

    def model_for(self, operation: AIOperation) -> str:
        return self.group_models.get(OPERATION_MODEL_GROUP[operation]) or self.default_model


class _RetryPrompt(Protocol):
    def __call__(self, *, problem: str) -> str: ...


class LLMAIProvider:
    """AIProvider backed by a chat-completion model. Builds each operation's versioned prompt,
    then validates the answer against the operation's schema, retrying once with a constrained
    prompt when it isn't valid (spec §36)."""

    def __init__(
        self, provider_name: str, transport: ChatTransport, settings: ModelSettings
    ) -> None:
        self._provider_name = provider_name
        self._transport = transport
        self._settings = settings

    def generate_curriculum(self, request: CurriculumRequest) -> CurriculumResult:
        messages = [
            ChatMessage("system", curriculum_prompt.SYSTEM.substitute(language=request.language)),
            ChatMessage(
                "user",
                curriculum_prompt.USER.substitute(
                    course_title=request.course_title,
                    passages="\n\n".join(_format_passage(p) for p in request.passages),
                ),
            ),
        ]
        output, info = self._structured_call(
            AIOperation.GENERATE_CURRICULUM,
            curriculum_prompt.VERSION,
            messages,
            CurriculumOutput,
            curriculum_prompt.RETRY.substitute,
        )
        return CurriculumResult(output=output, info=info)

    def generate_chapter_curriculum(
        self, request: ChapterCurriculumRequest
    ) -> ChapterCurriculumResult:
        messages = [
            ChatMessage("system", chapter_prompt.SYSTEM.substitute(language=request.language)),
            ChatMessage(
                "user",
                chapter_prompt.USER.substitute(
                    course_title=request.course_title,
                    chapter_title=request.chapter_title,
                    existing=_format_existing(request.existing_topics),
                    passages="\n\n".join(_format_passage(p) for p in request.passages),
                ),
            ),
        ]
        output, info = self._structured_call(
            AIOperation.GENERATE_CHAPTER_CURRICULUM,
            chapter_prompt.VERSION,
            messages,
            ChapterCurriculumOutput,
            chapter_prompt.RETRY.substitute,
        )
        return ChapterCurriculumResult(output=output, info=info)

    def generate_learning_items(self, request: LearningItemsRequest) -> LearningItemsResult:
        messages = [
            ChatMessage("system", items_prompt.SYSTEM.substitute(language=request.language)),
            ChatMessage(
                "user",
                items_prompt.USER.substitute(
                    course_title=request.course_title,
                    chapter_title=request.chapter_title,
                    topic_title=request.topic_title,
                    concept_title=request.concept_title,
                    concept_description=request.concept_description,
                    passages="\n\n".join(_format_passage(p) for p in request.passages),
                ),
            ),
        ]
        output, info = self._structured_call(
            AIOperation.GENERATE_LEARNING_ITEMS,
            items_prompt.VERSION,
            messages,
            LearningItemsOutput,
            items_prompt.RETRY.substitute,
        )
        return LearningItemsResult(output=output, info=info)

    def generate_questions(self, request: QuestionsRequest) -> QuestionsResult:
        messages = [
            ChatMessage(
                "system",
                questions_prompt.SYSTEM.substitute(
                    language=request.language,
                    count=request.count,
                    question_types=", ".join(t.value for t in request.question_types),
                ),
            ),
            ChatMessage(
                "user",
                questions_prompt.USER.substitute(
                    course_title=request.course_title,
                    concept_title=request.concept_title,
                    item_title=request.item_title,
                    objective=request.objective or "(not stated)",
                    expected_knowledge=request.expected_knowledge,
                    essential_points="\n".join(f"- {p}" for p in request.essential_points)
                    or "(none listed)",
                    existing_questions="\n".join(f"- {q}" for q in request.existing_questions)
                    or "(none)",
                    passages="\n\n".join(_format_passage(p) for p in request.passages)
                    or "(no source passages)",
                ),
            ),
        ]
        output, info = self._structured_call(
            AIOperation.GENERATE_QUESTIONS,
            questions_prompt.VERSION,
            messages,
            QuestionsOutput,
            questions_prompt.RETRY.substitute,
        )
        return QuestionsResult(output=output, info=info)

    def evaluate_answer(self, request: EvaluationRequest) -> EvaluationResult:
        messages = [
            ChatMessage("system", evaluation_prompt.SYSTEM.substitute(language=request.language)),
            ChatMessage(
                "user",
                evaluation_prompt.USER.substitute(
                    question=request.question,
                    objective=request.objective,
                    expected_knowledge=request.expected_knowledge,
                    essential_points="\n".join(f"- {p}" for p in request.essential_points)
                    or "(none listed)",
                    passages="\n\n".join(_format_passage(p) for p in request.passages)
                    or "(no source passages)",
                    answer=request.answer,
                )
                + (
                    evaluation_prompt.OBJECTION.substitute(argument=request.user_argument)
                    if request.user_argument
                    else ""
                ),
            ),
        ]
        output, info = self._structured_call(
            AIOperation.EVALUATE_ANSWER,
            evaluation_prompt.VERSION,
            messages,
            EvaluationOutput,
            evaluation_prompt.RETRY.substitute,
        )
        return EvaluationResult(output=output, info=info)

    def evaluate_drawing(self, request: DrawingEvaluationRequest) -> EvaluationResult:
        text = drawing_prompt.USER.substitute(
            question=request.question,
            objective=request.objective or "(not stated)",
            expected_knowledge=request.expected_knowledge or "(none)",
            note=request.note or "(none)",
        )
        if request.user_argument:
            text += drawing_prompt.OBJECTION.substitute(argument=request.user_argument)
        messages = [
            ChatMessage("system", drawing_prompt.SYSTEM.substitute(language=request.language)),
            ChatMessage(
                "user",
                [
                    {"type": "text", "text": text},
                    {"type": "image_url", "image_url": {"url": request.reference.data_url()}},
                    {"type": "image_url", "image_url": {"url": request.drawing.data_url()}},
                ],
            ),
        ]
        output, info = self._structured_call(
            AIOperation.EVALUATE_DRAWING,
            drawing_prompt.VERSION,
            messages,
            EvaluationOutput,
            drawing_prompt.RETRY.substitute,
        )
        return EvaluationResult(output=output, info=info)

    def _structured_call[T: BaseModel](
        self,
        operation: AIOperation,
        prompt_version: str,
        messages: list[ChatMessage],
        schema: type[T],
        retry_prompt: _RetryPrompt,
    ) -> tuple[T, AICallInfo]:
        model = self._settings.model_for(operation)
        mode = self._settings.structured_output
        schema_hint = (
            response_schema(schema, strict=mode is StructuredOutput.JSON_SCHEMA_STRICT)
            if mode in (StructuredOutput.JSON_SCHEMA, StructuredOutput.JSON_SCHEMA_STRICT)
            else None
        )
        started = time.monotonic()
        attempts = 0
        completion: ChatCompletion | None = None
        try:
            attempt_messages = messages
            for attempts in (1, 2):
                completion = self._transport.complete(
                    model=model,
                    messages=attempt_messages,
                    temperature=self._settings.temperature,
                    max_tokens=self._settings.max_tokens,
                    json_mode=mode is StructuredOutput.JSON_OBJECT,
                    response_schema=schema_hint,
                )
                if completion.truncated:
                    # Retrying with the same token limit would be cut off again.
                    raise AIInvalidOutputError(
                        "The AI answer was cut off. Raise AI_MAX_TOKENS or send less material.",
                        details={
                            "reason": "truncated",
                            "failure": FailureKind.INVALID_STRUCTURED_OUTPUT,
                        },
                    )
                parsed, problem = _parse(completion.content, schema)
                if parsed is not None:
                    info = self._info(model, completion, prompt_version, started, attempts)
                    _log_call(operation, info, error_type=None)
                    return parsed, info
                # One constrained retry: the original prompt plus what was wrong. The rejected
                # answer itself isn't sent back (cost, and it may be long).
                attempt_messages = [*messages, ChatMessage("user", retry_prompt(problem=problem))]
            raise AIInvalidOutputError(
                "The AI answer wasn't valid, even after a retry.",
                details={
                    "reason": "schema",
                    "problem": problem,
                    "failure": FailureKind.INVALID_STRUCTURED_OUTPUT,
                },
            )
        except Exception as exc:
            info = self._info(model, completion, prompt_version, started, attempts)
            _log_call(operation, info, error_type=getattr(exc, "error_type", type(exc).__name__))
            raise

    def _info(
        self,
        model: str,
        completion: ChatCompletion | None,
        prompt_version: str,
        started: float,
        attempts: int,
    ) -> AICallInfo:
        return AICallInfo(
            provider=self._provider_name,
            model=model,
            model_version=(completion.served_model if completion else None) or model,
            prompt_version=prompt_version,
            latency_ms=round((time.monotonic() - started) * 1000),
            attempts=attempts,
        )


def _format_passage(passage: SourcePassage) -> str:
    origin = [f"Document: {passage.document_name}"]
    if passage.page_number is not None and passage.page_end is not None:
        origin.append(f"Pages {passage.page_number}-{passage.page_end}")
    elif passage.page_number is not None:
        origin.append(f"Page {passage.page_number}")
    if passage.section:
        origin.append(f"Section: {passage.section}")
    return curriculum_prompt.PASSAGE.substitute(
        ref=passage.ref, origin=" | ".join(origin), text=passage.text
    )


def _format_existing(topics: list[ExistingTopic]) -> str:
    if not topics:
        return "(empty: this chapter has no topics yet)"
    lines = []
    for topic in topics:
        lines.append(f"[{topic.ref}] {topic.title}")
        lines.extend(f"  [{concept.ref}] {concept.title}" for concept in topic.concepts)
    return "\n".join(lines)


def _parse[T: BaseModel](content: str, schema: type[T]) -> tuple[T | None, str]:
    """Returns (parsed, "") or (None, a short description of the problem). The description
    names locations and error kinds only, never the content, so it is safe to log and to send
    back in the retry prompt."""
    try:
        data = json.loads(_strip_code_fence(content))
    except json.JSONDecodeError as exc:
        return None, f"not valid JSON ({exc.msg} at line {exc.lineno})"
    try:
        return schema.model_validate(data), ""
    except ValidationError as exc:
        issues = [
            f"{'.'.join(str(part) for part in err['loc']) or 'root'}: {err['msg']}"
            for err in exc.errors()[:5]
        ]
        more = exc.error_count() - len(issues)
        return None, "; ".join(issues) + (f"; and {more} more" if more > 0 else "")


def _strip_code_fence(content: str) -> str:
    # Many models wrap JSON in ```json fences even when told not to; that alone isn't worth a
    # retry.
    text = content.strip()
    if text.startswith("```") and text.endswith("```"):
        text = text[3:-3]
        if text.startswith("json"):
            text = text[4:]
    return text.strip()


def _log_call(operation: AIOperation, info: AICallInfo, error_type: str | None) -> None:
    # Structured, content-free (spec §94): no prompt, passage or answer text.
    logger.info(
        "ai_call operation=%s provider=%s model=%s latency_ms=%d attempts=%d error_type=%s",
        operation,
        info.provider,
        info.model,
        info.latency_ms,
        info.attempts,
        error_type or "none",
    )
