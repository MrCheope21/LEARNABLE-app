"""The course marketplace: courses their authors publish, and who has access to them.

A listing holds a snapshot of the course's study content (structure, learning items, questions,
priorities, reference drawings), never the author's uploaded files, answers or progress. Each
republish is a new version. Acquiring gives lasting access: a course in the acquirer's account
that mirrors the listing (read-only, synced on every republish) while their study is their own.
"""

import uuid
from datetime import datetime
from typing import Any

from sqlalchemy import JSON, ForeignKey, Index, Integer, String, Text, UniqueConstraint, Uuid
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base
from app.db.types import UTCDateTime, utc_now


class MarketplaceListing(Base):
    __tablename__ = "marketplace_listings"
    __table_args__ = (
        Index("ix_marketplace_listings_status_published_at", "status", "published_at"),
        Index("ix_marketplace_listings_status_category", "status", "category"),
    )

    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=uuid.uuid4)
    author_id: Mapped[uuid.UUID] = mapped_column(
        Uuid, ForeignKey("users.id", ondelete="CASCADE"), index=True
    )
    # One listing per course; it survives the course's deletion (access already given stays,
    # at the last published version).
    source_course_id: Mapped[uuid.UUID | None] = mapped_column(
        Uuid, ForeignKey("courses.id", ondelete="SET NULL"), unique=True, default=None
    )
    title: Mapped[str] = mapped_column(String(200))
    # The sales page (schemas.marketplace.ListingInfo).
    subtitle: Mapped[str] = mapped_column(String(200), default="", server_default="")
    description: Mapped[str] = mapped_column(Text, default="")
    outcomes: Mapped[list[str]] = mapped_column(JSON, default=list)
    audience: Mapped[str] = mapped_column(Text, default="")
    level: Mapped[str] = mapped_column(String(16), default="all", server_default="all")
    # schemas.marketplace.Category.
    category: Mapped[str] = mapped_column(String(32), default="other", server_default="other")
    language: Mapped[str] = mapped_column(String(16))
    tags: Mapped[list[str]] = mapped_column(JSON, default=list)
    # DRAFT: the sales page only, never published (version 0, empty snapshot). PUBLISHED: shown
    # and acquirable. UNPUBLISHED: hidden; whoever has access keeps it.
    status: Mapped[str] = mapped_column(String(16), default="DRAFT")
    # Paid listings come later; for now every listing is free (0).
    price_cents: Mapped[int] = mapped_column(Integer, default=0, server_default="0")
    currency: Mapped[str] = mapped_column(String(3), default="EUR", server_default="EUR")
    version: Mapped[int] = mapped_column(Integer, default=1)
    snapshot: Mapped[dict[str, Any]] = mapped_column(JSON)
    chapter_count: Mapped[int] = mapped_column(Integer, default=0)
    item_count: Mapped[int] = mapped_column(Integer, default=0)
    acquisition_count: Mapped[int] = mapped_column(Integer, default=0, server_default="0")
    # First publication.
    published_at: Mapped[datetime | None] = mapped_column(UTCDateTime, default=None)
    updated_at: Mapped[datetime] = mapped_column(UTCDateTime, default=utc_now, onupdate=utc_now)


class MarketplaceAcquisition(Base):
    """Access to a listing, once per user and for good: it outlives the course in their account
    (deleting it and adding it back is free) and later versions."""

    __tablename__ = "marketplace_acquisitions"
    __table_args__ = (UniqueConstraint("listing_id", "user_id"),)

    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=uuid.uuid4)
    listing_id: Mapped[uuid.UUID] = mapped_column(
        Uuid, ForeignKey("marketplace_listings.id", ondelete="CASCADE"), index=True
    )
    user_id: Mapped[uuid.UUID] = mapped_column(
        Uuid, ForeignKey("users.id", ondelete="CASCADE"), index=True
    )
    # The version current when access was given.
    version: Mapped[int] = mapped_column(Integer)
    # The course in the acquirer's account; null while they have removed it.
    course_id: Mapped[uuid.UUID | None] = mapped_column(
        Uuid, ForeignKey("courses.id", ondelete="SET NULL"), default=None
    )
    price_cents: Mapped[int] = mapped_column(Integer, default=0)
    acquired_at: Mapped[datetime] = mapped_column(UTCDateTime, default=utc_now)
