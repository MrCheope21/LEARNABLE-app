"""CHUNK step (docs/PROJECT_SPEC.md §17, §18): group cleaned paragraphs into passages sized for
retrieval and AI prompts, without ever blurring where a passage came from.

A chunk never crosses a section boundary, and starts a new page's content in a new chunk, so
"View source" can name one heading and one page. The one exception is a sentence the layout broke
across a page ("...ai sensi dell'art. | 109, comma 4, ..."): extraction keeps it whole, and its
chunk records the page range (`page` to `page_end`).
"""

from collections.abc import Iterable
from dataclasses import dataclass

from app.services.documents.cleaning import clean_text
from app.services.documents.extraction import Block
from app.services.documents.sentences import split_sentences

MAX_CHUNK_CHARS = 1200
_PARAGRAPH_SEPARATOR = "\n\n"


@dataclass(frozen=True)
class Chunk:
    text: str
    page: int | None
    section: str | None
    paragraph_start: int
    paragraph_end: int
    # Last page the passage reaches, when it continues past `page`; otherwise None.
    page_end: int | None = None


def chunk_blocks(blocks: Iterable[Block], max_chars: int = MAX_CHUNK_CHARS) -> list[Chunk]:
    chunks: list[Chunk] = []
    parts: list[str] = []
    length = 0
    page: int | None = None
    last_page: int | None = None
    section: str | None = None
    first_paragraph = last_paragraph = 0

    def flush() -> None:
        nonlocal length
        if parts:
            chunks.append(
                Chunk(
                    _PARAGRAPH_SEPARATOR.join(parts),
                    page,
                    section,
                    first_paragraph,
                    last_paragraph,
                    page_end=last_page if last_page != page else None,
                )
            )
            parts.clear()
            length = 0

    paragraph = -1
    for block in blocks:
        text = clean_text(block.text)
        if block.is_heading:
            # Headings become the next chunks' `section`, not passage text.
            flush()
            continue
        if not text:
            continue
        paragraph += 1
        for piece in _split_long(text, max_chars):
            added = len(piece) + (len(_PARAGRAPH_SEPARATOR) if parts else 0)
            if parts and (
                block.page != page or block.heading != section or length + added > max_chars
            ):
                flush()
                added = len(piece)
            if not parts:
                page, section, first_paragraph = block.page, block.heading, paragraph
                last_page = block.page
            if block.page_end is not None and (last_page is None or block.page_end > last_page):
                last_page = block.page_end
            parts.append(piece)
            length += added
            last_paragraph = paragraph
    flush()
    return chunks


def _split_long(text: str, max_chars: int) -> list[str]:
    """Split an over-long paragraph at sentence ends, then at word boundaries if it must."""
    if len(text) <= max_chars:
        return [text]
    pieces: list[str] = []
    current = ""
    for sentence in split_sentences(text):
        for fragment in _split_words(sentence, max_chars):
            candidate = f"{current} {fragment}" if current else fragment
            if len(candidate) <= max_chars:
                current = candidate
            else:
                pieces.append(current)
                current = fragment
    if current:
        pieces.append(current)
    return pieces


def _split_words(sentence: str, max_chars: int) -> list[str]:
    if len(sentence) <= max_chars:
        return [sentence]
    fragments: list[str] = []
    current = ""
    for word in sentence.split(" "):
        while len(word) > max_chars:  # a single "word" longer than a chunk (URLs, garbage)
            if current:
                fragments.append(current)
                current = ""
            fragments.append(word[:max_chars])
            word = word[max_chars:]
        candidate = f"{current} {word}" if current else word
        if len(candidate) <= max_chars:
            current = candidate
        else:
            fragments.append(current)
            current = word
    if current:
        fragments.append(current)
    return fragments
