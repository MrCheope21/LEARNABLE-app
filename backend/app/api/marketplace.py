"""Marketplace endpoints: browse and preview listings, get access, publish one's own courses."""

import uuid

from fastapi import APIRouter, BackgroundTasks, Depends, Query, status
from pydantic import BaseModel
from sqlalchemy.orm import Session

from app.api.cleanup import DrawingCleanup
from app.auth.dependencies import get_current_user
from app.core.config import get_settings
from app.core.rate_limit import per_user
from app.db.session import get_db
from app.email.sender import EmailSender, get_email_sender
from app.models.user import User
from app.schemas.marketplace import (
    Acquired,
    Announced,
    Announcement,
    Category,
    CourseOrigin,
    Level,
    ListingDetail,
    ListingInfo,
    ListingPrice,
    ListingPublish,
    ListingReviews,
    ListingSize,
    ListingSort,
    ListingSummary,
    MyListing,
    ReviewReply,
    ReviewWrite,
)
from app.services import marketplace
from app.services.courses.service import get_owned_course
from app.services.payments import PaymentGateway, get_payment_gateway
from app.storage.documents import DocumentStorage, get_document_storage

router = APIRouter(tags=["marketplace"])

CurrentUser = Depends(get_current_user)
DB = Depends(get_db)
Storage = Depends(get_document_storage)
Gateway = Depends(get_payment_gateway)
Sender = Depends(get_email_sender)


def _email_update(
    db: Session,
    background: BackgroundTasks,
    sender: EmailSender,
    listing_id: uuid.UUID,
    title: str,
    note: str,
) -> None:
    """Emails the author's note to the people with access who take such emails, after the
    response (only when this server really sends email)."""
    settings = get_settings()
    if not note.strip() or settings.email_backend != "smtp":
        return
    link = f"{settings.public_app_url.rstrip('/')}/marketplace/{listing_id}"
    for email, language in marketplace.update_recipients(db, listing_id):
        subject, body = marketplace.update_email(title, note.strip(), link, language)
        background.add_task(sender.send, email, subject, body)


class CourseMarketplace(BaseModel):
    # The author's own course: its listing (draft sales page or published), if any.
    listing: MyListing | None
    # A course reached through the marketplace: whose it is.
    origin: CourseOrigin | None


@router.get("/marketplace/listings", response_model=list[ListingSummary])
def browse(
    q: str | None = Query(default=None, max_length=200),
    category: Category | None = None,
    language: str | None = Query(default=None, max_length=16),
    size: ListingSize | None = None,
    level: Level | None = None,
    price: ListingPrice | None = None,
    sort: ListingSort = ListingSort.POPULAR,
    limit: int = Query(default=50, ge=1, le=100),
    db: Session = DB,
    user: User = CurrentUser,
) -> list[ListingSummary]:
    return marketplace.browse(
        db,
        user.id,
        query=q,
        category=category,
        language=language,
        size=size,
        level=level,
        price=price,
        sort=sort,
        limit=limit,
    )


@router.get("/marketplace/listings/{listing_id}", response_model=ListingDetail)
def detail(
    listing_id: uuid.UUID,
    db: Session = DB,
    user: User = CurrentUser,
    gateway: PaymentGateway | None = Gateway,
) -> ListingDetail:
    return marketplace.detail(db, user.id, listing_id, gateway)


@router.get("/marketplace/listings/{listing_id}/reviews", response_model=ListingReviews)
def reviews(listing_id: uuid.UUID, db: Session = DB, user: User = CurrentUser) -> ListingReviews:
    return marketplace.reviews(db, user.id, listing_id)


@router.put(
    "/marketplace/listings/{listing_id}/review",
    response_model=ListingReviews,
    dependencies=[Depends(per_user("marketplace_review", 30, 3600))],
)
def write_review(
    listing_id: uuid.UUID, payload: ReviewWrite, db: Session = DB, user: User = CurrentUser
) -> ListingReviews:
    """Stars and a comment, from someone who has the course; writing again edits it."""
    return marketplace.write_review(db, user.id, listing_id, payload)


