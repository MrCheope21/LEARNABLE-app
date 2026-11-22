"""Multiple-choice questions (docs/MULTIPLE_CHOICE.md): an item with `choices` is answered by
picking options and graded by the server, without AI. One correct option: pick it. Several:
pick exactly those.

Stored on the item as [{"text": str, "correct": bool}, …]; `answer_format` is then "CHOICE" and
`expected_knowledge` names the correct options (so the reference answer, search and the
marketplace page read as for any other question).
"""

import re
from typing import Any

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


def grade(
    item: LearningItem, answer_text_value: str, evaluation: Evaluation, language: str
) -> Evaluation:
    """Fills in a deterministic evaluation from the stored answer text."""
    options = item.choices or []
    picked = {
        LETTERS.index(m.group(1))
        for m in re.finditer(r"^([A-H])\) ", answer_text_value, re.MULTILINE)
        if LETTERS.index(m.group(1)) < len(options)
    }
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
