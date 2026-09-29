from typing import Annotated
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field

from app.models.enums import ItemGenerationStatus, StudyState
from app.schemas.common import InputModel, PatchModel, UTCTimestamp

# Limits mirror the column sizes in app/models/course.py — SQLite doesn't enforce VARCHAR lengths,
# so without these an over-long value would pass tests and then fail on Postgres.
Title = Annotated[str, Field(min_length=1, max_length=200)]
Description = Annotated[str, Field(max_length=2000)]
LanguageCode = Annotated[str, Field(pattern=r"^[a-z]{2}(-[A-Z]{2})?$")]
Order = Annotated[int, Field(ge=0)]


class CourseCreate(InputModel):
    title: Title
    description: Description = ""
    language: LanguageCode = "en"


class CourseUpdate(PatchModel):
    title: Title | None = None
    description: Description | None = None
    language: LanguageCode | None = None


class CourseRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    title: str
    description: str
    language: str
    paused: bool
    created_at: UTCTimestamp
    updated_at: UTCTimestamp


class ChapterCreate(InputModel):
    title: Title
    description: Description = ""
    order: Order = 0


class ChapterUpdate(PatchModel):
    title: Title | None = None
    description: Description | None = None
    order: Order | None = None


class ChapterRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    course_id: UUID
    title: str
    description: str
    order: int
    paused: bool


class TopicCreate(InputModel):
    title: Title
    description: Description = ""
    order: Order = 0


class TopicUpdate(PatchModel):
    title: Title | None = None
    description: Description | None = None
    order: Order | None = None


class TopicRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    chapter_id: UUID
    course_id: UUID
    title: str
    description: str
    order: int
    paused: bool


class ConceptCreate(InputModel):
    title: Title
    description: Description = ""
    order: Order = 0


class ConceptUpdate(PatchModel):
    title: Title | None = None
    description: Description | None = None
    order: Order | None = None
    # false = the user reviewed it and keeps it without a source.
    needs_source_review: bool | None = None


class ConceptRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    topic_id: UUID
    chapter_id: UUID
    course_id: UUID
    title: str
    description: str
    order: int
    study_state: StudyState
    # Its source material was deleted and nothing else supports it: keep, edit or delete it.
    needs_source_review: bool
    # Learning Item generation for this Concept (starts on activation); the error is user-safe.
    item_generation_status: ItemGenerationStatus
    item_generation_error: str | None
    # ACTIVE and not inside a paused Topic/Chapter/Course: will enter normal review (§50).
    is_reviewable: bool
