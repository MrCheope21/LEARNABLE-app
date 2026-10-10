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


class ListingPublish(ListingInfo):
    # The author confirms the content is theirs to share (their own questions and answers, or
    # material they have the rights to). Required.
    rights_confirmed: Literal[True]


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


class MyListing(ListingSummary):
    source_course_id: UUID | None


class Acquired(BaseModel):
    course_id: UUID


class CourseOrigin(BaseModel):
    """On a course reached through the marketplace."""

    listing_id: UUID
    author: str
    version: int
