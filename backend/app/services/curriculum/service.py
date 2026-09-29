"""AI curriculum proposals: generate, review, apply (docs/PROJECT_SPEC.md §20, §19, §21).

    request (202, GENERATING) → background: collect the scope's passages → AIProvider → ground
    the answer in the passages actually sent → READY | INSUFFICIENT_CONTEXT | FAILED
    → the user edits the tree and applies it → Topics/Concepts (NOT_STUDIED) + sources

Two scopes:
- **Chapter** (the usual flow): the user creates the Chapters and files material under each.
  The AI proposes Topics → Concepts for one Chapter from its material, and sees what the Chapter
  already contains, so added or revised material is merged in (new Concepts into existing
  Topics, new passages linked to existing Concepts) instead of duplicated.
- **Course**: the AI proposes Chapters → Topics → Concepts from material not filed under any
  Chapter, for users who don't define Chapters themselves.

By default only material not analyzed yet is sent, so each upload is analyzed on its own and
the AI is never handed the whole Course again. Applying marks the documents analyzed.

Nothing is activated, ever: applied Concepts start NOT_STUDIED and the user activates them (§21).
Retrieval is Course-scoped in the WHERE clause of every query (§10, §72).

Privacy (spec §70, §94): source text and AI output are never logged, only ids and error types.
"""

import logging
import uuid
from collections.abc import Iterable
from dataclasses import dataclass
from typing import Any

from sqlalchemy import Select, func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session, selectinload, sessionmaker

from app.ai.provider import AIProvider, ChapterCurriculumResult, CurriculumResult
from app.ai.schemas import (
    ChapterCurriculumOutput,
    ChapterCurriculumRequest,
    CurriculumOutput,
    CurriculumRequest,
    ExistingConcept,
    ExistingTopic,
    SourcePassage,
)
from app.core.errors import (
    AINotConfiguredError,
    AppError,
    ConflictError,
    InvalidRequestError,
    NotFoundError,
)
from app.db.types import utc_now
from app.models.course import Chapter, Concept, Course, Topic
from app.models.curriculum import ConceptSource, CurriculumProposal
from app.models.document import Document, DocumentChunk
from app.models.enums import CurriculumProposalStatus, DocumentPurpose, DocumentStatus
from app.schemas.curriculum import (
    ApplyTopic,
    CurriculumApply,
    CurriculumGenerate,
    CurriculumProposalRead,
    ProposalChapter,
    ProposalConcept,
    ProposalSource,
    ProposalTopic,
)
from app.services.courses.service import get_owned_concept, get_owned_course
from app.services.recovery import recover_stale_jobs

logger = logging.getLogger(__name__)

# Existing Concepts listed to the AI for a Chapter; beyond this the prompt would be mostly list.
MAX_EXISTING_CONCEPTS_SHOWN = 500

_NO_MATERIAL = "There is no processed study material to build a curriculum from."
_NO_NEW_MATERIAL = "All of this material has already been analyzed."
_INSUFFICIENT = "The study material doesn't contain enough to build a curriculum from."
_NOTHING_GROUNDED = (
    "The AI proposed nothing that it could tie to your study material, so the proposal was "
    "discarded."
)
_UNEXPECTED_FAILURE = "The curriculum couldn't be generated."

Status = CurriculumProposalStatus


# --- Request ---


@dataclass(frozen=True)
class GenerationJob:
    proposal: CurriculumProposal
    provider: AIProvider
    document_ids: list[uuid.UUID]


