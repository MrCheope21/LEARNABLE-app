"""MockAIProvider: deterministic, offline, no API key (docs/PROJECT_SPEC.md §76).

Used by every automated test and by `AI_PROVIDER=mock` for local development, so the whole flow
can run without a real model. Its output is mechanical, not a real curriculum: one Chapter per
document, one Topic per section, one Concept per passage, each citing that passage. For a
Chapter, a Topic or Concept whose title equals an existing one is matched to it, which is enough
to exercise the merge-with-existing flow.
"""

import re
from collections.abc import Callable
from dataclasses import replace
from itertools import groupby
from pathlib import PurePath

from app.ai.provider import (
    AICallInfo,
    ChapterCurriculumResult,
    CurriculumResult,
    EvaluationResult,
    LearningItemsResult,
    QuestionsResult,
)
from app.ai.schemas import (
    ChapterCurriculumOutput,
    ChapterCurriculumRequest,
    CurriculumOutput,
    CurriculumRequest,
    EvaluationOutput,
    EvaluationRequest,
    LearningItemsOutput,
    LearningItemsRequest,
    ProposedChapter,
    ProposedChapterConcept,
    ProposedChapterTopic,
    ProposedConcept,
    ProposedLearningItem,
    ProposedQuestion,
    ProposedTopic,
    QuestionsOutput,
    QuestionsRequest,
    SourcePassage,
)
from app.models.enums import EvaluationClassification, LearningItemRole, QuestionType
from app.services.documents.sentences import split_sentences

MOCK_INFO = AICallInfo(
    provider="mock",
    model="mock",
    model_version="mock-1",
    prompt_version="mock_curriculum_v1",
    latency_ms=0,
    attempts=1,
)
MOCK_CHAPTER_INFO = replace(MOCK_INFO, prompt_version="mock_chapter_curriculum_v1")
MOCK_ITEMS_INFO = replace(MOCK_INFO, prompt_version="mock_learning_items_v1")
MOCK_EVALUATION_INFO = replace(MOCK_INFO, prompt_version="mock_evaluation_v1")
MOCK_QUESTIONS_INFO = replace(MOCK_INFO, prompt_version="mock_questions_v1")
# Passages turned into Learning Items by the mechanical generator, at most.
_MOCK_ITEMS_PER_CONCEPT = 3

_PASSAGES_PER_UNNAMED_TOPIC = 5
# Titles are whole sentences where possible, shortened at a word boundary (columns hold 200).
_MAX_TITLE_CHARS = 150
# Mechanical question wording, in the Course's language (English otherwise).
_QUESTION_TEMPLATES = {
    "it": ("Che cosa sai di: {title}", "Spiega con parole tue: {title}"),
    "en": ("What do you know about: {title}", "Explain in your own words: {title}"),
}


