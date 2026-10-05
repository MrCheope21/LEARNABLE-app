import uuid
from datetime import datetime

from sqlalchemy import Boolean, ForeignKey, Integer, String, Uuid, false
from sqlalchemy import Enum as SAEnum
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base
from app.db.types import UTCDateTime, utc_now
from app.models.enums import ItemGenerationStatus, StudyState

# Deletes cascade in the database (ON DELETE CASCADE + passive_deletes) rather than by the ORM
# loading every descendant row first — a large Course can own thousands of Concepts, and later
# many more Learning Items and reviews.


class Course(Base):
    """Highest-level user-owned learning environment (docs/PROJECT_SPEC.md §9). `user_id` is the
    ownership boundary every isolation check (§10) is built around."""

    __tablename__ = "courses"

    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=uuid.uuid4)
    user_id: Mapped[uuid.UUID] = mapped_column(
        Uuid, ForeignKey("users.id", ondelete="CASCADE"), index=True
    )
    title: Mapped[str] = mapped_column(String(200))
    description: Mapped[str] = mapped_column(String(2000), default="")
    language: Mapped[str] = mapped_column(String(10), default="en")
    # docs/PROJECT_SPEC.md §56: pausing a section excludes everything under it from review
    # without touching each Concept's own study state (see Concept.is_reviewable).
    paused: Mapped[bool] = mapped_column(Boolean, default=False, server_default=false())
    # Access to a marketplace course: its content is the author's (kept in sync with the listing,
    # read-only here); the study state, schedule and answers are this user's.
    marketplace_listing_id: Mapped[uuid.UUID | None] = mapped_column(
        # use_alter: listings point back at their source course (a cycle for create/drop_all).
        Uuid,
        ForeignKey("marketplace_listings.id", ondelete="SET NULL", use_alter=True),
        default=None,
        index=True,
    )
    marketplace_version: Mapped[int | None] = mapped_column(Integer, default=None)
    # Archived: put away. Hidden from the dashboard's main list, and paused (so out of reviews
    # and the planner) until restored. Nothing is deleted.
    archived_at: Mapped[datetime | None] = mapped_column(UTCDateTime, default=None)
    created_at: Mapped[datetime] = mapped_column(UTCDateTime, default=utc_now)
    updated_at: Mapped[datetime] = mapped_column(UTCDateTime, default=utc_now, onupdate=utc_now)

    settings: Mapped["CourseSettings"] = relationship(
        back_populates="course", uselist=False, cascade="all, delete-orphan", passive_deletes=True
    )
    chapters: Mapped[list["Chapter"]] = relationship(
        back_populates="course",
        cascade="all, delete-orphan",
        passive_deletes=True,
        order_by="Chapter.order",
    )


class CourseSettings(Base):
    __tablename__ = "course_settings"

    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=uuid.uuid4)
    course_id: Mapped[uuid.UUID] = mapped_column(
        Uuid, ForeignKey("courses.id", ondelete="CASCADE"), unique=True
    )
    scheduling_policy: Mapped[str] = mapped_column(String(50), default="chessable_v1")
    external_knowledge_mode: Mapped[bool] = mapped_column(Boolean, default=False)
    audio_retention: Mapped[str] = mapped_column(String(20), default="none")

    course: Mapped["Course"] = relationship(back_populates="settings")


class Chapter(Base):
    __tablename__ = "chapters"

    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=uuid.uuid4)
    course_id: Mapped[uuid.UUID] = mapped_column(
        Uuid, ForeignKey("courses.id", ondelete="CASCADE"), index=True
    )
    # Marketplace copies: the id of the author's row this one mirrors (sync key).
    origin_key: Mapped[str | None] = mapped_column(String(32), default=None)
    title: Mapped[str] = mapped_column(String(200))
    description: Mapped[str] = mapped_column(String(2000), default="")
    order: Mapped[int] = mapped_column(Integer, default=0)
    # docs/PROJECT_SPEC.md §56: pausing a section excludes everything under it from review
    # without touching each Concept's own study state (see Concept.is_reviewable).
    paused: Mapped[bool] = mapped_column(Boolean, default=False, server_default=false())
    created_at: Mapped[datetime] = mapped_column(UTCDateTime, default=utc_now)
    updated_at: Mapped[datetime] = mapped_column(UTCDateTime, default=utc_now, onupdate=utc_now)

    course: Mapped["Course"] = relationship(back_populates="chapters")
    topics: Mapped[list["Topic"]] = relationship(
        back_populates="chapter",
        cascade="all, delete-orphan",
        passive_deletes=True,
        order_by="Topic.order",
    )