def request_proposal(
    db: Session,
    provider: AIProvider | None,
    user_id: uuid.UUID,
    course_id: uuid.UUID,
    payload: CurriculumGenerate,
) -> GenerationJob:
    """Validates and records the request; the caller schedules `generate_proposal`."""
    get_owned_course(db, user_id, course_id)  # first: an intruder gets 404, never 503/409
    chapter_id = payload.chapter_id
    if chapter_id is not None:
        _check_chapter(db, course_id, chapter_id)
    if provider is None:
        raise AINotConfiguredError("AI features are not configured on this server.")

    # Before the readiness and one-at-a-time checks, so a job lost to a restart blocks nothing.
    recover_stale_jobs(db, course_id)
    if payload.document_ids is not None:
        document_ids = payload.document_ids
        _check_documents(db, course_id, chapter_id, document_ids)
    else:
        document_ids = _unanalyzed_documents(db, course_id, chapter_id)
        if not document_ids:
            if _ready_documents_exist(db, course_id, chapter_id):
                raise ConflictError(_NO_NEW_MATERIAL, details={"reason": "no_new_material"})
            raise ConflictError(_NO_MATERIAL, details={"reason": "no_source_material"})
    if _count_chunks(db, course_id, document_ids) == 0:
        raise ConflictError(_NO_MATERIAL, details={"reason": "no_source_material"})

    running = db.scalar(
        select(CurriculumProposal.id).where(
            CurriculumProposal.course_id == course_id,
            CurriculumProposal.status == Status.GENERATING,
        )
    )
    if running is not None:
        raise ConflictError(
            "A curriculum is already being generated for this course.",
            details={"proposal_id": str(running)},
        )

    proposal = CurriculumProposal(
        course_id=course_id, chapter_id=chapter_id, status=Status.GENERATING
    )
    db.add(proposal)
    db.commit()
    db.refresh(proposal)
    return GenerationJob(proposal=proposal, provider=provider, document_ids=document_ids)


def _check_chapter(db: Session, course_id: uuid.UUID, chapter_id: uuid.UUID) -> Chapter:
    chapter = db.get(Chapter, chapter_id)
    if chapter is None or chapter.course_id != course_id:
        raise NotFoundError("Chapter not found")
    return chapter


def _in_scope(stmt: Select[Any], chapter_id: uuid.UUID | None) -> Select[Any]:
    """Chapter scope: the Chapter's documents. Course scope: documents not filed anywhere."""
    if chapter_id is None:
        return stmt.where(Document.chapter_id.is_(None))
    return stmt.where(Document.chapter_id == chapter_id)


def _unanalyzed_documents(
    db: Session, course_id: uuid.UUID, chapter_id: uuid.UUID | None
) -> list[uuid.UUID]:
    stmt = select(Document.id).where(
        Document.course_id == course_id,
        Document.status == DocumentStatus.READY,
        Document.purpose == DocumentPurpose.MATERIAL,
        Document.analyzed_at.is_(None),
    )
    return list(db.scalars(_in_scope(stmt, chapter_id).order_by(Document.created_at)))


def _ready_documents_exist(db: Session, course_id: uuid.UUID, chapter_id: uuid.UUID | None) -> bool:
    stmt = select(Document.id).where(
        Document.course_id == course_id,
        Document.status == DocumentStatus.READY,
        Document.purpose == DocumentPurpose.MATERIAL,
    )
    return db.scalar(_in_scope(stmt, chapter_id).limit(1)) is not None


def _check_documents(
    db: Session,
    course_id: uuid.UUID,
    chapter_id: uuid.UUID | None,
    document_ids: list[uuid.UUID],
) -> None:
    rows = db.execute(
        select(Document.id, Document.status, Document.chapter_id, Document.purpose).where(
            Document.course_id == course_id, Document.id.in_(document_ids)
        )
    ).all()
    if len({row.id for row in rows}) != len(set(document_ids)):
        # Same answer for another user's document and a nonexistent one (spec §10).
        raise NotFoundError("Document not found")
    banks = [str(row.id) for row in rows if row.purpose is not DocumentPurpose.MATERIAL]
    if banks:
        raise ConflictError(
            "Question banks are imported as they are; a curriculum is built from material only.",
            details={"reason": "documents_are_question_banks", "document_ids": banks},
        )
    not_ready = [str(row.id) for row in rows if row.status is not DocumentStatus.READY]
    if not_ready:
        raise ConflictError(
            "Some documents haven't finished processing, or failed.",
            details={"reason": "documents_not_ready", "document_ids": not_ready},
        )
    if chapter_id is not None:
        elsewhere = [str(row.id) for row in rows if row.chapter_id != chapter_id]
        if elsewhere:
            raise ConflictError(
                "Some documents aren't filed under this chapter.",
                details={"reason": "documents_not_in_chapter", "document_ids": elsewhere},
            )


