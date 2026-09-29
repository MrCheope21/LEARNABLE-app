from uuid import UUID

from pydantic import BaseModel, ConfigDict

from app.models.enums import DocumentKind, DocumentPurpose, DocumentStatus
from app.schemas.common import InputModel, UTCTimestamp


class DocumentRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    course_id: UUID
    # The Chapter this material is filed under; null when unassigned.
    chapter_id: UUID | None
    filename: str
    mime_type: str
    kind: DocumentKind
    # MATERIAL feeds curriculum generation; QUESTION_BANK was imported as the user's own Q&A.
    purpose: DocumentPurpose
    size_bytes: int
    sha256: str
    status: DocumentStatus
    # Why processing FAILED, safe to show the user.
    error_message: str | None
    # A note about a READY import (e.g. questions skipped for lacking an answer).
    import_notice: str | None
    page_count: int | None
    chunk_count: int
    # Creation date from the file's own metadata, when present.
    source_created_at: UTCTimestamp | None
    # When a curriculum covering the whole document was applied; null = not analyzed yet.
    analyzed_at: UTCTimestamp | None
    # Import date.
    created_at: UTCTimestamp
    updated_at: UTCTimestamp


class DocumentUpdate(InputModel):
    """Files the document under a Chapter of the same Course, or unassigns it (null). Moving it
    marks it not analyzed, so its material is analyzed again in its new Chapter."""

    chapter_id: UUID | None


class ChunkRead(BaseModel):
    """A source passage for "View source" (docs/PROJECT_SPEC.md §66)."""

    model_config = ConfigDict(from_attributes=True)

    id: UUID
    document_id: UUID
    position: int
    page_number: int | None
    # Set when the passage continues onto later pages ("p. 8-9").
    page_end: int | None
    section: str | None
    paragraph_start: int
    paragraph_end: int
    text: str
