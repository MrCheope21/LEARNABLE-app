"""Layout-aware PDF reading: recover headings and paragraphs from font sizes and line spacing.

Plain PDF text extraction flattens a page into one run of lines, so headings merge into the
prose and paragraph breaks disappear. Most study material (exported from Word or LaTeX) has
reliable layout signals instead: headings are set in a larger font, and paragraphs are
separated by a larger vertical gap than the lines within them. This module turns those signals
into blocks:

- body size = the font size carrying most of the text; a line clearly larger is a heading
  (consecutive heading lines of one size are one wrapped heading);
- a gap well above the typical line spacing starts a new paragraph;
- text repeated in the top/bottom margins on most pages (running headers, "Page 3") is dropped;
- a paragraph the page break cut mid-sentence is joined with its continuation on the next page.

Lines keep their "\\n" separators, so cleaning can still rejoin words hyphenated at a line end.
"""

import hashlib
import re
from collections import Counter
from collections.abc import Callable
from dataclasses import dataclass, replace
from io import BytesIO
from itertools import pairwise
from statistics import median
from typing import Any

import pdfplumber

from app.services.documents.blocks import IMAGE_MARKER, Block

# A line this much larger than the body text is a heading.
_HEADING_RATIO = 1.12
# Headings are short; a long "large" line is more likely a pull quote or a title page.
_MAX_HEADING_CHARS = 250
# A vertical gap this many times the typical line spacing starts a new paragraph.
_PARAGRAPH_GAP_RATIO = 1.8
# Share of the page height, at top and bottom, where running headers and footers live.
_MARGIN = 0.08
_MIN_PAGES_FOR_RUNNING_TEXT = 3

_DIGITS = re.compile(r"\d+")
_ENDS_SENTENCE = re.compile(r"[.!?…:;][\"'»”’)\]]*$")  # noqa: RUF001 - typographic quotes are intended
_CONTINUES = re.compile(r"[a-zà-öø-ÿ0-9,;:)\]]")


@dataclass(frozen=True)
class Line:
    text: str
    top: float
    bottom: float
    size: float


@dataclass(frozen=True)
class Page:
    number: int  # 1-based
    height: float
    # None when this page couldn't be read with layout; the caller falls back to plain text.
    lines: list[Line] | None


# Pictures smaller than this (points, either side) are icons or bullets, not content.
_MIN_PICTURE = 60
# A picture on this many pages or more is a logo or a decoration.
_REPEATED_PICTURE = 3
_PICTURE_DPI = 150
_MAX_PICTURE_BYTES = 2_500_000


def _pictures(page: Any) -> list[tuple[float, float, bytes]]:
    """The page's pictures as (top, bottom, PNG bytes), cut out of the rendered page."""
    found = []
    for image in page.images:
        x0, top, x1, bottom = (float(image[k]) for k in ("x0", "top", "x1", "bottom"))
        if x1 - x0 < _MIN_PICTURE or bottom - top < _MIN_PICTURE:
            continue
        box = (
            max(0.0, x0),
            max(0.0, top),
            min(float(page.width), x1),
            min(float(page.height), bottom),
        )
        try:
            rendered = page.crop(box).to_image(resolution=_PICTURE_DPI).original
            out = BytesIO()
            rendered.save(out, format="PNG", optimize=True)
            if out.tell() > _MAX_PICTURE_BYTES:
                # A photo-like picture: as JPEG it fits the 3 MB a question picture may take.
                out = BytesIO()
                rendered.convert("RGB").save(out, format="JPEG", quality=85)
        except Exception:  # noqa: S112 - a picture that won't render is simply left out
            continue
        found.append((top, bottom, out.getvalue()))
    return found


def read_pages(data: bytes, images: list[bytes] | None = None) -> list[Page] | None:
    """Lines with their dominant font size, per page. None if the file can't be opened this way
    (the caller then falls back to plain text extraction). With `images`, the page's pictures
    are appended to it and placed among the lines as IMAGE_MARKER lines (question banks)."""
    try:
        pdf = pdfplumber.open(BytesIO(data), password="")
    except Exception:
        return None
    pages: list[Page] = []
    pictures: dict[int, list[tuple[float, float, bytes]]] = {}
    with pdf:
        for number, page in enumerate(pdf.pages, start=1):
            try:
                raw = page.extract_text_lines(return_chars=True, strip=True)
            except Exception:
                pages.append(Page(number, float(page.height), None))
                continue
            lines = []
            for entry in raw:
                text = str(entry["text"]).strip()
                sizes = Counter(
                    round(float(char["size"]), 1)
                    for char in entry["chars"]
                    if str(char["text"]).strip()
                )
                if text and sizes:
                    lines.append(
                        Line(
                            text,
                            float(entry["top"]),
                            float(entry["bottom"]),
                            sizes.most_common(1)[0][0],
                        )
                    )
            if images is not None:
                pictures[number] = _pictures(page)
            pages.append(Page(number, float(page.height), lines))
    if images is not None and pictures:
        seen = Counter(
            hashlib.sha256(png).hexdigest() for found in pictures.values() for *_, png in found
        )
        for page_ in pages:
            if page_.lines is None:
                continue
            for top, bottom, png in pictures.get(page_.number, []):
                if seen[hashlib.sha256(png).hexdigest()] >= _REPEATED_PICTURE:
                    continue
                images.append(png)
                page_.lines.append(Line(IMAGE_MARKER.format(len(images) - 1), top, bottom, 0.0))
            page_.lines.sort(key=lambda line: line.top)
    return pages


