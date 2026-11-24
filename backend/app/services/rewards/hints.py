"""Cues for "Show hint" (docs/XP_AND_ACTIVITY.md §4). Pure.

A hint helps you retrieve the answer without giving it away. It has two parts, both taken from the
item's stored, source-grounded reference (never a new AI call, so it can't contradict the
reference and costs nothing):

- how many key points the answer should cover, and
- up to four key terms, one per key point: its longest word that the question doesn't already
  contain. Whole sentences are never shown.

When the reference is too short to cut cues from, there is no hint.
"""

import re
from dataclasses import dataclass

from app.services.documents.sentences import split_sentences

MAX_TERMS = 4
MIN_WORD_LETTERS = 5
MAX_HINT_CHARS = 300

_WORD = re.compile(rf"[^\W\d_]{{{MIN_WORD_LETTERS},}}")


@dataclass(frozen=True)
class Cues:
    point_count: int
    terms: list[str]

    @property
    def text(self) -> str:
        """The stored form of the hint: the terms, comma separated."""
        return ", ".join(self.terms)[:MAX_HINT_CHARS]


def _words(text: str) -> list[str]:
    return _WORD.findall(text)


def build_cues(
    essential_points: list[str], expected_knowledge: str, question_text: str = ""
) -> Cues | None:
    points = [p.strip() for p in essential_points if p.strip()]
    if not points:
        points = split_sentences(expected_knowledge)[:MAX_TERMS]
    if not points:
        return None
    asked = {w.lower() for w in _words(question_text)}
    terms: list[str] = []
    seen: set[str] = set()
    for point in points:
        candidates = [w for w in _words(point) if w.lower() not in asked and w.lower() not in seen]
        if not candidates:
            continue
        best = max(candidates, key=len)  # first of the longest
        seen.add(best.lower())
        terms.append(best.lower())
        if len(terms) == MAX_TERMS:
            break
    if not terms:
        return None
    return Cues(point_count=len(points), terms=terms)
