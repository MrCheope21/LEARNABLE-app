"""Multiple-choice questions (docs/MULTIPLE_CHOICE.md): an item with `choices` is answered by
picking options and graded by the server, without AI. One correct option: pick it. Several:
pick exactly those.

Stored on the item as [{"text": str, "correct": bool}, …]; `answer_format` is then "CHOICE" and
`expected_knowledge` names the correct options (so the reference answer, search and the
marketplace page read as for any other question).
"""

import re
import uuid
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models.enums import EvaluationClassification, EvaluationStatus
from app.models.learning import LearningItem
from app.models.review import Evaluation

CHOICE = "CHOICE"
MIN_CHOICES, MAX_CHOICES = 2, 8
LETTERS = "ABCDEFGH"

_RIGHT = {"it": "Risposta giusta", "en": "Correct answer"}


def normalized(choices: list[Any]) -> list[dict[str, Any]]:
    """[{"text", "correct"}] from schema objects or dicts, text trimmed."""
    out = []
    for choice in choices:
        text = choice["text"] if isinstance(choice, dict) else choice.text
        correct = choice["correct"] if isinstance(choice, dict) else choice.correct
        out.append({"text": " ".join(str(text).split()), "correct": bool(correct)})
    return out


def problem(choices: list[dict[str, Any]]) -> str | None:
    """Why these options can't be a question, or None."""
    if not MIN_CHOICES <= len(choices) <= MAX_CHOICES:
        return f"A multiple-choice question has {MIN_CHOICES} to {MAX_CHOICES} options."
    texts = [c["text"].lower() for c in choices]
    if any(not t for t in texts):
        return "Every option needs a text."
    if len(set(texts)) != len(texts):
        return "Two options have the same text."
    if not any(c["correct"] for c in choices):
        return "Mark at least one option as correct."
    return None


def correct_texts(item: LearningItem) -> list[str]:
    return [c["text"] for c in item.choices or [] if c["correct"]]


def apply(item: LearningItem, choices: list[dict[str, Any]] | None) -> None:
    """Sets (or, with None or [], removes) the options; keeps the reference answer in step."""
    if choices:
        item.choices = choices
        item.answer_format = CHOICE
        right = "; ".join(c["text"] for c in choices if c["correct"])
        if not item.expected_knowledge or item.expected_knowledge.startswith("✓ "):
            item.expected_knowledge = f"✓ {right}"
        if not item.essential_points:
            item.essential_points = [c["text"] for c in choices if c["correct"]][:10]
    else:
        if item.answer_format == CHOICE:
            item.answer_format = "TEXT"
        item.choices = None


def answer_text(item: LearningItem, picked: list[int]) -> str:
    """What is stored as the answer's text: the picked options, one per line, with letters."""
    options = item.choices or []
    return "\n".join(f"{LETTERS[i]}) {options[i]['text']}" for i in sorted(set(picked)))


def picked_positions(item: LearningItem, answer_text_value: str) -> list[int]:
    """The options picked, from the stored answer text ("B) …" lines)."""
    count = len(item.choices or [])
    return sorted(
        {
            LETTERS.index(m.group(1))
            for m in re.finditer(r"^([A-H])\) ", answer_text_value, re.MULTILINE)
            if LETTERS.index(m.group(1)) < count
        }
    )


def grade(
    item: LearningItem, answer_text_value: str, evaluation: Evaluation, language: str
) -> Evaluation:
    """Fills in a deterministic evaluation from the stored answer text."""
    options = item.choices or []
    picked = set(picked_positions(item, answer_text_value))
    right = {i for i, c in enumerate(options) if c["correct"]}
    hits, wrong, missed = picked & right, picked - right, right - picked
    exact = picked == right
    if exact:
        classification = EvaluationClassification.CORRECT
        score = 1.0
    elif hits and not wrong:
        classification = EvaluationClassification.PARTIALLY_CORRECT
        score = len(hits) / len(right)
    else:
        classification = EvaluationClassification.WRONG
        score = 0.0
    label = _RIGHT.get(language.split("-")[0].lower(), _RIGHT["en"])
    right_text = "; ".join(f"{LETTERS[i]}) {options[i]['text']}" for i in sorted(right))
    evaluation.status = EvaluationStatus.COMPLETED
    evaluation.classification = classification
    evaluation.correctness = score
    evaluation.completeness = score
    evaluation.conceptual_understanding = score
    evaluation.precision = 1.0 if not wrong else 0.0
    evaluation.confidence = 1.0
    evaluation.correct_points = [options[i]["text"] for i in sorted(hits)]
    evaluation.missing_points = [options[i]["text"] for i in sorted(missed)]
    evaluation.misconceptions = [options[i]["text"] for i in sorted(wrong)]
    evaluation.source_corrections = []
    evaluation.context_sufficient = True
    evaluation.feedback = ""
    evaluation.gap = "" if exact else f"{label}: {right_text}"
    evaluation.ai_provider = "choice"
    evaluation.ai_model = "exact-match"
    evaluation.ai_model_version = "1"
    evaluation.prompt_version = "choice_v1"
    return evaluation