def build_blocks(pages: list[Page], plain_text: Callable[[int], list[str]]) -> list[Block]:
    """`plain_text(page_number)` gives fallback paragraphs for a page layout couldn't read."""
    readable = [line for page in pages if page.lines for line in page.lines]
    if not readable:
        # Nothing readable with layout (e.g. a scan): let the fallback decide per page.
        return [Block(text, page=page.number) for page in pages for text in plain_text(page.number)]

    body_size = _body_size(readable)
    running = _running_text(pages)
    paragraph_gap = _paragraph_gap(pages, body_size)

    blocks: list[Block] = []
    heading: str | None = None
    for page in pages:
        if page.lines is None:
            blocks.extend(
                Block(text, page=page.number, heading=heading) for text in plain_text(page.number)
            )
            continue
        lines = [line for line in page.lines if not _is_running(line, page, running)]
        for group, is_heading in _group_lines(lines, body_size, paragraph_gap):
            if is_heading:
                heading = " ".join(line.text for line in group)[:500]
                blocks.append(Block(heading, page=page.number, heading=heading, is_heading=True))
            else:
                text = "\n".join(line.text for line in group)
                blocks.append(Block(text, page=page.number, heading=heading))
    return _join_page_breaks(blocks)


def _group_lines(
    lines: list[Line], body_size: float, paragraph_gap: float
) -> list[tuple[list[Line], bool]]:
    """Consecutive lines → (lines, is_heading) groups: a paragraph, or one (possibly wrapped)
    heading. A new group starts at a large gap or when body/heading or heading size changes."""
    groups: list[tuple[list[Line], bool]] = []
    for line in lines:
        is_heading = (
            line.size >= body_size * _HEADING_RATIO and len(line.text) <= _MAX_HEADING_CHARS
        )
        if groups:
            group, group_is_heading = groups[-1]
            last = group[-1]
            continues = (
                is_heading == group_is_heading
                and (not is_heading or line.size == last.size)
                and line.top - last.bottom <= paragraph_gap
            )
            if continues:
                group.append(line)
                continue
        groups.append(([line], is_heading))
    return groups


def _body_size(lines: list[Line]) -> float:
    weight: Counter[float] = Counter()
    for line in lines:
        if line.size > 0:  # picture markers have no font size
            weight[line.size] += len(line.text)
    return weight.most_common(1)[0][0]


def _paragraph_gap(pages: list[Page], body_size: float) -> float:
    gaps: list[float] = []
    for page in pages:
        body = [line for line in page.lines or [] if line.size < body_size * _HEADING_RATIO]
        gaps.extend(b.top - a.bottom for a, b in pairwise(body) if b.top > a.bottom)
    if not gaps:
        return body_size * 0.6
    return float(median(gaps)) * _PARAGRAPH_GAP_RATIO


def _margin_key(text: str) -> str:
    return _DIGITS.sub("#", text.lower())


def _in_margin(line: Line, page: Page) -> bool:
    return line.top < page.height * _MARGIN or line.bottom > page.height * (1 - _MARGIN)


def _running_text(pages: list[Page]) -> set[str]:
    """Margin text repeated on at least half of the pages (headers, footers, page numbers)."""
    readable = [page for page in pages if page.lines is not None]
    if len(readable) < _MIN_PAGES_FOR_RUNNING_TEXT:
        return set()
    seen: Counter[str] = Counter()
    for page in readable:
        keys = {_margin_key(line.text) for line in page.lines or [] if _in_margin(line, page)}
        seen.update(keys)
    return {key for key, count in seen.items() if count >= len(readable) / 2}


def _is_running(line: Line, page: Page, running: set[str]) -> bool:
    return bool(running) and _in_margin(line, page) and _margin_key(line.text) in running


def _join_page_breaks(blocks: list[Block]) -> list[Block]:
    """Rejoin a paragraph the page break cut mid-sentence: the last paragraph of a page that
    doesn't end a sentence, or whose continuation starts lowercase / with a digit ("...ai sensi
    dell'art. | 109, comma 4"), continues in the first paragraph of the next page."""
    joined: list[Block] = []
    for block in blocks:
        previous = joined[-1] if joined else None
        if (
            previous is not None
            and not previous.is_heading
            and not block.is_heading
            and previous.page is not None
            and block.page == (previous.page_end or previous.page) + 1
            and _continues_across(previous.text, block.text)
        ):
            joined[-1] = replace(
                previous,
                text=f"{previous.text}\n{block.text}",
                page_end=block.page_end or block.page,
            )
        else:
            joined.append(block)
    return joined


def _continues_across(before: str, after: str) -> bool:
    after = after.lstrip()
    if after and _CONTINUES.match(after):
        return True
    return not _ENDS_SENTENCE.search(before.rstrip())
