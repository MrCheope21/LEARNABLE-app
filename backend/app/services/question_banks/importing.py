"""Import a question bank: the user's own questions and expected answers, as they wrote them.

Each question/answer pair becomes one passage (so "View source" shows exactly what the user
wrote), one Concept and one Learning Item whose single question is the user's question, verbatim,
and whose expected knowledge is the user's answer. No AI is involved. The Concepts arrive
NOT_STUDIED like any others; the user activates them to start reviewing (spec §21).
"""

import re
import uuid
from dataclasses import dataclass, replace
from pathlib import PurePath

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.core.errors import AppError
from app.db.types import utc_now
from app.models.course import Chapter, Concept, Course, Topic
from app.models.curriculum import ConceptSource
from app.models.document import Document, DocumentChunk
from app.models.enums import ItemGenerationStatus, LearningItemRole, QuestionType
from app.models.learning import LearningItemSource
from app.schemas.learning import Choice, LearningItemCreate, QuestionCreate
from app.services import drawings
from app.services.documents.blocks import Block
from app.services.documents.sentences import split_sentences
from app.services.learning import choices
from app.services.learning.service import new_item
from app.services.question_banks.parsing import MAX_PAIRS, QuestionAnswer, parse_question_bank
from app.storage.documents import DocumentStorage

NO_PAIRS = (
    'No questions were found. Start each question with "Domanda:" (or "Question:") and each '
    'answer with "Risposta:" (or "Answer:"), at the beginning of a line.'
)

_TITLE_CHARS = 200
_OBJECTIVE_CHARS = 2000
_POINT_CHARS = 500
_MAX_POINTS = 6
_DEFAULT_TOPIC = {"it": "Domande"}
_DEFAULT_TOPIC_EN = "Questions"


@dataclass(frozen=True)
class ImportResult:
    pairs: int
    notice: str | None


class NoQuestionsFoundError(Exception):
    pass


def import_question_bank(
    db: Session,
    document: Document,
    blocks: list[Block],
    images: list[bytes] | None = None,
    storage: DocumentStorage | None = None,
) -> ImportResult:
    """Adds chunks, hierarchy and items to the session; the caller commits. A picture under an
    answer (`images`, from a Word file) makes the item a drawing question with that picture as
    its reference drawing, saved in `storage`."""
    parsed = parse_question_bank(blocks)
    skipped_pictures = 0
    if not parsed.pairs:
        raise NoQuestionsFoundError(NO_PAIRS)
    course = db.get(Course, document.course_id)
    if course is None:
        raise NoQuestionsFoundError(NO_PAIRS)  # deleted meanwhile; the commit will fail anyway

    chapter = _chapter_for(db, document)
    topics: dict[str, Topic] = {}
    default_topic = _DEFAULT_TOPIC.get(course.language.split("-")[0].lower(), _DEFAULT_TOPIC_EN)
    next_concept_order: dict[uuid.UUID, int] = {}

    for position, labelled in enumerate(parsed.pairs):
        pair, priority = _priority(labelled)
        chunk = DocumentChunk(
            id=uuid.uuid4(),
            document_id=document.id,
            course_id=document.course_id,
            position=position,
            page_number=pair.page,
            page_end=pair.page_end,
            section=pair.heading[:500] if pair.heading else None,
            paragraph_start=position,
            paragraph_end=position,
            text=_passage_text(pair, course.language),
        )
        db.add(chunk)

        title = (pair.heading or default_topic)[:_TITLE_CHARS]
        topic = topics.get(title) or _topic_for(db, chapter, title)
        topics[title] = topic
        order = next_concept_order.get(topic.id)
        if order is None:
            last = db.scalar(select(func.max(Concept.order)).where(Concept.topic_id == topic.id))
            order = 0 if last is None else last + 1
        next_concept_order[topic.id] = order + 1

        # Its title is the question alone (a multiple-choice one without its options).
        made = _item_for(pair, priority)
        concept = Concept(
            id=uuid.uuid4(),
            topic_id=topic.id,
            chapter_id=chapter.id,
            course_id=document.course_id,
            title=made.title,
            order=order,
            # Items are already here: activation must not generate more over them.
            item_generation_status=ItemGenerationStatus.READY,
        )
        db.add(concept)
        db.flush()
        db.add(ConceptSource(concept_id=concept.id, chunk_id=chunk.id, course_id=course.id))
        item = new_item(db, concept, made, order=0)
        if pair.question_images and storage is not None:
            picture = _picture(images, pair.question_images[0])
            try:
                media_type = drawings.image_type(picture)
            except AppError:
                skipped_pictures += 1
            else:
                storage.save(drawings.question_image_key(item), picture)
                item.question_image_type = media_type
        if pair.answer_images and storage is not None:
            pictures = images or []
            index = pair.answer_images[0]
            picture = pictures[index] if index < len(pictures) else b""
            try:
                media_type = drawings.image_type(picture)
            except AppError:
                skipped_pictures += 1  # not PNG/JPEG/WebP, or over 3 MB: stays a text question
            else:
                storage.save(drawings.reference_key(item), picture)
                item.answer_format = "DRAWING"
                item.reference_drawing_type = media_type
        db.add(LearningItemSource(learning_item_id=item.id, chunk_id=chunk.id, course_id=course.id))

    document.analyzed_at = utc_now()
    notice = _notice(parsed.unanswered_pages, parsed.truncated)
    if skipped_pictures:
        extra = f"{skipped_pictures} picture(s) couldn't be used (PNG, JPEG or WebP up to 3 MB)."
        notice = f"{notice} {extra}" if notice else extra
    return ImportResult(len(parsed.pairs), notice)