class MockAIProvider:
    def __init__(
        self,
        curriculum: CurriculumOutput | None = None,
        error: Exception | None = None,
        chapter_curriculum: ChapterCurriculumOutput | None = None,
        learning_items: LearningItemsOutput | None = None,
        evaluation: EvaluationOutput
        | Callable[[EvaluationRequest], EvaluationOutput]
        | None = None,
    ) -> None:
        """`curriculum`/`chapter_curriculum` replace the generated output and `error` is raised
        instead of answering, so tests can script any provider behavior."""
        self._curriculum = curriculum
        self._chapter_curriculum = chapter_curriculum
        self._error = error
        self.curriculum_requests: list[CurriculumRequest] = []
        self.chapter_requests: list[ChapterCurriculumRequest] = []
        self._learning_items = learning_items
        self.learning_item_requests: list[LearningItemsRequest] = []
        self._evaluation = evaluation
        self.evaluation_requests: list[EvaluationRequest] = []
        self.question_requests: list[QuestionsRequest] = []

    def generate_curriculum(self, request: CurriculumRequest) -> CurriculumResult:
        self.curriculum_requests.append(request)
        if self._error is not None:
            raise self._error
        output = self._curriculum or _mechanical_curriculum(request.passages)
        return CurriculumResult(output=output, info=MOCK_INFO)

    def generate_chapter_curriculum(
        self, request: ChapterCurriculumRequest
    ) -> ChapterCurriculumResult:
        self.chapter_requests.append(request)
        if self._error is not None:
            raise self._error
        output = self._chapter_curriculum or _mechanical_chapter_curriculum(request)
        return ChapterCurriculumResult(output=output, info=MOCK_CHAPTER_INFO)

    def generate_learning_items(self, request: LearningItemsRequest) -> LearningItemsResult:
        self.learning_item_requests.append(request)
        if self._error is not None:
            raise self._error
        output = self._learning_items or _mechanical_learning_items(request)
        return LearningItemsResult(output=output, info=MOCK_ITEMS_INFO)

    def generate_questions(self, request: QuestionsRequest) -> QuestionsResult:
        self.question_requests.append(request)
        if self._error is not None:
            raise self._error
        return QuestionsResult(output=_mechanical_questions(request), info=MOCK_QUESTIONS_INFO)

    def evaluate_answer(self, request: EvaluationRequest) -> EvaluationResult:
        self.evaluation_requests.append(request)
        if self._error is not None:
            raise self._error
        if callable(self._evaluation):
            output = self._evaluation(request)
        else:
            output = self._evaluation or _mechanical_evaluation(request)
        return EvaluationResult(output=output, info=MOCK_EVALUATION_INFO)


def _mechanical_curriculum(passages: list[SourcePassage]) -> CurriculumOutput:
    chapters = []
    for document_name, doc_passages in groupby(passages, key=lambda p: p.document_name):
        topics = [
            ProposedTopic(title=title, concepts=[_concept(p) for p in group])
            for title, group in _topic_groups(list(doc_passages))
        ]
        chapters.append(ProposedChapter(title=_title(PurePath(document_name).stem), topics=topics))
    return CurriculumOutput(context_sufficient=bool(chapters), chapters=chapters)


def _mechanical_chapter_curriculum(request: ChapterCurriculumRequest) -> ChapterCurriculumOutput:
    topic_refs = {t.title: t.ref for t in request.existing_topics}
    concept_refs = {c.title: c.ref for t in request.existing_topics for c in t.concepts}
    topics = []
    for title, group in _topic_groups(request.passages):
        concepts = []
        for passage in group:
            concept = _concept(passage)
            concepts.append(
                ProposedChapterConcept(
                    **concept.model_dump(), existing_concept_ref=concept_refs.get(concept.title)
                )
            )
        topics.append(
            ProposedChapterTopic(
                title=title, existing_topic_ref=topic_refs.get(title), concepts=concepts
            )
        )
    return ChapterCurriculumOutput(context_sufficient=bool(topics), topics=topics)


def _mechanical_learning_items(request: LearningItemsRequest) -> LearningItemsOutput:
    """One CORE_TRAINABLE item per passage (up to 3), each with two formulations, so question
    rotation can be exercised. The expected knowledge is the passage itself."""
    items = []
    for passage in request.passages[:_MOCK_ITEMS_PER_CONCEPT]:
        sentences = split_sentences(passage.text)
        title = _title(sentences[0]) if sentences else request.concept_title
        recall, explain = _QUESTION_TEMPLATES.get(request.language, _QUESTION_TEMPLATES["en"])
        items.append(
            ProposedLearningItem(
                title=title,
                objective=f"{request.concept_title}: {title}",
                expected_knowledge=passage.text[:5000],
                essential_points=[_title(s)[:500] for s in sentences[:3]],
                role=LearningItemRole.CORE_TRAINABLE,
                source_refs=[passage.ref],
                questions=[
                    ProposedQuestion(
                        question_type=QuestionType.RECALL, text=recall.format(title=title)
                    ),
                    ProposedQuestion(
                        question_type=QuestionType.EXPLANATION, text=explain.format(title=title)
                    ),
                ],
            )
        )
    return LearningItemsOutput(context_sufficient=bool(items), items=items)


