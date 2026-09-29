"""CLEAN step (docs/PROJECT_SPEC.md §17): normalize extracted text without changing its meaning."""

import re
import unicodedata

# C0 controls except \t and \n, plus DEL. NUL in particular: PostgreSQL rejects it in text columns,
# and PDF extraction produces it regularly.
_CONTROL_CHARS = re.compile(r"[\x00-\x08\x0b-\x1f\x7f]")
# A word broken across lines by a hyphen ("inter-\nnazionale"), rejoined only when the next line
# starts lowercase — so "Rossi-\nBianchi" and "2019-\n2020" are left alone.
_HYPHENATED_BREAK = re.compile(r"(\w)-\n(?=[a-zà-öø-ÿ])")
# Typographic ligatures PDFs emit as single code points. Replaced explicitly rather than via NFKC,
# which would also rewrite meaningful characters (e.g. "x²" → "x2").
_LIGATURES = str.maketrans(
    {"ﬀ": "ff", "ﬁ": "fi", "ﬂ": "fl", "ﬃ": "ffi", "ﬄ": "ffl", "ﬅ": "st", "ﬆ": "st"}
)


def clean_text(text: str) -> str:
    text = unicodedata.normalize("NFC", text)
    text = text.replace("\r\n", "\n").replace("\r", "\n")
    text = text.replace("\u00ad", "")  # soft hyphen: invisible, splits words in search/AI input
    text = _CONTROL_CHARS.sub("", text)
    text = text.translate(_LIGATURES)
    text = _HYPHENATED_BREAK.sub(r"\1", text)
    # Line breaks inside a paragraph are layout (PDF/wrapped text), not meaning.
    return " ".join(text.split())