def _chapter_for(db: Session, document: Document) -> Chapter:
    if document.chapter_id is not None:
        chapter = db.get(Chapter, document.chapter_id)
        if chapter is not None and chapter.course_id == document.course_id:
            return chapter
    last = db.scalar(select(func.max(Chapter.order)).where(Chapter.course_id == document.course_id))
    chapter = Chapter(
        id=uuid.uuid4(),
        course_id=document.course_id,
        title=(PurePath(document.filename).stem.strip() or document.filename)[:_TITLE_CHARS],
        order=0 if last is None else last + 1,
    )
    db.add(chapter)
    db.flush()
    document.chapter_id = chapter.id
    return chapter


def _topic_for(db: Session, chapter: Chapter, title: str) -> Topic:
    """The Chapter's Topic with this title, so re-importing a revised bank fills the same
    Topics instead of duplicating them."""
    existing = db.scalar(
        select(Topic)
        .where(Topic.chapter_id == chapter.id, Topic.title == title)
        .order_by(Topic.order)
        .limit(1)
    )
    if existing is not None:
        return existing
    last = db.scalar(select(func.max(Topic.order)).where(Topic.chapter_id == chapter.id))
    topic = Topic(
        id=uuid.uuid4(),
        chapter_id=chapter.id,
        course_id=chapter.course_id,
        title=title,
        order=0 if last is None else last + 1,
    )
    db.add(topic)
    db.flush()
    return topic


# "Priorità: 1" … "Priorità: 5", "Priorità: alta" or "Priority: accessory" at the end of a line
# of a question or its answer sets the question's priority; the label is not part of the text.
_PRIORITY_LINE = re.compile(
    # On its own line, or at the end of one (the parser joins a question's lines with spaces).
    r"(?:^|\s)(?i:priorit[aà]|priority)\s*[:.\-\u2013]\s*(?P<value>[^\s.,;]+)[.,;]?\s*$",
    re.MULTILINE,
)
_PRIORITY_WORDS = {
    # 1 Essential: must be known.
    "1": 1,
    "alta": 1,
    "essenziale": 1,
    "fondamentale": 1,
    "core": 1,
    "high": 1,
    "essential": 1,
    # 2 Important.
    "2": 2,
    "media": 2,
    "importante": 2,
    "medium": 2,
    "important": 2,
    # 3 Useful: completes the picture.
    "3": 3,
    "bassa": 3,
    "utile": 3,
    "complementare": 3,
    "extra": 3,
    "low": 3,
    "useful": 3,
    # 4 Accessory: a detail, not central.
    "4": 4,
    "accessoria": 4,
    "accessorio": 4,
    "secondaria": 4,
    "dettaglio": 4,
    "accessory": 4,
    "minor": 4,
    "detail": 4,
    # 5 In depth: optional.
    "5": 5,
    "approfondimento": 5,
    "facoltativa": 5,
    "facoltativo": 5,
    "curiosità": 5,
    "addendum": 5,
    "optional": 5,
    "in-depth": 5,
}


