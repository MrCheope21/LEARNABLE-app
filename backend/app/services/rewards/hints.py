"""Retrieval cues for "Show hint" (docs/XP_AND_ACTIVITY.md §4). Pure.

A hint is the opening word(s) of the item's first key point (about a third of it, 1-6 words),
or of its reference answer when it has no key points: a nudge taken from the stored,
source-grounded reference, never from a new AI call, so it can't contradict the reference
answer and costs nothing. When the reference is too short to cut a cue from without giving the
answer away, there is no hint.
"""

import re

from app.services.documents.sentences import split_sentences

MAX_CUE_WORDS = 6
MIN_CUE_WORDS = 1
# The cue is at most this share of the words in the source sentence…
CUE_SHARE = 0.34
# …and must leave most of the whole reference unsaid.
MAX_SHARE_OF_REFERENCE = 0.5
MIN_SOURCE_WORDS = 2
MAX_HINT_CHARS = 300

_TRAILING = re.compile(r"[\s,;:.\u00b7\u2013\u2014-]+$")


def build_hint(essential_points: list[str], expected_knowledge: str) -> str | None:
    source = next((p.strip() for p in essential_points if p.strip()), "")
    if not source:
        sentences = split_sentences(expected_knowledge)
        source = sentences[0] if sentences else ""
    words = source.split()
    if len(words) < MIN_SOURCE_WORDS:
        return None
    take = max(MIN_CUE_WORDS, min(MAX_CUE_WORDS, int(len(words) * CUE_SHARE)))
    reference_words = len(expected_knowledge.split()) or len(words)
    if take > reference_words * MAX_SHARE_OF_REFERENCE:
        return None
    cue = _TRAILING.sub("", " ".join(words[:take]))
    if not cue:
        return None
    return f"{cue}…"[:MAX_HINT_CHARS]
