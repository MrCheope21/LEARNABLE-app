"""What extraction produces: paragraph-level blocks that remember where they came from."""

from dataclasses import dataclass, field
from datetime import datetime


@dataclass(frozen=True)
class Block:
    text: str
    # PDF page / PPTX slide number, 1-based.
    page: int | None = None
    # Heading in effect for this block (the section it belongs to).
    heading: str | None = None
    is_heading: bool = False
    # Last page, when the layout broke this paragraph across pages; otherwise None.
    page_end: int | None = None


# A paragraph that is only a picture: its text is this marker, the picture is
# Extraction.images[N]. Only question banks use pictures (a drawing as the expected answer).
IMAGE_MARKER = "\u27e6img:{}\u27e7"


@dataclass(frozen=True)
class Extraction:
    blocks: list[Block]
    page_count: int | None
    source_created_at: datetime | None
    # Pictures found in the document (DOCX), referenced by IMAGE_MARKER blocks.
    images: list[bytes] = field(default_factory=list)