# --- Markdown left in text by chatbots ---

# A backslash at the end of a line is Markdown's line break; "\*", "\_", "\." are escapes.
_HARD_BREAK = re.compile(r"\\+[ \t]*$", re.MULTILINE)
_ESCAPE = re.compile(r"\\([\\`*_{}\[\]()#+\-.!|>~])")
_BOLD = re.compile(r"(\*\*|__)(.+?)\1")


def tidy(text: str) -> str:
    """Text as written, without the Markdown a chatbot left in it: line-break backslashes,
    escapes and bold markers. Line breaks themselves are kept."""
    text = _HARD_BREAK.sub("", text)
    # Lines a parser already joined keep the break as "\\ " in the middle of the text.
    text = re.sub(r"\\+(?=\s)", "", text)
    text = _ESCAPE.sub(r"\1", text)
    text = _BOLD.sub(r"\2", text)
    return text.replace("**", "").strip()


# --- Recognising a multiple-choice question in text (imports, and questions already saved) ---

# Markdown that chatbots put around labels and letters: "**A)**", "__B.__", "- C) …", "> D) …".
_DECORATION = re.compile(r"^\s*(?:[-*•+>]\s+)?")
_EMPHASIS = re.compile(r"[*_`]{1,3}")
# "A) …", "a. …", "(A) …" at the start of a line.
_OPTION_LINE = re.compile(r"^\(?([A-Ha-h])[).]\s+(.+?)\s*$")
# Options written on one line: " A) … B) … C) …".
_INLINE_MARK = re.compile(r"(?:^|\s)\(?([A-H])[).]\s+")
_ANSWER_PREFIX = re.compile(
    r"^(?:la\s+)?(?:risposta\s+)?(?:corretta|giusta|esatta|correct(?:\s+answer)?|answer)\s*[:.\-]\s*",
    re.IGNORECASE,
)
_LETTERS_ONLY = re.compile(
    r"^\(?([A-Ha-h])\)?(?:\s*(?:,|;|/|&|\be\b|\band\b)\s*\(?([A-Ha-h])\)?)*\s*\.?$"
)
_LETTER_AND_TEXT = re.compile(r"^\(?([A-Ha-h])[).:]\s*(.+)$")


def _clean(line: str) -> str:
    return " ".join(_EMPHASIS.sub("", _DECORATION.sub("", tidy(line))).split())


def _comparable(text: str) -> str:
    return re.sub(r"[^\w]+", " ", text.lower()).strip()


def _options_by_line(lines: list[str]) -> tuple[list[str], dict[str, str]]:
    stem: list[str] = []
    options: dict[str, str] = {}
    for raw in lines:
        line = _clean(raw)
        if not line:
            continue
        match = _OPTION_LINE.match(line)
        if match and (options or stem) and match.group(1).upper() not in options:
            options[match.group(1).upper()] = match.group(2)
        elif options:
            last = list(options)[-1]  # a wrapped option continues the last one
            options[last] = f"{options[last]} {line}"
        else:
            stem.append(line)
    return stem, options


def _options_inline(text: str) -> tuple[list[str], dict[str, str]]:
    """ "Stem A) one B) two C) three": the markers must run A, B, C… in order."""
    marks = list(_INLINE_MARK.finditer(text))
    first = next((i for i, m in enumerate(marks) if m.group(1) == "A"), None)
    if first is None:
        return [text], {}
    chosen: list[re.Match[str]] = []
    for mark in marks[first:]:
        if mark.group(1) == LETTERS[len(chosen)]:
            chosen.append(mark)
    if len(chosen) < MIN_CHOICES:
        return [text], {}
    options = {}
    for index, mark in enumerate(chosen):
        end = chosen[index + 1].start() if index + 1 < len(chosen) else len(text)
        options[mark.group(1)] = text[mark.end() : end].strip()
    return [text[: chosen[0].start()].strip()], options


