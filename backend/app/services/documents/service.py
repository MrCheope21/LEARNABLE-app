"""Knowledge Repository: upload and the ingestion pipeline (docs/PROJECT_SPEC.md §16-18).

UPLOAD (request) → EXTRACT → CLEAN → CHUNK → store (background task). Upload returns as soon as
the file is safely stored; the document is PROCESSING until the pipeline marks it READY or FAILED.
ASSOCIATE (linking chunks to Concepts) and RETRIEVE arrive with curriculum generation (Phase 6).

Privacy (spec §70, §94): document content is never logged — only ids and error types.
"""

import hashlib
import logging
import uuid

from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session, sessionmaker

from app.core.errors import ConflictError, NotFoundError, UnsupportedMediaTypeError
from app.models.course import Chapter, Concept
from app.models.curriculum import ConceptSource
from app.models.document import Document, DocumentChunk
from app.models.enums import DocumentKind, DocumentPurpose, DocumentStatus
from app.services.courses.service import get_owned_course
from app.services.documents.chunking import chunk_blocks
from app.services.documents.detection import SUPPORTED_DESCRIPTION, clean_filename, detect_type
from app.services.documents.extraction import ExtractionError, extract
from app.services.question_banks.importing import NoQuestionsFoundError, import_question_bank
from app.storage.documents import (
    DocumentStorage,
    StoredFileMissingError,
    document_storage_key,
)

logger = logging.getLogger(__name__)

_NO_TEXT = (
    "No text could be found in this document. If it's a scan or a photo, text recognition "
    "isn't supported yet."
)
_UNEXPECTED_FAILURE = "This file couldn't be processed."
# Question banks are read by their text labels, so they need a text format (not images or slides).
_QUESTION_BANK_KINDS = {
    DocumentKind.PDF,
    DocumentKind.DOCX,
    DocumentKind.TEXT,
    DocumentKind.MARKDOWN,
}


def upload_document(
    db: Session,
    storage: DocumentStorage,
    user_id: uuid.UUID,
    course_id: uuid.UUID,
    filename: str | None,
    data: bytes,
    chapter_id: uuid.UUID | None = None,
    purpose: DocumentPurpose = DocumentPurpose.MATERIAL,
) -> Document:
    get_owned_course(db, user_id, course_id)
    if chapter_id is not None:
        _check_chapter(db, course_id, chapter_id)
    if not data:
        raise UnsupportedMediaTypeError("The file is empty.")
    detected = detect_type(filename or "", data)
    if detected is None:
        raise UnsupportedMediaTypeError(
            f"This file type isn't supported. Supported: {SUPPORTED_DESCRIPTION}."
        )
    if purpose is DocumentPurpose.QUESTION_BANK and detected.kind not in _QUESTION_BANK_KINDS:
        raise UnsupportedMediaTypeError(
            "Questions and answers can be imported from PDF, Word (.docx), text (.txt) or "
            "Markdown (.md) files."
        )

    sha256 = hashlib.sha256(data).hexdigest()
    existing = db.scalar(
        select(Document.id).where(Document.course_id == course_id, Document.sha256 == sha256)
    )
    if existing is not None:
        raise ConflictError(
            "This file is already in the course.", details={"document_id": str(existing)}
        )

    document_id = uuid.uuid4()
    document = Document(
        id=document_id,
        course_id=course_id,
        chapter_id=chapter_id,
        filename=clean_filename(filename),
        mime_type=detected.mime_type,
        kind=detected.kind,
        purpose=purpose,
        size_bytes=len(data),
        sha256=sha256,
        storage_key=document_storage_key(course_id, document_id),
        status=DocumentStatus.PROCESSING,
    )
    # File first, then the row: a crash in between leaves an orphan file (harmless), never a
    # row pointing at a missing file.
    storage.save(document.storage_key, data)
    db.add(document)
    try:
        db.commit()
    except IntegrityError as exc:
        # Same file uploaded twice concurrently: the unique (course_id, sha256) index decides.
        db.rollback()
        storage.delete(document.storage_key)
        raise ConflictError("This file is already in the course.") from exc
    except Exception:
        db.rollback()
        storage.delete(document.storage_key)
        raise
    db.refresh(document)
    return document


def process_document(
    session_factory: sessionmaker[Session], storage: DocumentStorage, document_id: uuid.UUID
) -> None:
    """Background task: extract → clean → chunk → store. Opens its own session because it runs
    after the request's session has closed."""
    with session_factory() as db:
        document = db.get(Document, document_id)
        if document is None or document.status is not DocumentStatus.PROCESSING:
            return  # deleted, or already processed

        try:
            extraction = extract(document.kind, storage.load(document.storage_key))
            if document.purpose is DocumentPurpose.QUESTION_BANK:
                imported = import_question_bank(db, document, extraction.blocks)
                document.page_count = extraction.page_count
                document.chunk_count = imported.pairs
                document.import_notice = imported.notice
                document.source_created_at = extraction.source_created_at
                document.status = DocumentStatus.READY
                _commit_processed(db)
                return
            chunks = chunk_blocks(extraction.blocks)
            if not chunks:
                raise ExtractionError(_NO_TEXT)
        except (ExtractionError, NoQuestionsFoundError) as exc:
            db.rollback()
            _mark_failed(db, document, str(exc))
            return
        except Exception:
            logger.exception("Unexpected failure processing document %s", document_id)
            db.rollback()
            _mark_failed(db, document, _UNEXPECTED_FAILURE)
            return

        db.add_all(
            DocumentChunk(
                document_id=document.id,
                course_id=document.course_id,
                position=position,
                page_number=chunk.page,
                page_end=chunk.page_end,
                section=chunk.section,
                paragraph_start=chunk.paragraph_start,
                paragraph_end=chunk.paragraph_end,
                text=chunk.text,
            )
            for position, chunk in enumerate(chunks)
        )
        document.page_count = extraction.page_count
        document.chunk_count = len(chunks)
        document.source_created_at = extraction.source_created_at
        document.status = DocumentStatus.READY
        _commit_processed(db)


