"""The course marketplace: courses their authors publish, and who has access to them.

A listing holds a snapshot of the course's study content (structure, learning items, questions,
priorities, reference drawings), never the author's uploaded files, answers or progress. Each
republish is a new version. Acquiring gives lasting access: a course in the acquirer's account
that mirrors the listing (read-only, synced on every republish) while their study is their own.
"""

import uuid
from datetime import datetime
from typing import Any

from sqlalchemy import (
    JSON,
    CheckConstraint,
    ForeignKey,
    Index,
    Integer,
    String,
    Text,
    UniqueConstraint,
    Uuid,
)
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
    # Set by the author: 0 is free; a price needs payments (services/payments.py).
    price_cents: Mapped[int] = mapped_column(Integer, default=0, server_default="0")
    # How many of the first questions (with their answers) anyone may read before getting the
    # course: a free sample, when the author chooses one. 0 (the default): none.
    preview_count: Mapped[int] = mapped_column(Integer, default=0, server_default="0")
    currency: Mapped[str] = mapped_column(String(3), default="EUR", server_default="EUR")
    version: Mapped[int] = mapped_column(Integer, default=1)
    snapshot: Mapped[dict[str, Any]] = mapped_column(JSON)
    chapter_count: Mapped[int] = mapped_column(Integer, default=0)
    item_count: Mapped[int] = mapped_column(Integer, default=0)
    acquisition_count: Mapped[int] = mapped_column(Integer, default=0, server_default="0")
    # Reviews (MarketplaceReview), kept here so listings sort and show without counting.
    rating_count: Mapped[int] = mapped_column(Integer, default=0, server_default="0")
    rating_sum: Mapped[int] = mapped_column(Integer, default=0, server_default="0")
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


class MarketplaceReview(Base):
    """A rating (1-5 stars) and an optional comment by someone who has the course: one per
    person and listing, editable. The author may answer once (and edit the answer)."""

    __tablename__ = "marketplace_reviews"
    __table_args__ = (
        UniqueConstraint("listing_id", "user_id"),
        CheckConstraint("rating BETWEEN 1 AND 5", name="rating_range"),
    )

    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=uuid.uuid4)
    listing_id: Mapped[uuid.UUID] = mapped_column(
        Uuid, ForeignKey("marketplace_listings.id", ondelete="CASCADE"), index=True
    )
    user_id: Mapped[uuid.UUID] = mapped_column(
        Uuid, ForeignKey("users.id", ondelete="CASCADE"), index=True
    )
    rating: Mapped[int] = mapped_column(Integer)
    comment: Mapped[str] = mapped_column(Text, default="")
    # The listing's version when it was written or last edited.
    version: Mapped[int] = mapped_column(Integer, default=1)
    reply: Mapped[str] = mapped_column(Text, default="", server_default="")
    replied_at: Mapped[datetime | None] = mapped_column(UTCDateTime, default=None)
    created_at: Mapped[datetime] = mapped_column(UTCDateTime, default=utc_now)
    updated_at: Mapped[datetime] = mapped_column(UTCDateTime, default=utc_now, onupdate=utc_now)


class MarketplaceUpdate(Base):
    """What the author told the people who have the course: the note of a new version
    (`version` set) or an announcement between versions (`version` null). The listing's
    public "What's new"."""

    __tablename__ = "marketplace_updates"
    __table_args__ = (
        Index("ix_marketplace_updates_listing_id_created_at", "listing_id", "created_at"),
    )

    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=uuid.uuid4)
    listing_id: Mapped[uuid.UUID] = mapped_column(
        Uuid, ForeignKey("marketplace_listings.id", ondelete="CASCADE")
    )
    version: Mapped[int | None] = mapped_column(Integer, default=None)
    note: Mapped[str] = mapped_column(Text)
    # How many people were told.
    recipients: Mapped[int] = mapped_column(Integer, default=0)
    created_at: Mapped[datetime] = mapped_column(UTCDateTime, default=utc_now)


class MarketplaceOrder(Base):
    """One attempt to buy a paid listing (services/payments.py). PENDING while the buyer is on
    the payment page; PAID when the payment provider confirmed it (only then is access given);
    FAILED or EXPIRED otherwise; REFUNDED when the money went back (access is removed)."""

    __tablename__ = "marketplace_orders"
    __table_args__ = (
        Index("ix_marketplace_orders_seller_id_status", "seller_id", "status"),
        Index("ix_marketplace_orders_buyer_id_listing_id", "buyer_id", "listing_id"),
    )

    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=uuid.uuid4)
    listing_id: Mapped[uuid.UUID] = mapped_column(
        Uuid, ForeignKey("marketplace_listings.id", ondelete="CASCADE")
    )
    buyer_id: Mapped[uuid.UUID] = mapped_column(Uuid, ForeignKey("users.id", ondelete="CASCADE"))
    # Kept when the seller's account goes, for the buyer's receipt.
    seller_id: Mapped[uuid.UUID | None] = mapped_column(
        Uuid, ForeignKey("users.id", ondelete="SET NULL"), default=None
    )
    amount_cents: Mapped[int] = mapped_column(Integer)
    # The platform's share of amount_cents.
    fee_cents: Mapped[int] = mapped_column(Integer, default=0)
    currency: Mapped[str] = mapped_column(String(3), default="EUR")
    status: Mapped[str] = mapped_column(String(16), default="PENDING")
    provider: Mapped[str] = mapped_column(String(16))
    # The provider's checkout session and payment ids.
    provider_session_id: Mapped[str | None] = mapped_column(String(255), unique=True, default=None)
    provider_payment_id: Mapped[str | None] = mapped_column(String(255), default=None)
    created_at: Mapped[datetime] = mapped_column(UTCDateTime, default=utc_now)
    paid_at: Mapped[datetime | None] = mapped_column(UTCDateTime, default=None)
    refunded_at: Mapped[datetime | None] = mapped_column(UTCDateTime, default=None)
    # The discount code used, if any (amount_cents is what was actually paid).
    discount_code: Mapped[str | None] = mapped_column(String(40), default=None)


class MarketplaceDiscount(Base):
    """A code the author gives out: a percentage off one of their courses."""

    __tablename__ = "marketplace_discounts"
    __table_args__ = (
        UniqueConstraint("listing_id", "code"),
        CheckConstraint("percent_off BETWEEN 1 AND 90", name="percent_range"),
    )

    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=uuid.uuid4)
    listing_id: Mapped[uuid.UUID] = mapped_column(
        Uuid, ForeignKey("marketplace_listings.id", ondelete="CASCADE"), index=True
    )
    # Uppercase letters and digits.
    code: Mapped[str] = mapped_column(String(40))
    percent_off: Mapped[int] = mapped_column(Integer)
    # Null: no limit.
    max_uses: Mapped[int | None] = mapped_column(Integer, default=None)
    used_count: Mapped[int] = mapped_column(Integer, default=0, server_default="0")
    expires_at: Mapped[datetime | None] = mapped_column(UTCDateTime, default=None)
    created_at: Mapped[datetime] = mapped_column(UTCDateTime, default=utc_now)