def _chunks_query(
    course_id: uuid.UUID, document_ids: list[uuid.UUID]
) -> Select[tuple[DocumentChunk, str]]:
    return (
        select(DocumentChunk, Document.filename)
        .join(Document, Document.id == DocumentChunk.document_id)
        .where(
            # Both scoped, so neither table alone can widen the scope (spec §72).
            DocumentChunk.course_id == course_id,
            Document.course_id == course_id,
            Document.status == DocumentStatus.READY,
            Document.id.in_(document_ids),
        )
        .order_by(Document.created_at, Document.id, DocumentChunk.position)
    )


def _count_chunks(db: Session, course_id: uuid.UUID, document_ids: list[uuid.UUID]) -> int:
    subquery = _chunks_query(course_id, document_ids).subquery()
    return db.scalar(select(func.count()).select_from(subquery)) or 0


# --- Generation (background task) ---


@dataclass
class _Refs:
    """Short refs shown to the model, mapped back to ids."""

    chunks: dict[str, uuid.UUID]
    topics: dict[str, uuid.UUID]
    concepts: dict[str, uuid.UUID]


def generate_proposal(
    session_factory: sessionmaker[Session],
    provider: AIProvider,
    proposal_id: uuid.UUID,
    document_ids: list[uuid.UUID],
    max_context_chars: int,
) -> None:
    """Runs after the response. The AI call happens with no database session open: it can take
    a minute, and holding a connection (and a transaction) that long starves the pool."""
    request: CurriculumRequest | ChapterCurriculumRequest
    with session_factory() as db:
        proposal = db.get(CurriculumProposal, proposal_id)
        if proposal is None or proposal.status is not Status.GENERATING:
            return
        course = db.get(Course, proposal.course_id)
        if course is None:
            return
        passages, chunk_refs, fully_sent = _collect_passages(
            db, course.id, document_ids, max_context_chars
        )
        refs = _Refs(chunks=chunk_refs, topics={}, concepts={})
        if proposal.chapter_id is None:
            request = CurriculumRequest(
                course_title=course.title, language=course.language, passages=passages
            )
        else:
            chapter = db.get(Chapter, proposal.chapter_id)
            if chapter is None:
                return
            existing = _existing_structure(db, chapter, refs)
            request = ChapterCurriculumRequest(
                course_title=course.title,
                chapter_title=chapter.title,
                language=course.language,
                existing_topics=existing,
                passages=passages,
            )
        proposal.passages_used = len(passages)
        proposal.passages_total = _count_chunks(db, course.id, document_ids)
        proposal.document_ids = [str(d) for d in fully_sent]
        _commit_or_rollback(db)

    result: CurriculumResult | ChapterCurriculumResult | None = None
    failure = _NO_MATERIAL if not passages else None
    if passages:
        try:
            if isinstance(request, CurriculumRequest):
                result = provider.generate_curriculum(request)
            else:
                result = provider.generate_chapter_curriculum(request)
        except AppError as exc:
            failure = exc.message
        except Exception:
            logger.exception("Unexpected failure generating curriculum proposal %s", proposal_id)
            failure = _UNEXPECTED_FAILURE

    with session_factory() as db:
        proposal = db.get(CurriculumProposal, proposal_id)
        if proposal is None or proposal.status is not Status.GENERATING:
            return  # discarded (or expired) while the AI was working
        if result is None:
            proposal.status = (
                Status.INSUFFICIENT_CONTEXT if failure == _NO_MATERIAL else Status.FAILED
            )
            proposal.error_message = failure
        else:
            _store_result(proposal, result, refs)
        _commit_or_rollback(db)


