import uuid
from datetime import datetime

from sqlalchemy import Enum as SAEnum
from sqlalchemy import ForeignKey, Index, Integer, String, Text, UniqueConstraint, Uuid
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base
from app.db.types import UTCDateTime, utc_now
from app.models.enums import DocumentKind, DocumentPurpose, DocumentStatus


def _enum(
    enum_cls: type[DocumentKind] | type[DocumentStatus] | type[DocumentPurpose], name: str
) -> SAEnum:
    # VARCHAR + CHECK like study_state, so adding a value later is a plain migration.
    return SAEnum(
        enum_cls,
        name=name,
        native_enum=False,
        create_constraint=True,
        length=20,
        validate_strings=True,
    )


class Document(Base):
    """A file in a Course's private Knowledge Repository (docs/PROJECT_SPEC.md §16)."""

    __tablename__ = "documents"
    # Deduplication is per Course only: the same file in two Courses is two documents, and a
    # duplicate check must never reveal what another Course (or user) contains.
    __table_args__ = (UniqueConstraint("course_id", "sha256"),)

    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=uuid.uuid4)
    course_id: Mapped[uuid.UUID] = mapped_column(
        Uuid, ForeignKey("courses.id", ondelete="CASCADE"), index=True
    )
    # The Chapter this material belongs to, when the user organizes material by Chapter. Deleting
    # the Chapter keeps the document (nothing uploaded disappears silently); it becomes
    # unassigned.
    chapter_id: Mapped[uuid.UUID | None] = mapped_column(
        Uuid, ForeignKey("chapters.id", ondelete="SET NULL"), index=True, default=None
    )
    # When a curriculum proposal covering this whole document was applied. Unanalyzed documents
    # are what the next generation looks at by default, so new material is analyzed on its own.
    analyzed_at: Mapped[datetime | None] = mapped_column(UTCDateTime, default=None)
    # The user's original name, kept as metadata only; the file is stored under storage_key.
    filename: Mapped[str] = mapped_column(String(255))
    # Derived from the file's content, never from what the client claimed.
    mime_type: Mapped[str] = mapped_column(String(100))
    kind: Mapped[DocumentKind] = mapped_column(_enum(DocumentKind, "document_kind"))
    # Question banks are imported directly and never feed curriculum generation.
    purpose: Mapped[DocumentPurpose] = mapped_column(
        _enum(DocumentPurpose, "document_purpose"),
        default=DocumentPurpose.MATERIAL,
        server_default=DocumentPurpose.MATERIAL.value,
    )
    size_bytes: Mapped[int] = mapped_column(Integer)
    sha256: Mapped[str] = mapped_column(String(64))
    storage_key: Mapped[str] = mapped_column(String(500))
    status: Mapped[DocumentStatus] = mapped_column(
        _enum(DocumentStatus, "document_status"), default=DocumentStatus.PROCESSING
    )
    # User-safe explanation when status is FAILED; never contains document content.
    error_message: Mapped[str | None] = mapped_column(String(500), default=None)
    # User-safe note about a READY import, e.g. question-bank questions skipped for lacking an
    # answer. Never contains document content.
    import_notice: Mapped[str | None] = mapped_column(String(500), default=None)
    page_count: Mapped[int | None] = mapped_column(Integer, default=None)
    chunk_count: Mapped[int] = mapped_column(Integer, default=0)
    # "Creation date" from the file's own metadata, when it has one; created_at is the import date.
    source_created_at: Mapped[datetime | None] = mapped_column(UTCDateTime, default=None)
    created_at: Mapped[datetime] = mapped_column(UTCDateTime, default=utc_now)
    updated_at: Mapped[datetime] = mapped_column(UTCDateTime, default=utc_now, onupdate=utc_now)

    chunks: Mapped[list["DocumentChunk"]] = relationship(
        back_populates="document",
        cascade="all, delete-orphan",
        passive_deletes=True,
        order_by="DocumentChunk.position",
    )


class DocumentChunk(Base):
    """A passage of cleaned text with its exact origin, so any generated question can answer
    "where did this come from?" (docs/PROJECT_SPEC.md §17, §18, §66)."""

    __tablename__ = "document_chunks"
    __table_args__ = (Index("ix_document_chunks_document_id_position", "document_id", "position"),)

    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=uuid.uuid4)
    document_id: Mapped[uuid.UUID] = mapped_column(
        Uuid, ForeignKey("documents.id", ondelete="CASCADE")
    )
    # Denormalized so Course-scoped retrieval (spec §72) is a single WHERE, never a join that
    # could forget the scope.
    course_id: Mapped[uuid.UUID] = mapped_column(
        Uuid, ForeignKey("courses.id", ondelete="CASCADE"), index=True
    )
    # Order within the document, from 0.
    position: Mapped[int] = mapped_column(Integer)
    # PDF page or PPTX slide number (1-based); None for formats without pages.
    page_number: Mapped[int | None] = mapped_column(Integer, default=None)
    # Last page when a sentence broken across pages is kept whole ("p. 8-9"); else None.
    page_end: Mapped[int | None] = mapped_column(Integer, default=None)
    # Nearest heading / bookmark / slide title above this passage.
    section: Mapped[str | None] = mapped_column(String(500), default=None)
    # Paragraph range within the document (0-based, inclusive), for "source position".
    paragraph_start: Mapped[int] = mapped_column(Integer)
    paragraph_end: Mapped[int] = mapped_column(Integer)
    text: Mapped[str] = mapped_column(Text)

    document: Mapped["Document"] = relationship(back_populates="chunks")