@router.delete("/marketplace/listings/{listing_id}/review", status_code=status.HTTP_204_NO_CONTENT)
def delete_review(listing_id: uuid.UUID, db: Session = DB, user: User = CurrentUser) -> None:
    marketplace.delete_review(db, user.id, listing_id)


@router.put(
    "/marketplace/reviews/{review_id}/reply",
    status_code=status.HTTP_204_NO_CONTENT,
    dependencies=[Depends(per_user("marketplace_reply", 60, 3600))],
)
def reply_to_review(
    review_id: uuid.UUID, payload: ReviewReply, db: Session = DB, user: User = CurrentUser
) -> None:
    """The course's author answers a review."""
    marketplace.reply_to_review(db, user.id, review_id, payload.reply)


@router.post(
    "/marketplace/listings/{listing_id}/acquire",
    response_model=Acquired,
    status_code=status.HTTP_201_CREATED,
    dependencies=[Depends(per_user("marketplace_acquire", 30, 3600))],
)
def acquire(
    listing_id: uuid.UUID,
    db: Session = DB,
    user: User = CurrentUser,
    storage: DocumentStorage = Storage,
) -> Acquired:
    return Acquired(course_id=marketplace.acquire(db, storage, user.id, listing_id))


@router.get("/marketplace/mine", response_model=list[MyListing])
def mine(db: Session = DB, user: User = CurrentUser) -> list[MyListing]:
    return marketplace.my_listings(db, user.id)


@router.post(
    "/marketplace/listings/{listing_id}/unpublish",
    response_model=MyListing,
)
def unpublish(listing_id: uuid.UUID, db: Session = DB, user: User = CurrentUser) -> MyListing:
    return marketplace.unpublish(db, user.id, listing_id)


@router.get("/courses/{course_id}/marketplace", response_model=CourseMarketplace)
def course_marketplace(
    course_id: uuid.UUID, db: Session = DB, user: User = CurrentUser
) -> CourseMarketplace:
    course = get_owned_course(db, user.id, course_id)
    return CourseMarketplace(
        listing=marketplace.listing_for_course(db, user.id, course_id),
        origin=marketplace.origin(db, course),
    )


@router.put("/courses/{course_id}/marketplace/info", response_model=MyListing)
def save_info(
    course_id: uuid.UUID,
    payload: ListingInfo,
    db: Session = DB,
    user: User = CurrentUser,
    gateway: PaymentGateway | None = Gateway,
) -> MyListing:
    return marketplace.save_info(db, user.id, course_id, payload, gateway)


@router.post(
    "/courses/{course_id}/marketplace/publish",
    response_model=MyListing,
    dependencies=[Depends(per_user("marketplace_publish", 20, 3600))],
)
def publish(
    course_id: uuid.UUID,
    payload: ListingPublish,
    background: BackgroundTasks,
    db: Session = DB,
    user: User = CurrentUser,
    storage: DocumentStorage = Storage,
    cleanup: DrawingCleanup = Depends(),
    gateway: PaymentGateway | None = Gateway,
    sender: EmailSender = Sender,
) -> MyListing:
    listing = marketplace.publish(db, storage, user.id, course_id, payload, gateway)
    # Questions the author removed went from every course with access, answers included.
    for synced in marketplace.courses_with_access(db, listing.id):
        cleanup.after(synced)
    if listing.version > 1:
        _email_update(db, background, sender, listing.id, listing.title, payload.update_note)
    return listing


@router.post(
    "/courses/{course_id}/marketplace/announce",
    response_model=Announced,
    dependencies=[Depends(per_user("marketplace_announce", 5, 86400))],
)
def announce(
    course_id: uuid.UUID,
    payload: Announcement,
    background: BackgroundTasks,
    db: Session = DB,
    user: User = CurrentUser,
    sender: EmailSender = Sender,
) -> Announced:
    """The author writes to everyone who has the course (at most 5 a day)."""
    told = marketplace.announce(db, user.id, course_id, payload.message)
    listing = marketplace.listing_for_course(db, user.id, course_id)
    if listing is not None:
        _email_update(db, background, sender, listing.id, listing.title, payload.message)
    return Announced(recipients=told)