def _mechanical_questions(request: QuestionsRequest) -> QuestionsOutput:
    """One question per requested type (up to `count`), worded from the item's title, skipping
    any that already exist. Needs a reference answer, like the real prompt."""
    if not request.expected_knowledge.strip():
        return QuestionsOutput(context_sufficient=False)
    existing = set(request.existing_questions)
    questions = []
    for question_type in request.question_types:
        text = f"{question_type.value.replace('_', ' ').capitalize()}: {request.item_title}"
        if text not in existing:
            questions.append(ProposedQuestion(question_type=question_type, text=text))
    return QuestionsOutput(context_sufficient=True, questions=questions[: request.count])


_WORD = re.compile(r"\w{4,}")


def _mechanical_evaluation(request: EvaluationRequest) -> EvaluationOutput:
    """Keyword overlap with the essential points. Explicitly NOT a real evaluator (spec §39
    forbids keyword matching as the evaluation strategy); it only makes local development and
    tests produce plausible, deterministic grades."""
    if not request.passages and not request.expected_knowledge:
        return EvaluationOutput(
            classification=EvaluationClassification.UNCERTAIN,
            correctness=0.0,
            completeness=0.0,
            conceptual_understanding=0.0,
            precision=0.0,
            confidence=0.2,
            context_sufficient=False,
            feedback="There is no source material to evaluate this answer against.",
        )
    answer_words = set(_WORD.findall(request.answer.lower()))
    points = request.essential_points or [request.expected_knowledge]
    hit = [p for p in points if _covered(p, answer_words)]
    missing = [p for p in points if p not in hit]
    coverage = len(hit) / len(points)
    if coverage >= 0.8:
        classification = EvaluationClassification.CORRECT
    elif coverage >= 0.3:
        classification = EvaluationClassification.PARTIALLY_CORRECT
    else:
        classification = EvaluationClassification.WRONG
    return EvaluationOutput(
        classification=classification,
        correctness=round(min(1.0, coverage + 0.1), 2),
        completeness=round(coverage, 2),
        conceptual_understanding=round(coverage, 2),
        precision=0.9 if hit else 0.2,
        confidence=0.9,
        correct_points=hit[:20],
        missing_points=missing[:20],
        context_sufficient=True,
        feedback="Mock evaluation (keyword overlap).",
    )


def _covered(point: str, answer_words: set[str]) -> bool:
    words = set(_WORD.findall(point.lower()))
    return bool(words) and len(words & answer_words) / len(words) >= 0.5


def _topic_groups(passages: list[SourcePassage]) -> list[tuple[str, list[SourcePassage]]]:
    groups: list[tuple[str, list[SourcePassage]]] = []
    for section, section_passages in groupby(passages, key=lambda p: p.section):
        items = list(section_passages)
        if section:
            groups.append((_title(section), items))
            continue
        for start in range(0, len(items), _PASSAGES_PER_UNNAMED_TOPIC):
            groups.append(
                (f"Part {len(groups) + 1}", items[start : start + _PASSAGES_PER_UNNAMED_TOPIC])
            )
    return groups


def _concept(passage: SourcePassage) -> ProposedConcept:
    sentences = split_sentences(passage.text)
    first_sentence = sentences[0] if sentences else passage.text
    return ProposedConcept(
        title=_title(first_sentence),
        description=passage.text[:300],
        source_refs=[passage.ref],
    )


def _title(text: str) -> str:
    text = " ".join(text.split()) or "Untitled"
    if len(text) <= _MAX_TITLE_CHARS:
        return text
    cut = text[: _MAX_TITLE_CHARS - 1]
    # End on a whole word rather than mid-word ("dall'art. 73 TU…").
    if " " in cut:
        cut = cut[: cut.rindex(" ")]
    return cut.rstrip(" ,;:") + "…"
