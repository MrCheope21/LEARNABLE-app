"""Tags a user follows (docs/COMMUNITY.md §6): when a course carrying one of them is published
for the first time, they get a notification. Tags are compared lowercased."""

import uuid
from collections import Counter

from sqlalchemy import delete, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.core.errors import InvalidRequestError
from app.models.community import Block, TagSubscription
from app.models.marketplace import MarketplaceAcquisition, MarketplaceListing
from app.schemas.community import Interests
from app.services import notifications

MAX_TAGS = 30
SUGGESTIONS = 12


def normalize(tag: str) -> str:
    return " ".join(tag.split()).lower().lstrip("#")


def _followed(db: Session, user_id: uuid.UUID) -> list[str]:
    return list(
        db.scalars(
            select(TagSubscription.tag)
            .where(TagSubscription.user_id == user_id)
            .order_by(TagSubscription.created_at, TagSubscription.tag)
        )
    )


def interests(db: Session, user_id: uuid.UUID) -> Interests:
    followed = _followed(db, user_id)
    counts: Counter[str] = Counter()
    for tags in db.scalars(
        select(MarketplaceListing.tags).where(MarketplaceListing.status == "PUBLISHED")
    ):
        counts.update({normalize(t) for t in tags or [] if len(normalize(t)) >= 2})
    ranked = sorted(counts, key=lambda tag: (-counts[tag], tag))
    suggestions = [tag for tag in ranked if tag not in followed][:SUGGESTIONS]
    return Interests(tags=followed, suggestions=suggestions)


def follow(db: Session, user_id: uuid.UUID, tag: str) -> Interests:
    tag = normalize(tag)
    if len(tag) < 2:
        raise InvalidRequestError("Type at least 2 letters.")
    followed = _followed(db, user_id)
    if tag not in followed:
        if len(followed) >= MAX_TAGS:
            raise InvalidRequestError(f"You can follow up to {MAX_TAGS} topics.")
        db.add(TagSubscription(user_id=user_id, tag=tag))
        try:
            db.commit()
        except IntegrityError:
            db.rollback()  # added twice at the same moment
    return interests(db, user_id)


def unfollow(db: Session, user_id: uuid.UUID, tag: str) -> Interests:
    db.execute(
        delete(TagSubscription).where(
            TagSubscription.user_id == user_id, TagSubscription.tag == normalize(tag)
        )
    )
    db.commit()
    return interests(db, user_id)


def tell_new_course(db: Session, listing: MarketplaceListing) -> int:
    """A course was published for the first time: everyone following one of its tags is told
    (not its author, not who already has it, not who blocked or is blocked by the author).
    Returns how many. The caller commits."""
    tags = {normalize(t) for t in listing.tags or []}
    if not tags:
        return 0
    rows = db.execute(
        select(TagSubscription.user_id, TagSubscription.tag)
        .where(TagSubscription.tag.in_(tags), TagSubscription.user_id != listing.author_id)
        .order_by(TagSubscription.tag)
    ).all()
    skip = set(
        db.scalars(
            select(MarketplaceAcquisition.user_id).where(
                MarketplaceAcquisition.listing_id == listing.id
            )
        )
    )
    skip |= set(db.scalars(select(Block.blocker_id).where(Block.blocked_id == listing.author_id)))
    skip |= set(db.scalars(select(Block.blocked_id).where(Block.blocker_id == listing.author_id)))
    told: set[uuid.UUID] = set()
    for user_id, tag in rows:
        if user_id in skip or user_id in told:
            continue
        told.add(user_id)
        notifications.notify(
            db,
            user_id,
            "course_new",
            actor_id=listing.author_id,
            data={"listing_id": str(listing.id), "title": listing.title, "tag": tag},
            link=f"/marketplace/{listing.id}",
        )
    return len(told)
