"""Knowledge Repository endpoints (docs/PROJECT_SPEC.md §16-18, §66)."""

import uuid
from urllib.parse import quote

from fastapi import (
    APIRouter,
    BackgroundTasks,
    Depends,
    File,
    Form,
    Query,
    Response,
    UploadFile,
    status,
)
from sqlalchemy.orm import Session, sessionmaker

from app.auth.dependencies import get_current_user
from app.core.config import get_settings
from app.core.errors import PayloadTooLargeError
from app.core.rate_limit import per_user
from app.db.session import get_db, get_session_factory
from app.models.document import Document, DocumentChunk
from app.models.enums import DocumentPurpose
from app.models.user import User
from app.schemas.documents import ChunkRead, DocumentRead, DocumentUpdate
from app.services.documents import service
from app.storage.documents import DocumentStorage, get_document_storage

router = APIRouter(tags=["documents"])

CurrentUser = Depends(get_current_user)
DB = Depends(get_db)
Storage = Depends(get_document_storage)


def get_max_upload_bytes() -> int:
    """A dependency so tests can lower the limit instead of uploading 50 MB."""
    return get_settings().max_upload_mb * 1024 * 1024


@router.post(
    "/courses/{course_id}/documents",
    response_model=DocumentRead,
    status_code=status.HTTP_202_ACCEPTED,
    dependencies=[Depends(per_user("upload", 60, 3600))],
)
def upload_document(
    course_id: uuid.UUID,
    background_tasks: BackgroundTasks,
    file: UploadFile = File(...),
    chapter_id: uuid.UUID | None = Form(default=None),
    purpose: DocumentPurpose = Form(default=DocumentPurpose.MATERIAL),
    db: Session = DB,
    user: User = CurrentUser,
    storage: DocumentStorage = Storage,
    session_factory: sessionmaker[Session] = Depends(get_session_factory),
    max_bytes: int = Depends(get_max_upload_bytes),
) -> Document:
    """Stores the file and returns immediately (202) with status PROCESSING; poll
    GET /documents/{id} until it is READY or FAILED. Optional form field `chapter_id` files it
    under a Chapter of this Course.

    Form field `purpose`: MATERIAL (default) is study material for curriculum generation.
    QUESTION_BANK holds the user's own questions and expected answers, labelled "Domanda:" /
    "Risposta:" (or "Question:" / "Answer:"). Each pair becomes a NOT_STUDIED Concept with one
    Learning Item, under `chapter_id` or a new Chapter named after the file."""
    data = file.file.read(max_bytes + 1)
    if len(data) > max_bytes:
        raise PayloadTooLargeError(
            f"Files are limited to {max_bytes // (1024 * 1024)} MB.",
            details={"max_bytes": max_bytes},
        )
    document = service.upload_document(
        db, storage, user.id, course_id, file.filename, data, chapter_id, purpose
    )
    background_tasks.add_task(service.process_document, session_factory, storage, document.id)
    return document


@router.get("/courses/{course_id}/documents", response_model=list[DocumentRead])
def list_documents(
    course_id: uuid.UUID,
    chapter_id: uuid.UUID | None = Query(default=None),
    db: Session = DB,
    user: User = CurrentUser,
) -> list[Document]:
    return service.list_documents(db, user.id, course_id, chapter_id)


@router.patch("/documents/{document_id}", response_model=DocumentRead)
def update_document(
    document_id: uuid.UUID, payload: DocumentUpdate, db: Session = DB, user: User = CurrentUser
) -> Document:
    return service.update_document(db, user.id, document_id, payload.chapter_id)


@router.get("/documents/{document_id}", response_model=DocumentRead)
def get_document(document_id: uuid.UUID, db: Session = DB, user: User = CurrentUser) -> Document:
    return service.get_owned_document(db, user.id, document_id)


@router.get(
    "/documents/{document_id}/file",
    response_class=Response,
    responses={200: {"content": {"application/octet-stream": {}}}},
)
def download_document(
    document_id: uuid.UUID,
    db: Session = DB,
    user: User = CurrentUser,
    storage: DocumentStorage = Storage,
) -> Response:
    """The original file, to its owner only (404 for anyone else, as for a missing id). Always
    an attachment, never rendered inline, so an uploaded HTML or SVG can't run in the app's
    origin. There are no public or pre-signed URLs: every download passes this check."""
    document = service.get_owned_document(db, user.id, document_id)
    data = service.load_original(storage, document)
    ascii_name = document.filename.encode("ascii", "replace").decode().replace('"', "'")
    return Response(
        content=data,
        media_type="application/octet-stream",
        headers={
            "Content-Disposition": (
                f'attachment; filename="{ascii_name}"; '
                f"filename*=UTF-8''{quote(document.filename)}"
            ),
            "X-Content-Type-Options": "nosniff",
            "Cache-Control": "private, no-store",
        },
    )


@router.delete("/documents/{document_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_document(
    document_id: uuid.UUID,
    db: Session = DB,
    user: User = CurrentUser,
    storage: DocumentStorage = Storage,
) -> None:
    service.delete_document(db, storage, user.id, document_id)


@router.get("/documents/{document_id}/chunks", response_model=list[ChunkRead])
def list_chunks(
    document_id: uuid.UUID,
    offset: int = Query(default=0, ge=0),
    limit: int = Query(default=50, ge=1, le=200),
    db: Session = DB,
    user: User = CurrentUser,
) -> list[DocumentChunk]:
    return service.list_chunks(db, user.id, document_id, offset, limit)


@router.get("/documents/{document_id}/chunks/{chunk_id}", response_model=ChunkRead)
def get_chunk(
    document_id: uuid.UUID,
    chunk_id: uuid.UUID,
    db: Session = DB,
    user: User = CurrentUser,
) -> DocumentChunk:
    return service.get_chunk(db, user.id, document_id, chunk_id)
