"""Marketplace endpoints: browse and preview listings, get access, publish one's own courses."""

import uuid

from fastapi import APIRouter, Depends, Query, status
from pydantic import BaseModel
from sqlalchemy.orm import Session

from app.api.cleanup import DrawingCleanup
from app.auth.dependencies import get_current_user
from app.core.rate_limit import per_user
from app.db.session import get_db
from app.models.user import User
from app.schemas.marketplace import (
    Acquired,
    Category,
    CourseOrigin,
    Level,
    ListingDetail,
    ListingInfo,
    ListingPublish,
    ListingSize,
    ListingSort,
    ListingSummary,
    MyListing,
)
from app.services import marketplace
from app.services.courses.service import get_owned_course
from app.storage.documents import DocumentStorage, get_document_storage

router = APIRouter(tags=["marketplace"])

CurrentUser = Depends(get_current_user)
DB = Depends(get_db)
Storage = Depends(get_document_storage)


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
        sort=sort,
        limit=limit,
    )


@router.get("/marketplace/listings/{listing_id}", response_model=ListingDetail)
def detail(listing_id: uuid.UUID, db: Session = DB, user: User = CurrentUser) -> ListingDetail:
    return marketplace.detail(db, user.id, listing_id)


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
    course_id: uuid.UUID, payload: ListingInfo, db: Session = DB, user: User = CurrentUser
) -> MyListing:
    return marketplace.save_info(db, user.id, course_id, payload)


@router.post(
    "/courses/{course_id}/marketplace/publish",
    response_model=MyListing,
    dependencies=[Depends(per_user("marketplace_publish", 20, 3600))],
)
def publish(
    course_id: uuid.UUID,
    payload: ListingPublish,
    db: Session = DB,
    user: User = CurrentUser,
    storage: DocumentStorage = Storage,
    cleanup: DrawingCleanup = Depends(),
) -> MyListing:
    listing = marketplace.publish(db, storage, user.id, course_id, payload)
    # Questions the author removed went from every course with access, answers included.
    for synced in marketplace.courses_with_access(db, listing.id):
        cleanup.after(synced)
    return listing