def _collect_passages(
    db: Session,
    course_id: uuid.UUID,
    document_ids: list[uuid.UUID],
    max_chars: int,
) -> tuple[list[SourcePassage], dict[str, uuid.UUID], list[uuid.UUID]]:
    """Passages in document order until the character budget is spent. Returns them, the
    ref → chunk id map for grounding the answer, and the documents sent in full."""
    per_document = dict(
        db.execute(
            select(DocumentChunk.document_id, func.count())
            .where(
                DocumentChunk.course_id == course_id, DocumentChunk.document_id.in_(document_ids)
            )
            .group_by(DocumentChunk.document_id)
        )
        .tuples()
        .all()
    )
    passages: list[SourcePassage] = []
    chunk_ids: dict[str, uuid.UUID] = {}
    sent: dict[uuid.UUID, int] = {}
    used = 0
    for chunk, filename in db.execute(_chunks_query(course_id, document_ids)).yield_per(200):
        if passages and used + len(chunk.text) > max_chars:
            break
        ref = f"S{len(passages) + 1}"
        passages.append(
            SourcePassage(
                ref=ref,
                document_name=filename,
                page_number=chunk.page_number,
                page_end=chunk.page_end,
                section=chunk.section,
                text=chunk.text,
            )
        )
        chunk_ids[ref] = chunk.id
        sent[chunk.document_id] = sent.get(chunk.document_id, 0) + 1
        used += len(chunk.text)
    fully_sent = [doc for doc, total in per_document.items() if sent.get(doc, 0) == total]
    return passages, chunk_ids, fully_sent


def _existing_structure(db: Session, chapter: Chapter, refs: _Refs) -> list[ExistingTopic]:
    topics = db.scalars(
        select(Topic)
        .where(Topic.chapter_id == chapter.id)
        .order_by(Topic.order, Topic.created_at)
        .options(selectinload(Topic.concepts))
    ).all()
    shown = 0
    existing = []
    for topic in topics:
        topic_ref = f"T{len(refs.topics) + 1}"
        refs.topics[topic_ref] = topic.id
        concepts = []
        for concept in topic.concepts:
            if shown >= MAX_EXISTING_CONCEPTS_SHOWN:
                break
            concept_ref = f"C{len(refs.concepts) + 1}"
            refs.concepts[concept_ref] = concept.id
            concepts.append(ExistingConcept(ref=concept_ref, title=concept.title))
            shown += 1
        existing.append(ExistingTopic(ref=topic_ref, title=topic.title, concepts=concepts))
    return existing


def _store_result(
    proposal: CurriculumProposal,
    result: CurriculumResult | ChapterCurriculumResult,
    refs: _Refs,
) -> None:
    info = result.info
    proposal.ai_provider = info.provider[:50]
    proposal.ai_model = info.model[:200]
    proposal.ai_model_version = info.model_version[:200]
    proposal.prompt_version = info.prompt_version[:100]

    if not result.output.context_sufficient:
        proposal.status = Status.INSUFFICIENT_CONTEXT
        proposal.error_message = _INSUFFICIENT
        return
    if isinstance(result.output, CurriculumOutput):
        content, dropped = _ground_course(result.output, refs)
        empty = not content["chapters"]
    else:
        content, dropped = _ground_chapter(result.output, refs)
        empty = not content["topics"]
    proposal.dropped_concepts = dropped
    if empty:
        proposal.status = Status.INSUFFICIENT_CONTEXT
        proposal.error_message = _INSUFFICIENT if dropped == 0 else _NOTHING_GROUNDED
        return
    proposal.content = content
    proposal.status = Status.READY


def _cited(source_refs: list[str], refs: _Refs) -> list[str]:
    return list(dict.fromkeys(str(refs.chunks[r]) for r in source_refs if r in refs.chunks))


