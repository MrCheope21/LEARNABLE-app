"""Sentence splitting that survives legal and academic prose.

A full stop is not always a sentence end: "art. 72", "D.Lgs. 209/2023", "Cass. nn. 450/2018",
"S.p.A.". Splitting there cuts passages and titles mid-thought. A boundary is accepted only when
the next word starts like a sentence (capital letter, possibly after an opening quote or
bracket) and the word before the punctuation isn't a known abbreviation or a lone initial.
"""

import re

# Lowercased, without the final dot: Italian legal references, then company forms and titles,
# then common English.
_ABBREVIATION_LIST = """
art artt co c lett n nn num d.lgs dlgs d.l d.p.r dpr d.m d.p.c.m l r.d c.c c.p c.p.c c.p.p
t.u t.u.i.r g.u cass sez sezz reg dir circ ris cfr cit op ss segg sgg par parr cap capp
pag pagg p pp vol voll tab fig figg es ecc etc rif

s.p.a s.r.l s.r.l.s s.a.p.a s.n.c s.a.s soc coop sig sigg sig.ra dott dott.ssa prof prof.ssa
avv ing geom rag spett egr gent

e.g i.e vs mr mrs ms dr inc ltd corp jr sr approx dept u.s u.k
"""
_ABBREVIATIONS = frozenset(_ABBREVIATION_LIST.split())

# End punctuation, then any closing quotes/brackets, then whitespace.
_CANDIDATE = re.compile(r"[.!?…]+[\"'»”’)\]]*\s+")  # noqa: RUF001 - typographic quotes are intended
_WORD_BEFORE = re.compile(r"([\w.]+)$")
_STARTS_SENTENCE = re.compile(r"[\"'«“‘(\[]?[A-ZÀ-ÖØ-Þ]")  # noqa: RUF001 - typographic quotes are intended


def split_sentences(text: str) -> list[str]:
    text = text.strip()
    if not text:
        return []
    sentences: list[str] = []
    start = 0
    for match in _CANDIDATE.finditer(text):
        end = match.end()
        if end >= len(text) or not _STARTS_SENTENCE.match(text, end):
            continue
        if _is_abbreviation(text[start : match.start() + 1]):
            continue
        sentences.append(text[start:end].strip())
        start = end
    tail = text[start:].strip()
    if tail:
        sentences.append(tail)
    return sentences


def _is_abbreviation(before_and_dot: str) -> bool:
    if not before_and_dot.endswith("."):
        return False  # "!" / "?" / "…" always end a sentence
    match = _WORD_BEFORE.search(before_and_dot[:-1])
    if match is None:
        return False
    word = match.group(1).lower().strip(".")
    # A lone letter is an initial ("A. Rossi", "L. 207/2024"), not a sentence end.
    return word in _ABBREVIATIONS or (len(word) == 1 and word.isalpha())