def _right_letters(answer: str, options: dict[str, str]) -> set[str] | None:
    text = _ANSWER_PREFIX.sub("", _clean(answer.split("\n")[0])).strip()
    if _LETTERS_ONLY.match(text):
        # A lowercase "e" between letters is Italian "and"; the option is a capital E.
        connectors = re.sub(r"(?<=\s)e(?=\s)|\band\b", " ", text)
        return {x.upper() for x in re.findall(r"(?<![A-Za-z])([A-Ha-h])(?![A-Za-z])", connectors)}
    match = _LETTER_AND_TEXT.match(text)
    if match:
        letter, rest = match.group(1).upper(), _comparable(match.group(2))
        option = _comparable(options.get(letter, ""))
        if option and (rest == option or rest.startswith(option) or option.startswith(rest)):
            return {letter}
    # The answer is the text of exactly one option.
    same = [letter for letter, text_ in options.items() if _comparable(text_) == _comparable(text)]
    return set(same) if len(same) == 1 else None


def detect(question: str | list[str], answer: str) -> tuple[str, list[dict[str, Any]]] | None:
    """The stem and the options when `question` lists options (A, B, C…) and `answer` names
    the right ones; None for a written-answer question."""
    lines = question if isinstance(question, list) else question.split("\n")
    stem, options = _options_by_line(lines)
    if len(options) < MIN_CHOICES:
        stem, options = _options_inline(" ".join(_clean(line) for line in lines))
    if not MIN_CHOICES <= len(options) <= MAX_CHOICES or list(options) != list(
        LETTERS[: len(options)]
    ):
        return None
    right = _right_letters(answer, options)
    if not right or not right <= set(options):
        return None
    made = [
        {"text": " ".join(text.split()), "correct": letter in right}
        for letter, text in options.items()
    ]
    if problem(made):
        return None
    stem_text = " ".join(" ".join(stem).split())
    return (stem_text, made) if stem_text else None


def convert_course(db: Session, user_id: uuid.UUID, course_id: uuid.UUID) -> int:
    """Turns the course's written-answer questions that are really multiple choice (options in
    the question, letters as the answer, as imported before options were recognised) into
    multiple-choice questions. Memory state and history are kept. Returns how many."""
    from app.models.course import Concept
    from app.services import managed_courses
    from app.services.courses.service import get_owned_course

    course = get_owned_course(db, user_id, course_id)
    managed_courses.ensure_editable(course)
    _tidy_course(db, course.id)
    converted = 0
    items = db.scalars(
        select(LearningItem).where(
            LearningItem.course_id == course.id, LearningItem.answer_format == "TEXT"
        )
    ).all()
    for item in items:
        if not item.questions:
            continue
        question = item.questions[0]
        found = detect(question.text, item.expected_knowledge)
        if found is None:
            continue
        stem, options = found
        concept = db.get(Concept, item.concept_id)
        # An imported concept is titled after its question, options included: the stem now.
        if concept is not None and concept.title.startswith(stem[:40]):
            concept.title = stem[:200]
        question.text = stem
        if item.title == item.objective or not item.title.strip():
            item.objective = stem[:2000]
        item.title = stem[:200]
        item.expected_knowledge = ""
        item.essential_points = []
        apply(item, options)
        converted += 1
    db.commit()
    return converted


def _tidy_course(db: Session, course_id: uuid.UUID) -> None:
    """Removes the Markdown a chatbot left in imported text (titles, questions, answers)."""
    from app.models.course import Chapter, Concept, Topic
    from app.models.learning import QuestionFormulation

    rows: list[Chapter | Topic | Concept] = [
        *db.scalars(select(Chapter).where(Chapter.course_id == course_id)),
        *db.scalars(select(Topic).where(Topic.course_id == course_id)),
        *db.scalars(select(Concept).where(Concept.course_id == course_id)),
    ]
    for row in rows:
        clean = tidy(row.title)
        if clean and clean != row.title:
            row.title = clean
    for item in db.scalars(select(LearningItem).where(LearningItem.course_id == course_id)):
        for name in ("title", "objective", "expected_knowledge"):
            value = getattr(item, name)
            clean = tidy(value) if value else value
            if clean != value and (clean or name != "title"):
                setattr(item, name, clean)
        points = [tidy(p) for p in item.essential_points]
        if points != list(item.essential_points):
            item.essential_points = [p for p in points if p]
    for question in db.scalars(
        select(QuestionFormulation).where(QuestionFormulation.course_id == course_id)
    ):
        clean = tidy(question.text)
        if clean and clean != question.text:
            question.text = clean