def _ground_course(output: CurriculumOutput, refs: _Refs) -> tuple[dict[str, Any], int]:
    """Keeps only what the passages support (spec §19): citations of refs that weren't sent are
    removed, Concepts left without a citation are dropped (and counted), and Topics/Chapters
    left empty go too. Never invents a source."""
    dropped = 0
    chapters = []
    for chapter in output.chapters:
        topics = []
        for topic in chapter.topics:
            concepts = []
            for concept in topic.concepts:
                chunk_ids = _cited(concept.source_refs, refs)
                if not chunk_ids:
                    dropped += 1
                    continue
                concepts.append(
                    {
                        "title": concept.title,
                        "description": concept.description,
                        "source_chunk_ids": chunk_ids,
                    }
                )
            if concepts:
                topics.append(
                    {"title": topic.title, "description": topic.description, "concepts": concepts}
                )
        if topics:
            chapters.append(
                {"title": chapter.title, "description": chapter.description, "topics": topics}
            )
    return {"chapters": chapters}, dropped


def _ground_chapter(output: ChapterCurriculumOutput, refs: _Refs) -> tuple[dict[str, Any], int]:
    """As `_ground_course`, and references to existing Topics/Concepts are kept only if they
    were in the listed structure (anything else is treated as new). A match to an existing
    Concept must cite passages too: linking nothing would be a no-op."""
    dropped = 0
    topics = []
    for topic in output.topics:
        concepts = []
        for concept in topic.concepts:
            chunk_ids = _cited(concept.source_refs, refs)
            if not chunk_ids:
                dropped += 1
                continue
            existing_concept = refs.concepts.get(concept.existing_concept_ref or "")
            concepts.append(
                {
                    "title": concept.title,
                    "description": concept.description,
                    "existing_concept_id": str(existing_concept) if existing_concept else None,
                    "source_chunk_ids": chunk_ids,
                }
            )
        if concepts:
            existing_topic = refs.topics.get(topic.existing_topic_ref or "")
            topics.append(
                {
                    "title": topic.title,
                    "description": topic.description,
                    "existing_topic_id": str(existing_topic) if existing_topic else None,
                    "concepts": concepts,
                }
            )
    return {"topics": topics}, dropped


def _commit_or_rollback(db: Session) -> None:
    try:
        db.commit()
    except IntegrityError:
        db.rollback()  # the Course or Chapter was deleted meanwhile


# --- Read / discard ---


def get_owned_proposal(
    db: Session, user_id: uuid.UUID, proposal_id: uuid.UUID
) -> CurriculumProposal:
    proposal = db.get(CurriculumProposal, proposal_id)
    if proposal is None:
        raise NotFoundError("Curriculum proposal not found")
    get_owned_course(db, user_id, proposal.course_id)
    return proposal


def list_proposals(
    db: Session, user_id: uuid.UUID, course_id: uuid.UUID
) -> list[CurriculumProposal]:
    get_owned_course(db, user_id, course_id)
    stmt = (
        select(CurriculumProposal)
        .where(CurriculumProposal.course_id == course_id)
        .order_by(CurriculumProposal.created_at.desc())
    )
    return list(db.scalars(stmt).all())


def delete_proposal(db: Session, user_id: uuid.UUID, proposal_id: uuid.UUID) -> None:
    """Rejecting a proposal. Allowed in any status; an applied proposal's Chapters stay. Its
    documents stay unanalyzed, so the next generation looks at them again."""
    proposal = get_owned_proposal(db, user_id, proposal_id)
    db.delete(proposal)
    db.commit()


