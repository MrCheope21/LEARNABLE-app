from typing import Self
from uuid import UUID

from pydantic import BaseModel, Field, model_validator

from app.models.enums import CurriculumProposalStatus
from app.schemas.common import InputModel, UTCTimestamp
from app.schemas.courses import ChapterRead, ConceptRead, Description, Title, TopicRead

# Upper bound on what one apply can create, so a single request can't insert unbounded rows.
MAX_APPLIED_CONCEPTS = 2000


class CurriculumGenerate(InputModel):
    # Set: propose Topics → Concepts for this Chapter from its material, merged with what the
    # Chapter already contains. Omitted: propose Chapters → Topics → Concepts for the Course
    # from material not filed under any Chapter.
    chapter_id: UUID | None = None
    # Analyze exactly these documents (each READY, and in the Chapter when one is given).
    # Omitted: the scope's documents that haven't been analyzed yet, i.e. new material.
    document_ids: list[UUID] | None = Field(default=None, min_length=1, max_length=100)


# --- Proposal (read) ---


class ProposalSource(BaseModel):
    """Where a proposed Concept came from; open it with
    GET /documents/{document_id}/chunks/{chunk_id}."""

    chunk_id: UUID
    document_id: UUID
    # The document's filename, for showing where a passage comes from without another call.
    document_name: str
    page_number: int | None
    page_end: int | None = None
    section: str | None


class ProposalConcept(BaseModel):
    title: str
    description: str
    # Chapter proposals only: set when this is an existing Concept the new passages also teach.
    # Applying links the passages to it instead of creating a duplicate.
    existing_concept_id: UUID | None = None
    sources: list[ProposalSource]


class ProposalTopic(BaseModel):
    title: str
    description: str
    # Chapter proposals only: set when the concepts go into this existing Topic.
    existing_topic_id: UUID | None = None
    concepts: list[ProposalConcept]


class ProposalChapter(BaseModel):
    title: str
    description: str
    topics: list[ProposalTopic]


class CurriculumProposalRead(BaseModel):
    id: UUID
    course_id: UUID
    # Set for a Chapter proposal, which fills `topics`; null for a Course proposal, which fills
    # `chapters`. The other is always null, and both are null until READY.
    chapter_id: UUID | None
    status: CurriculumProposalStatus
    error_message: str | None
    chapters: list[ProposalChapter] | None
    topics: list[ProposalTopic] | None
    # Documents fully sent to the AI; applying marks them analyzed.
    document_ids: list[UUID]
    passages_used: int
    passages_total: int
    dropped_concepts: int
    ai_provider: str | None
    ai_model: str | None
    ai_model_version: str | None
    prompt_version: str | None
    created_at: UTCTimestamp
    updated_at: UTCTimestamp
    applied_at: UTCTimestamp | None


# --- Apply (the user's reviewed version of a proposal) ---


class ApplyConcept(InputModel):
    title: Title
    description: Description = ""
    source_chunk_ids: list[UUID] = Field(default_factory=list, max_length=20)
    # Chapter proposals only: link the sources to this existing Concept of the Chapter instead
    # of creating one (its title and description are left as they are).
    existing_concept_id: UUID | None = None


class ApplyTopic(InputModel):
    title: Title
    description: Description = ""
    concepts: list[ApplyConcept] = Field(default_factory=list, max_length=500)
    # Chapter proposals only: add the concepts to this existing Topic of the Chapter (its title
    # and description are left as they are).
    existing_topic_id: UUID | None = None


class ApplyChapter(InputModel):
    title: Title
    description: Description = ""
    topics: list[ApplyTopic] = Field(default_factory=list, max_length=200)


class CurriculumApply(InputModel):
    """The curriculum as the user accepted it: renamed, reordered, merged, split, moved or with
    items deleted, all expressed by sending the edited tree (docs/PROJECT_SPEC.md §20).
    `chapters` for a Course proposal, `topics` for a Chapter proposal: exactly one."""

    chapters: list[ApplyChapter] | None = Field(default=None, min_length=1, max_length=100)
    topics: list[ApplyTopic] | None = Field(default=None, min_length=1, max_length=200)

    @model_validator(mode="after")
    def _one_tree_within_limits(self) -> Self:
        if (self.chapters is None) == (self.topics is None):
            raise ValueError("send exactly one of `chapters` (Course proposal) or `topics`")
        topics = self.topics or [t for c in self.chapters or [] for t in c.topics]
        if sum(len(t.concepts) for t in topics) > MAX_APPLIED_CONCEPTS:
            raise ValueError(f"at most {MAX_APPLIED_CONCEPTS} concepts can be applied at once")
        return self


# --- Course outline ---


class TopicOutline(TopicRead):
    concepts: list[ConceptRead]


class ChapterOutline(ChapterRead):
    topics: list[TopicOutline]