class Topic(Base):
    __tablename__ = "topics"

    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=uuid.uuid4)
    chapter_id: Mapped[uuid.UUID] = mapped_column(
        Uuid, ForeignKey("chapters.id", ondelete="CASCADE"), index=True
    )
    # Denormalized so course-scoped isolation checks are a single WHERE clause, not a join
    # through Chapter (docs/DATA_MODEL.md). Must be rewritten if a Topic ever moves Chapters.
    course_id: Mapped[uuid.UUID] = mapped_column(
        Uuid, ForeignKey("courses.id", ondelete="CASCADE"), index=True
    )
    # Marketplace copies: the id of the author's row this one mirrors (sync key).
    origin_key: Mapped[str | None] = mapped_column(String(32), default=None)
    title: Mapped[str] = mapped_column(String(200))
    description: Mapped[str] = mapped_column(String(2000), default="")
    order: Mapped[int] = mapped_column(Integer, default=0)
    # docs/PROJECT_SPEC.md §56: pausing a section excludes everything under it from review
    # without touching each Concept's own study state (see Concept.is_reviewable).
    paused: Mapped[bool] = mapped_column(Boolean, default=False, server_default=false())
    created_at: Mapped[datetime] = mapped_column(UTCDateTime, default=utc_now)
    updated_at: Mapped[datetime] = mapped_column(UTCDateTime, default=utc_now, onupdate=utc_now)

    chapter: Mapped["Chapter"] = relationship(back_populates="topics")
    concepts: Mapped[list["Concept"]] = relationship(
        back_populates="topic",
        cascade="all, delete-orphan",
        passive_deletes=True,
        order_by="[Concept.order, Concept.created_at]",
    )


class Concept(Base):
    """Basic conceptual knowledge unit — NOT equal to one flashcard (docs/PROJECT_SPEC.md §15).
    Carries no SRS state of its own; that belongs to LearningItem (Phase 8)."""

    __tablename__ = "concepts"

    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=uuid.uuid4)
    topic_id: Mapped[uuid.UUID] = mapped_column(
        Uuid, ForeignKey("topics.id", ondelete="CASCADE"), index=True
    )
    # Denormalized, matching the pattern LearningItem will use (docs/DATA_MODEL.md §25). Must be
    # rewritten if a Concept ever moves Topics.
    chapter_id: Mapped[uuid.UUID] = mapped_column(
        Uuid, ForeignKey("chapters.id", ondelete="CASCADE"), index=True
    )
    course_id: Mapped[uuid.UUID] = mapped_column(
        Uuid, ForeignKey("courses.id", ondelete="CASCADE"), index=True
    )
    # Marketplace copies: the id of the author's row this one mirrors (sync key).
    origin_key: Mapped[str | None] = mapped_column(String(32), default=None)
    title: Mapped[str] = mapped_column(String(200))
    description: Mapped[str] = mapped_column(String(2000), default="")
    # Position within the Topic, like Chapter/Topic `order`; ties fall back to creation time.
    order: Mapped[int] = mapped_column(Integer, default=0, server_default="0")
    # Stored as VARCHAR + CHECK rather than a native Postgres ENUM: adding a state later is then a
    # plain migration instead of ALTER TYPE, which can't run inside a transaction.
    study_state: Mapped[StudyState] = mapped_column(
        SAEnum(
            StudyState,
            name="study_state",
            native_enum=False,
            create_constraint=True,
            length=20,
            validate_strings=True,
        ),
        default=StudyState.NOT_STUDIED,
    )
    # Set when the material this Concept came from was deleted and it has no source left, so the
    # user can decide to keep, edit or delete it. Cleared when a source is linked again.
    needs_source_review: Mapped[bool] = mapped_column(
        Boolean, default=False, server_default=false()
    )
    # Learning Item generation (Phase 8): started on activation or on request, runs in the
    # background. The error is user-safe, never source content.
    item_generation_status: Mapped[ItemGenerationStatus] = mapped_column(
        SAEnum(
            ItemGenerationStatus,
            name="item_generation_status",
            native_enum=False,
            create_constraint=True,
            length=30,
            validate_strings=True,
        ),
        default=ItemGenerationStatus.NONE,
        server_default=ItemGenerationStatus.NONE.value,
    )
    item_generation_error: Mapped[str | None] = mapped_column(String(500), default=None)
    item_generation_started_at: Mapped[datetime | None] = mapped_column(UTCDateTime, default=None)
    created_at: Mapped[datetime] = mapped_column(UTCDateTime, default=utc_now)
    updated_at: Mapped[datetime] = mapped_column(UTCDateTime, default=utc_now, onupdate=utc_now)

    topic: Mapped["Topic"] = relationship(back_populates="concepts")

    @property
    def is_reviewable(self) -> bool:
        """Whether this Concept may enter normal review (docs/PROJECT_SPEC.md §21, §50):
        ACTIVE, and not inside a paused Topic, Chapter or Course."""
        topic = self.topic
        chapter = topic.chapter
        return self.study_state == StudyState.ACTIVE and not (
            topic.paused or chapter.paused or chapter.course.paused
        )