def to_read(db: Session, proposal: CurriculumProposal) -> CurriculumProposalRead:
    """Resolves each cited chunk to its document/page/section at read time, so a passage whose
    document was deleted since simply disappears from the sources. Existing Topics/Concepts are
    shown with their current title, or as new if they were deleted since."""
    content = proposal.content or {}
    raw_chapters: list[dict[str, Any]] | None = content.get("chapters")
    raw_topics: list[dict[str, Any]] | None = content.get("topics")
    all_topics = raw_topics or [t for c in raw_chapters or [] for t in c["topics"]]
    cited = {
        uuid.UUID(chunk_id)
        for topic in all_topics
        for concept in topic["concepts"]
        for chunk_id in concept["source_chunk_ids"]
    }
    sources = _sources_by_chunk(db, proposal.course_id, cited)
    existing_topics: dict[uuid.UUID, Topic] = {}
    existing_concepts: dict[uuid.UUID, Concept] = {}
    if raw_topics is not None and proposal.chapter_id is not None:
        existing_topics = {
            t.id: t
            for t in db.scalars(select(Topic).where(Topic.chapter_id == proposal.chapter_id))
        }
        existing_concepts = {
            c.id: c
            for c in db.scalars(select(Concept).where(Concept.chapter_id == proposal.chapter_id))
        }

    def concept_read(raw: dict[str, Any]) -> ProposalConcept:
        existing_id = raw.get("existing_concept_id")
        existing = existing_concepts.get(uuid.UUID(existing_id)) if existing_id else None
        return ProposalConcept(
            title=existing.title if existing else raw["title"],
            description=existing.description if existing else raw["description"],
            existing_concept_id=existing.id if existing else None,
            sources=[
                sources[chunk_id]
                for chunk_id in map(uuid.UUID, raw["source_chunk_ids"])
                if chunk_id in sources
            ],
        )

    def topic_read(raw: dict[str, Any]) -> ProposalTopic:
        existing_id = raw.get("existing_topic_id")
        existing = existing_topics.get(uuid.UUID(existing_id)) if existing_id else None
        return ProposalTopic(
            title=existing.title if existing else raw["title"],
            description=existing.description if existing else raw["description"],
            existing_topic_id=existing.id if existing else None,
            concepts=[concept_read(c) for c in raw["concepts"]],
        )

    return CurriculumProposalRead(
        id=proposal.id,
        course_id=proposal.course_id,
        chapter_id=proposal.chapter_id,
        status=proposal.status,
        error_message=proposal.error_message,
        chapters=None
        if raw_chapters is None
        else [
            ProposalChapter(
                title=c["title"],
                description=c["description"],
                topics=[topic_read(t) for t in c["topics"]],
            )
            for c in raw_chapters
        ],
        topics=None if raw_topics is None else [topic_read(t) for t in raw_topics],
        document_ids=[uuid.UUID(d) for d in proposal.document_ids or []],
        passages_used=proposal.passages_used,
        passages_total=proposal.passages_total,
        dropped_concepts=proposal.dropped_concepts,
        ai_provider=proposal.ai_provider,
        ai_model=proposal.ai_model,
        ai_model_version=proposal.ai_model_version,
        prompt_version=proposal.prompt_version,
        created_at=proposal.created_at,
        updated_at=proposal.updated_at,
        applied_at=proposal.applied_at,
    )


def _sources_by_chunk(
    db: Session, course_id: uuid.UUID, chunk_ids: Iterable[uuid.UUID]
) -> dict[uuid.UUID, ProposalSource]:
    ids = list(chunk_ids)
    if not ids:
        return {}
    rows = db.execute(
        select(
            DocumentChunk.id,
            DocumentChunk.document_id,
            Document.filename,
            DocumentChunk.page_number,
            DocumentChunk.page_end,
            DocumentChunk.section,
        )
        .join(Document, Document.id == DocumentChunk.document_id)
        .where(DocumentChunk.course_id == course_id, DocumentChunk.id.in_(ids))
    )
    return {
        row.id: ProposalSource(
            chunk_id=row.id,
            document_id=row.document_id,
            document_name=row.filename,
            page_number=row.page_number,
            page_end=row.page_end,
            section=row.section,
        )
        for row in rows
    }


# --- Apply ---