def _priority(pair: QuestionAnswer) -> tuple[QuestionAnswer, int | None]:
    found: int | None = None

    def take(match: re.Match[str]) -> str:
        nonlocal found
        value = _PRIORITY_WORDS.get(match.group("value").lower())
        if value is None:
            return match.group(0)
        found = found or value
        return ""

    question = _PRIORITY_LINE.sub(take, pair.question).strip()
    answer = _PRIORITY_LINE.sub(take, pair.answer).strip()
    return replace(pair, question=question, answer=answer), found


def _picture(images: list[bytes] | None, index: int) -> bytes:
    pictures = images or []
    return pictures[index] if index < len(pictures) else b""


def _multiple_choice(pair: QuestionAnswer) -> tuple[str, list[Choice]] | None:
    """The stem and the options, when the question lists options and the answer names them
    (services/learning/choices.py `detect`)."""
    lines = [line for line in pair.question_lines if not _PRIORITY_LINE.search(line)]
    found = choices.detect(lines or pair.question, pair.answer)
    if found is None:
        return None
    stem, options = found
    return stem, [Choice.model_construct(text=o["text"], correct=o["correct"]) for o in options]


def _item_for(pair: QuestionAnswer, priority: int | None) -> LearningItemCreate:
    found = _multiple_choice(pair)
    if found is not None:
        stem, options = found
        question = QuestionCreate.model_construct(question_type=QuestionType.RECALL, text=stem)
        return LearningItemCreate.model_construct(
            title=_shorten(stem, _TITLE_CHARS),
            objective=_shorten(stem, _OBJECTIVE_CHARS),
            expected_knowledge="",
            essential_points=[],
            role=LearningItemRole.CORE_TRAINABLE,
            difficulty=3,
            priority=priority,
            questions=[question],
            choices=options,
        )
    # model_construct: the user's full answer is kept even beyond the API's input limits, which
    # exist for hand-typed edits; only database column sizes are enforced, by cutting.
    sentences = [s for line in pair.answer.split("\n") for s in split_sentences(line)]
    points = [_shorten(s, _POINT_CHARS) for s in sentences[:_MAX_POINTS]]
    question = QuestionCreate.model_construct(question_type=QuestionType.RECALL, text=pair.question)
    return LearningItemCreate.model_construct(
        title=_shorten(pair.question, _TITLE_CHARS),
        objective=_shorten(pair.question, _OBJECTIVE_CHARS),
        expected_knowledge=pair.answer,
        essential_points=points,
        role=LearningItemRole.CORE_TRAINABLE,
        difficulty=3,
        priority=priority,
        questions=[question],
    )


def _passage_text(pair: QuestionAnswer, language: str) -> str:
    italian = language.split("-")[0].lower() == "it"
    answer = pair.answer or ("[disegno]" if italian else "[drawing]")
    if italian:
        return f"Domanda: {pair.question}\n\nRisposta: {answer}"
    return f"Question: {pair.question}\n\nAnswer: {answer}"


def _shorten(text: str, limit: int) -> str:
    text = " ".join(text.split())
    if len(text) <= limit:
        return text
    cut = text[: limit - 1]
    if " " in cut:
        cut = cut.rsplit(" ", 1)[0]
    return cut.rstrip(" ,;:") + "…"


def _notice(unanswered_pages: list[int | None], truncated: bool) -> str | None:
    parts: list[str] = []
    if unanswered_pages:
        pages = sorted({page for page in unanswered_pages if page is not None})
        where = f" (pages {', '.join(map(str, pages[:10]))})" if pages else ""
        count = len(unanswered_pages)
        noun = "question was" if count == 1 else "questions were"
        parts.append(f"{count} {noun} skipped because no answer followed{where}.")
    if truncated:
        parts.append(f"Only the first {MAX_PAIRS} questions were imported.")
    return " ".join(parts)[:500] or None
