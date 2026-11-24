"""Read question/answer pairs from a labelled document — no AI involved.

The user writes their own questions and expected answers, marking each with a label at the start
of a line:

    Domanda: Qual è il presupposto dell'IRES?
    Risposta: Il possesso di redditi, in denaro o in natura, ...

Accepted question labels: "Domanda", "Quesito", "Question" (any case, followed by ":", ".",
")" or a dash, optionally numbered: "Domanda 3:", "1. Domanda:"), or the single capital letters
"D:" / "Q:". Answer labels: "Risposta", "Soluzione", "Answer", or "R:" / "A:". Single letters need
a colon so ordinary text ("D.Lgs. 209/2023", "a) primo punto") is never mistaken for a label.
A question and its answer may also sit on one line ("Domanda: ... Risposta: ...", full-word
answer labels only).

Text between labels belongs to the current question or answer, so both may span several lines,
paragraphs and pages. Document headings group the questions into topics.
"""

import re
from dataclasses import dataclass, field

from app.services.documents.blocks import IMAGE_MARKER, Block
from app.services.documents.cleaning import clean_text

MAX_PAIRS = 2000

_NUMBER = r"(?:\s*(?:n\.?\s*)?\d+)?"
# ":", ".", ")", hyphen, en dash, em dash.
_SEPARATOR = r"[:.)\-\u2013\u2014]"
_QUESTION = re.compile(
    r"^\s*(?:[-*•]\s*)?(?:\d+\s*[.)]\s*)?"
    rf"(?:(?:(?i:domanda|quesito|question)){_NUMBER}\s*{_SEPARATOR}|[DQ]{_NUMBER}\s*:)\s*"
)
_ANSWER = re.compile(
    r"^\s*(?:[-*•]\s*)?"
    rf"(?:(?:(?i:risposta|soluzione|answer)){_NUMBER}\s*{_SEPARATOR}|[RA]{_NUMBER}\s*:)\s*"
)


def _md_line(line: str) -> str:
    """Markdown a chatbot leaves on a line: "\\" at the end (a line break) and escapes."""
    line = re.sub(r"\\+[ \t]*$", "", line)
    line = re.sub(r"\\+(?=\s)", "", line)
    line = re.sub(r"\\([\\`*_{}\[\]()#+\-.!|>~])", r"\1", line)
    return re.sub(r"(\*\*|__)(.+?)\1", r"\2", line)


_BOLD_LABEL = re.compile(r"^(\s*(?:[-*•]\s+)?)[*_]{1,3}([^*_\n]{1,30}?)[*_]{1,3}(?=\s|:|$)")
_PICTURE = re.compile(IMAGE_MARKER.replace("{}", r"(\d+)"))
_LIST_ITEM = re.compile(r"\s*(?:[-*•]|\d+[.)]|[a-z]\))\s")
# An answer label later on the question's own line: full words only, after whitespace.
_INLINE_ANSWER = re.compile(r"\s(?i:risposta|soluzione|answer)\s*:\s*")


@dataclass
class QuestionAnswer:
    question: str
    answer: str
    # The document heading the pair appears under; groups pairs into topics.
    heading: str | None
    page: int | None
    page_end: int | None = None
    # The question's own lines as written (multiple-choice options are found in them).
    question_lines: list[str] = field(default_factory=list)
    # Pictures under "Risposta:" (Extraction.images indexes): a drawing as the expected answer.
    answer_images: list[int] = field(default_factory=list)
    # Pictures between "Domanda:" and "Risposta:": shown with the question.
    question_images: list[int] = field(default_factory=list)


@dataclass
class ParseResult:
    pairs: list[QuestionAnswer] = field(default_factory=list)
    # Questions found without an answer, by page (None when the format has no pages).
    unanswered_pages: list[int | None] = field(default_factory=list)
    truncated: bool = False


@dataclass
class _Draft:
    heading: str | None
    page: int | None
    question: list[str] = field(default_factory=list)
    answer: list[str] | None = None
    last_page: int | None = None
    answer_images: list[int] = field(default_factory=list)
    question_images: list[int] = field(default_factory=list)


def parse_question_bank(blocks: list[Block]) -> ParseResult:
    result = ParseResult()
    heading: str | None = None
    draft: _Draft | None = None

    def finish() -> None:
        nonlocal draft
        if draft is None:
            return
        question = clean_text("\n".join(draft.question))
        answer = _paragraphs(draft.answer or [])
        if question and (answer or draft.answer_images):
            if len(result.pairs) >= MAX_PAIRS:
                result.truncated = True
            else:
                page_end = draft.last_page if draft.last_page != draft.page else None
                result.pairs.append(
                    QuestionAnswer(
                        question,
                        answer,
                        draft.heading,
                        draft.page,
                        page_end,
                        [line for line in draft.question if line.strip()],
                        list(draft.answer_images),
                        list(draft.question_images),
                    )
                )
        elif question:
            result.unanswered_pages.append(draft.page)
        draft = None

    for block in blocks:
        for raw_line in block.text.split("\n"):
            picture = _PICTURE.fullmatch(raw_line.strip())
            if picture:
                # Under "Domanda:" it goes with the question; under "Risposta:" it is the
                # expected drawing; before any question it is ignored.
                if draft is not None:
                    images = (
                        draft.answer_images if draft.answer is not None else draft.question_images
                    )
                    images.append(int(picture.group(1)))
                continue
            # Chatbots often write labels in bold: "**Domanda:** …", "__Risposta__: …".
            line = _BOLD_LABEL.sub(r"\1\2", _md_line(raw_line))
            question_label = _QUESTION.match(line)
            answer_label = _ANSWER.match(line)
            if question_label:
                finish()
                draft = _Draft(heading=heading, page=block.page, last_page=block.page)
                rest = line[question_label.end() :]
                inline = _INLINE_ANSWER.search(rest)
                if inline:
                    draft.question.append(rest[: inline.start()])
                    draft.answer = [rest[inline.end() :]]
                else:
                    draft.question.append(rest)
            elif answer_label and draft is not None and draft.answer is None:
                draft.answer = [line[answer_label.end() :]]
                draft.last_page = block.page_end or block.page
            elif block.is_heading:
                # A heading closes the current pair and names the pairs that follow.
                finish()
                heading = clean_text(line).replace("**", "").strip("_ ") or heading
            elif draft is not None:
                (draft.answer if draft.answer is not None else draft.question).append(line)
                draft.last_page = block.page_end or block.page
            # Text before the first question (a title page, instructions) is ignored.
        if draft is not None and draft.answer is not None:
            # Paragraph breaks inside an answer are kept as breaks in its text.
            draft.answer.append("")
    finish()
    return result


def _paragraphs(lines: list[str]) -> str:
    """Wrapped lines are rejoined, but paragraphs ("" markers) and list items stay on their own
    lines, so an enumerated answer still reads as a list."""
    paragraphs: list[list[str]] = [[]]
    for line in lines:
        if not line.strip() or _LIST_ITEM.match(line):
            paragraphs.append([])
        if line.strip():
            paragraphs[-1].append(line)
    cleaned = (clean_text("\n".join(paragraph)) for paragraph in paragraphs)
    return "\n".join(text for text in cleaned if text)