class _Applier:
    """Creates Topics/Concepts and source links for one apply, in one transaction.

    Source ids are kept only if they are passages of this Course: another Course's passage (or a
    deleted one) is silently left out, and the answer is the same either way, so nothing about
    other Courses is revealed or linked (spec §10)."""

    def __init__(self, db: Session, course_id: uuid.UUID, requested: set[uuid.UUID]) -> None:
        self.db = db
        self.course_id = course_id
        self.valid_chunks = (
            set(
                db.scalars(
                    select(DocumentChunk.id).where(
                        DocumentChunk.course_id == course_id, DocumentChunk.id.in_(requested)
                    )
                )
            )
            if requested
            else set()
        )
        self.links: list[tuple[uuid.UUID, uuid.UUID]] = []

    def new_topic(self, chapter_id: uuid.UUID, topic_in: ApplyTopic, order: int) -> uuid.UUID:
        topic = Topic(
            id=uuid.uuid4(),
            chapter_id=chapter_id,
            course_id=self.course_id,
            title=topic_in.title,
            description=topic_in.description,
            order=order,
        )
        self.db.add(topic)
        return topic.id

    def concepts(
        self, chapter_id: uuid.UUID, topic_id: uuid.UUID, topic_in: ApplyTopic, first_order: int
    ) -> None:
        order = first_order
        for concept_in in topic_in.concepts:
            if concept_in.existing_concept_id is not None:
                concept_id = concept_in.existing_concept_id
            else:
                concept_id = uuid.uuid4()
                self.db.add(
                    Concept(
                        id=concept_id,
                        topic_id=topic_id,
                        chapter_id=chapter_id,
                        course_id=self.course_id,
                        title=concept_in.title,
                        description=concept_in.description,
                        order=order,
                    )
                )
                order += 1
            self.links.extend(
                (concept_id, chunk_id)
                for chunk_id in concept_in.source_chunk_ids
                if chunk_id in self.valid_chunks
            )

    def link_sources(self) -> None:
        # ConceptSource has no ORM relationship to Concept, so the unit of work doesn't know to
        # insert Concepts first; flush them before adding the links.
        self.db.flush()
        wanted = list(dict.fromkeys(self.links))
        concept_ids = {concept_id for concept_id, _ in wanted}
        already = set(
            self.db.execute(
                select(ConceptSource.concept_id, ConceptSource.chunk_id).where(
                    ConceptSource.concept_id.in_(concept_ids)
                )
            ).tuples()
        )
        self.db.add_all(
            ConceptSource(concept_id=concept_id, chunk_id=chunk_id, course_id=self.course_id)
            for concept_id, chunk_id in wanted
            if (concept_id, chunk_id) not in already
        )
        # Revised material re-linked these: they are supported again.
        for concept in self.db.scalars(
            select(Concept).where(Concept.id.in_(concept_ids), Concept.needs_source_review)
        ):
            concept.needs_source_review = False


def apply_proposal(
    db: Session, user_id: uuid.UUID, proposal_id: uuid.UUID, payload: CurriculumApply
) -> list[Chapter]:
    """Creates the user's reviewed tree in one transaction and marks the proposal's documents
    analyzed. Concepts start NOT_STUDIED (spec §20: never activated automatically)."""
    proposal = get_owned_proposal(db, user_id, proposal_id)
    if proposal.status is not Status.READY:
        raise ConflictError(
            "Only a ready proposal can be applied.", details={"status": proposal.status.value}
        )
    course_id = proposal.course_id
    topics_in = payload.topics or [t for c in payload.chapters or [] for t in c.topics]
    applier = _Applier(
        db,
        course_id,
        {chunk for t in topics_in for c in t.concepts for chunk in c.source_chunk_ids},
    )

    if proposal.chapter_id is None:
        if payload.chapters is None:
            raise InvalidRequestError(
                "This proposal is for the whole course: send `chapters`.",
                details={"reason": "expected_chapters"},
            )
        if any(
            t.existing_topic_id or any(c.existing_concept_id for c in t.concepts) for t in topics_in
        ):
            raise InvalidRequestError(
                "Existing topics and concepts can only be referenced in a chapter proposal.",
                details={"reason": "existing_in_course_proposal"},
            )
        _apply_chapters(db, applier, course_id, payload)
    else:
        if payload.topics is None:
            raise InvalidRequestError(
                "This proposal is for one chapter: send `topics`.",
                details={"reason": "expected_topics"},
            )
        _apply_topics(db, applier, proposal.chapter_id, payload.topics)

    applier.link_sources()
    now = utc_now()
    for document in db.scalars(
        select(Document).where(
            Document.course_id == course_id,
            Document.id.in_([uuid.UUID(d) for d in proposal.document_ids or []]),
        )
    ):
        document.analyzed_at = now
    proposal.status = Status.APPLIED
    proposal.applied_at = now
    db.commit()
    return get_outline(db, user_id, course_id)


