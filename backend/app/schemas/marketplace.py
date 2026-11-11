"""Marketplace API shapes. Authors are shown by display name only, never by email.

Before getting access, a listing shows only what its author wrote about it (title, description,
category, tags) and its size: the chapter titles with their question counts. No question, answer
or drawing is shown until the course is in the user's courses, and none can be downloaded even
then: it is studied inside LEARNABLE.
"""

from enum import StrEnum
from typing import Annotated, Literal
from uuid import UUID

from pydantic import BaseModel, Field

from app.schemas.common import InputModel, UTCTimestamp

Tag = Annotated[str, Field(min_length=1, max_length=40)]


class Category(StrEnum):
    LAW = "law"
    ECONOMICS_BUSINESS = "economics_business"
    ACCOUNTING_FINANCE = "accounting_finance"
    MEDICINE_HEALTH = "medicine_health"
    SCIENCES = "sciences"
    MATHEMATICS = "mathematics"
    ENGINEERING = "engineering"
    COMPUTER_SCIENCE = "computer_science"
    LANGUAGES = "languages"
    HUMANITIES = "humanities"
    ARTS = "arts"
    PROFESSIONAL_EXAMS = "professional_exams"
    OTHER = "other"


class ListingSort(StrEnum):
    POPULAR = "popular"
    NEWEST = "newest"
    LARGEST = "largest"
    BEST_RATED = "best_rated"


# Browse filter: free courses only, or paid ones only.
ListingPrice = Literal["free", "paid"]


# By number of questions.
ListingSize = Literal["small", "medium", "large"]
SIZE_BOUNDS: dict[str, tuple[int, int | None]] = {
    "small": (0, 49),
    "medium": (50, 299),
    "large": (300, None),
}


class Level(StrEnum):
    ALL = "all"
    BEGINNER = "beginner"
    INTERMEDIATE = "intermediate"
    ADVANCED = "advanced"


Outcome = Annotated[str, Field(min_length=1, max_length=200)]


class ListingInfo(InputModel):
    """The course's sales page, written by its author: all a buyer sees before getting access,
    with the chapter titles and question counts. Editable at any time, published or not."""

    title: Annotated[str, Field(min_length=1, max_length=200)]
    # One line under the title, e.g. "All 300 questions of the oral exam, with model answers".
    subtitle: Annotated[str, Field(max_length=200)] = ""
    # What the course covers, how it was made, how to use it.
    description: Annotated[str, Field(min_length=1, max_length=5000)]
    # "What you'll learn": up to 8 points.
    outcomes: list[Outcome] = Field(default_factory=list, max_length=8)
    # Who it's for, e.g. "Candidates for the chartered accountant exam (first session)".
    audience: Annotated[str, Field(max_length=1000)] = ""
    level: Level = Level.ALL
    category: Category
    tags: list[Tag] = Field(default_factory=list, max_length=8)
    # In cents of a euro; 0 is free. A price needs payments set up (GET /payments/payout).
    # People who already have the course keep it whatever the price becomes.
    price_cents: Annotated[int, Field(ge=0, le=1_000_000)] = 0


class ListingPublish(ListingInfo):
    # The author confirms the content is theirs to share (their own questions and answers, or
    # material they have the rights to). Required.
    rights_confirmed: Literal[True]
    # On a republish: what changed and what it means for who has the course. Everyone with
    # access is told (a notification, and an email unless they turned it off).
    update_note: Annotated[str, Field(max_length=2000)] = ""


class Announcement(InputModel):
    """A message from the author to everyone who has the course, without a new version."""

    message: Annotated[str, Field(min_length=1, max_length=2000)]


class UpdateRead(BaseModel):
    id: UUID
    # Null for an announcement between versions.
    version: int | None
    note: str
    created_at: UTCTimestamp


class Announced(BaseModel):
    recipients: int


class ReviewWrite(InputModel):
    rating: Annotated[int, Field(ge=1, le=5)]
    comment: Annotated[str, Field(max_length=2000)] = ""


class ReviewReply(InputModel):
    # Empty removes the reply.
    reply: Annotated[str, Field(max_length=2000)]


class ListingReview(BaseModel):
    id: UUID
    author: str
    rating: int
    comment: str
    created_at: UTCTimestamp
    updated_at: UTCTimestamp
    is_mine: bool
    # The course author's answer.
    reply: str
    replied_at: UTCTimestamp | None


class ListingReviews(BaseModel):
    count: int
    # Null with no reviews.
    average: float | None
    # How many reviews gave 1, 2, 3, 4 and 5 stars.
    distribution: list[int]
    # The viewer's own review, when they wrote one.
    mine: ListingReview | None
    # The viewer has the course and isn't its author.
    can_review: bool
    items: list[ListingReview]


class PayoutStatus(BaseModel):
    """Whether the viewer can sell paid courses."""

    # Payments are set up on this server.
    enabled: bool
    # The viewer started setting up their account with the payment provider.
    account: bool
    # ... and it can take payments.
    ready: bool
    fee_percent: int
    price_min_cents: int
    price_max_cents: int


class Redirect(BaseModel):
    """An address on the payment provider's site to send the browser to."""

    url: str


class OrderStatus(BaseModel):
    # PENDING, PAID, EXPIRED or REFUNDED.
    status: str
    # The course in the buyer's account, once paid.
    course_id: UUID | None


class Sale(BaseModel):
    id: UUID
    listing_id: UUID
    title: str
    amount_cents: int
    # After the platform's fee (the payment provider's own fee is on their statement).
    net_cents: int
    currency: str
    paid_at: UTCTimestamp
    refunded: bool


class Sales(BaseModel):
    count: int
    gross_cents: int
    net_cents: int
    currency: str
    items: list[Sale]


class ListingSummary(BaseModel):
    id: UUID
    title: str
    subtitle: str
    description: str
    outcomes: list[str]
    audience: str
    level: Level
    category: Category
    language: str
    tags: list[str]
    author: str
    price_cents: int
    currency: str
    version: int
    chapter_count: int
    item_count: int
    acquisition_count: int
    rating_count: int
    # Mean of the reviews' stars, one decimal; null with no reviews.
    rating_average: float | None
    # Null while a draft that was never published.
    published_at: UTCTimestamp | None
    updated_at: UTCTimestamp
    # DRAFT (sales page saved, never published), PUBLISHED or UNPUBLISHED.
    status: str
    # Set when the viewer has access and the course is in their courses.
    course_id: UUID | None


class ChapterSize(BaseModel):
    title: str
    questions: int


class ListingDetail(ListingSummary):
    chapters: list[ChapterSize]
    is_mine: bool
    # The viewer got access earlier (the course may since have been removed from their courses).
    has_access: bool
    # A paid course can be bought now (payments are on and the author can take them).
    can_buy: bool
    # What the author said about new versions and announcements, newest first.
    updates: list[UpdateRead]


class MyListing(ListingSummary):
    source_course_id: UUID | None


class Acquired(BaseModel):
    course_id: UUID


class CourseOrigin(BaseModel):
    """On a course reached through the marketplace."""

    listing_id: UUID
    author: str
    version: int
