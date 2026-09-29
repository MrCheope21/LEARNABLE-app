import uuid
from datetime import datetime
from typing import Any

from sqlalchemy import JSON, ForeignKey, Integer, String, UniqueConstraint, Uuid
from sqlalchemy import Enum as SAEnum
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base
from app.db.types import UTCDateTime, utc_now
from app.models.enums import CurriculumProposalStatus


class CurriculumProposal(Base):
    """An AI-proposed Chapter → Topic → Concept structure for a Course, held for the user to
    review (docs/PROJECT_SPEC.md §20). Proposals never touch the Course hierarchy until applied,
    and applying never activates anything (§21)."""

    __tablename__ = "curriculum_proposals"

    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=uuid.uuid4)
    course_id: Mapped[uuid.UUID] = mapped_column(
        Uuid, ForeignKey("courses.id", ondelete="CASCADE"), index=True
    )
    # Set: a Chapter-scoped proposal (Topics → Concepts for that Chapter, merged with what it
    # already has). Null: a Course-scoped proposal (Chapters → Topics → Concepts).
    chapter_id: Mapped[uuid.UUID | None] = mapped_column(
        Uuid, ForeignKey("chapters.id", ondelete="CASCADE"), index=True, default=None
    )
    # Documents whose every passage was sent; applying marks them analyzed.
    document_ids: Mapped[list[str] | None] = mapped_column(JSON, default=None)
    # VARCHAR + CHECK like study_state, so adding a status later is a plain migration.
    status: Mapped[CurriculumProposalStatus] = mapped_column(
        SAEnum(
            CurriculumProposalStatus,
            name="curriculum_proposal_status",
            native_enum=False,
            create_constraint=True,
            length=30,
            validate_strings=True,
        ),
        default=CurriculumProposalStatus.GENERATING,
    )
    # User-safe explanation for FAILED / INSUFFICIENT_CONTEXT; never contains source content.
    error_message: Mapped[str | None] = mapped_column(String(500), default=None)
    # {"chapters": [...]} or {"topics": [...]}, source chunk ids as strings; see
    # app/services/curriculum.
    content: Mapped[dict[str, Any] | None] = mapped_column(JSON, default=None)
    # Passages sent to the model, out of those available. Fewer means the material exceeded
    # AI_MAX_CONTEXT_CHARS and the proposal covers only its beginning.
    passages_used: Mapped[int] = mapped_column(Integer, default=0)
    passages_total: Mapped[int] = mapped_column(Integer, default=0)
    # Proposed Concepts removed because they cited no passage that was actually sent (§19).
    dropped_concepts: Mapped[int] = mapped_column(Integer, default=0)
    # What produced it (spec §73, §74). Null until generation finishes.
    ai_provider: Mapped[str | None] = mapped_column(String(50), default=None)
    ai_model: Mapped[str | None] = mapped_column(String(200), default=None)
    ai_model_version: Mapped[str | None] = mapped_column(String(200), default=None)
    prompt_version: Mapped[str | None] = mapped_column(String(100), default=None)
    created_at: Mapped[datetime] = mapped_column(UTCDateTime, default=utc_now)
    updated_at: Mapped[datetime] = mapped_column(UTCDateTime, default=utc_now, onupdate=utc_now)
    applied_at: Mapped[datetime | None] = mapped_column(UTCDateTime, default=None)


class ConceptSource(Base):
    """Links a Concept to the source passages it was derived from, for "View source"
    (docs/PROJECT_SPEC.md §18, §66). Deleting the document removes the link, not the Concept."""

    __tablename__ = "concept_sources"
    __table_args__ = (UniqueConstraint("concept_id", "chunk_id"),)

    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=uuid.uuid4)
    concept_id: Mapped[uuid.UUID] = mapped_column(
        Uuid, ForeignKey("concepts.id", ondelete="CASCADE"), index=True
    )
    chunk_id: Mapped[uuid.UUID] = mapped_column(
        Uuid, ForeignKey("document_chunks.id", ondelete="CASCADE"), index=True
    )
    # Denormalized like every Course-scoped table, so isolation is one WHERE clause.
    course_id: Mapped[uuid.UUID] = mapped_column(
        Uuid, ForeignKey("courses.id", ondelete="CASCADE"), index=True
    )
    created_at: Mapped[datetime] = mapped_column(UTCDateTime, default=utc_now)