def _apply_chapters(
    db: Session, applier: _Applier, course_id: uuid.UUID, payload: CurriculumApply
) -> None:
    last_order = db.scalar(select(func.max(Chapter.order)).where(Chapter.course_id == course_id))
    first_order = 0 if last_order is None else last_order + 1
    for chapter_index, chapter_in in enumerate(payload.chapters or []):
        chapter = Chapter(
            id=uuid.uuid4(),
            course_id=course_id,
            title=chapter_in.title,
            description=chapter_in.description,
            order=first_order + chapter_index,
        )
        db.add(chapter)
        for topic_index, topic_in in enumerate(chapter_in.topics):
            topic_id = applier.new_topic(chapter.id, topic_in, topic_index)
            applier.concepts(chapter.id, topic_id, topic_in, 0)


def _apply_topics(
    db: Session, applier: _Applier, chapter_id: uuid.UUID, topics_in: list[ApplyTopic]
) -> None:
    """Existing Topic/Concept ids must be this Chapter's: anything else (another Chapter's,
    another Course's, deleted) is a 404, identical for all of them."""
    wanted_topics = {t.existing_topic_id for t in topics_in if t.existing_topic_id}
    wanted_concepts = {
        c.existing_concept_id for t in topics_in for c in t.concepts if c.existing_concept_id
    }
    topic_orders = dict(
        db.execute(
            select(Topic.id, Topic.order).where(
                Topic.chapter_id == chapter_id, Topic.id.in_(wanted_topics)
            )
        )
        .tuples()
        .all()
    )
    if len(topic_orders) != len(wanted_topics):
        raise NotFoundError("Topic not found")
    found_concepts = set(
        db.scalars(
            select(Concept.id).where(
                Concept.chapter_id == chapter_id, Concept.id.in_(wanted_concepts)
            )
        )
    )
    if found_concepts != wanted_concepts:
        raise NotFoundError("Concept not found")

    last_topic = db.scalar(select(func.max(Topic.order)).where(Topic.chapter_id == chapter_id))
    next_topic_order = 0 if last_topic is None else last_topic + 1
    for topic_in in topics_in:
        if topic_in.existing_topic_id is not None:
            topic_id = topic_in.existing_topic_id
            last_concept = db.scalar(
                select(func.max(Concept.order)).where(Concept.topic_id == topic_id)
            )
            first_concept_order = 0 if last_concept is None else last_concept + 1
        else:
            topic_id = applier.new_topic(chapter_id, topic_in, next_topic_order)
            next_topic_order += 1
            first_concept_order = 0
        applier.concepts(chapter_id, topic_id, topic_in, first_concept_order)
        # New Concepts are flushed per Topic, so the next existing Topic's max(order) sees them.
        db.flush()


# --- Outline and sources ---


def get_outline(db: Session, user_id: uuid.UUID, course_id: uuid.UUID) -> list[Chapter]:
    """The Course's whole hierarchy in three queries, not one per row."""
    get_owned_course(db, user_id, course_id)
    stmt = (
        select(Chapter)
        .where(Chapter.course_id == course_id)
        .order_by(Chapter.order, Chapter.created_at)
        .options(selectinload(Chapter.topics).selectinload(Topic.concepts))
        .execution_options(populate_existing=True)
    )
    return list(db.scalars(stmt).all())


def list_concept_sources(
    db: Session, user_id: uuid.UUID, concept_id: uuid.UUID
) -> list[DocumentChunk]:
    """The passages a Concept was derived from, for "View source" (spec §18, §66)."""
    concept = get_owned_concept(db, user_id, concept_id)
    stmt = (
        select(DocumentChunk)
        .join(ConceptSource, ConceptSource.chunk_id == DocumentChunk.id)
        .where(
            ConceptSource.concept_id == concept.id,
            ConceptSource.course_id == concept.course_id,
            DocumentChunk.course_id == concept.course_id,
        )
        .order_by(ConceptSource.created_at, DocumentChunk.position)
    )
    return list(db.scalars(stmt).all())