def _commit_processed(db: Session) -> None:
    try:
        db.commit()
    except IntegrityError:
        db.rollback()  # the document (or its Course) was deleted while it was being processed


def _mark_failed(db: Session, document: Document, reason: str) -> None:
    document.status = DocumentStatus.FAILED
    document.error_message = reason[:500]
    try:
        db.commit()
    except IntegrityError:
        db.rollback()


def _check_chapter(db: Session, course_id: uuid.UUID, chapter_id: uuid.UUID) -> None:
    chapter = db.get(Chapter, chapter_id)
    if chapter is None or chapter.course_id != course_id:
        # Same answer for another Course's Chapter and a nonexistent one (spec §10).
        raise NotFoundError("Chapter not found")


def list_documents(
    db: Session, user_id: uuid.UUID, course_id: uuid.UUID, chapter_id: uuid.UUID | None = None
) -> list[Document]:
    get_owned_course(db, user_id, course_id)
    stmt = select(Document).where(Document.course_id == course_id).order_by(Document.created_at)
    if chapter_id is not None:
        stmt = stmt.where(Document.chapter_id == chapter_id)
    return list(db.scalars(stmt).all())


def update_document(
    db: Session, user_id: uuid.UUID, document_id: uuid.UUID, chapter_id: uuid.UUID | None
) -> Document:
    document = get_owned_document(db, user_id, document_id)
    if chapter_id is not None:
        _check_chapter(db, document.course_id, chapter_id)
    if chapter_id != document.chapter_id:
        document.chapter_id = chapter_id
        document.analyzed_at = None
    db.commit()
    db.refresh(document)
    return document


def load_original(storage: DocumentStorage, document: Document) -> bytes:
    """The uploaded bytes. A row whose file is gone (lost volume, manual deletion) is reported
    as such rather than as a server error."""
    try:
        return storage.load(document.storage_key)
    except StoredFileMissingError as exc:
        logger.error("Stored file missing for document %s", document.id)
        raise NotFoundError(
            "The original file is no longer in storage.", details={"reason": "file_missing"}
        ) from exc


def get_owned_document(db: Session, user_id: uuid.UUID, document_id: uuid.UUID) -> Document:
    document = db.get(Document, document_id)
    if document is None:
        raise NotFoundError("Document not found")
    get_owned_course(db, user_id, document.course_id)
    return document


def delete_document(
    db: Session, storage: DocumentStorage, user_id: uuid.UUID, document_id: uuid.UUID
) -> None:
    document = get_owned_document(db, user_id, document_id)
    key = document.storage_key
    _flag_concepts_losing_their_last_source(db, document)
    db.delete(document)
    db.commit()
    # After the commit: if this fails, an orphan file remains, but no row points to nothing.
    storage.delete(key)


def _flag_concepts_losing_their_last_source(db: Session, document: Document) -> None:
    """Concepts whose every source passage is in this document are about to have none. They
    are kept (the user decides), but flagged `needs_source_review`. Revised material that
    re-links them clears the flag."""
    in_document = select(DocumentChunk.id).where(DocumentChunk.document_id == document.id)
    affected = select(ConceptSource.concept_id).where(ConceptSource.chunk_id.in_(in_document))
    keeping_a_source = select(ConceptSource.concept_id).where(
        ConceptSource.concept_id.in_(affected), ConceptSource.chunk_id.not_in(in_document)
    )
    for concept in db.scalars(
        select(Concept).where(
            Concept.course_id == document.course_id,
            Concept.id.in_(affected),
            Concept.id.not_in(keeping_a_source),
        )
    ):
        concept.needs_source_review = True


def delete_course_files(storage: DocumentStorage, keys: list[str]) -> None:
    """Remove a deleted Course's files (spec §70: deleting data really deletes it)."""
    for key in keys:
        try:
            storage.delete(key)
        except Exception:
            logger.exception("Could not delete stored file for a deleted course")


def list_chunks(
    db: Session, user_id: uuid.UUID, document_id: uuid.UUID, offset: int, limit: int
) -> list[DocumentChunk]:
    get_owned_document(db, user_id, document_id)
    stmt = (
        select(DocumentChunk)
        .where(DocumentChunk.document_id == document_id)
        .order_by(DocumentChunk.position)
        .offset(offset)
        .limit(limit)
    )
    return list(db.scalars(stmt).all())


def get_chunk(
    db: Session, user_id: uuid.UUID, document_id: uuid.UUID, chunk_id: uuid.UUID
) -> DocumentChunk:
    get_owned_document(db, user_id, document_id)
    chunk = db.get(DocumentChunk, chunk_id)
    if chunk is None or chunk.document_id != document_id:
        raise NotFoundError("Passage not found")
    return chunk
