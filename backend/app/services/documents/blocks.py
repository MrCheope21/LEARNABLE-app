"""What extraction produces: paragraph-level blocks that remember where they came from."""

from dataclasses import dataclass
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


@dataclass(frozen=True)
class Extraction:
    blocks: list[Block]
    page_count: int | None
    source_created_at: datetime | None
