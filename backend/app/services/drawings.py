"""Drawn answers: image checks and where the files live.

A reference drawing belongs to a Learning Item; a drawn answer to an Answer. Both are stored with
the Course's other files (DocumentStorage), under keys derived from their ids, and only served
after an ownership check.
"""

import base64
import binascii
import logging
import re
import uuid
from datetime import datetime, timedelta

from sqlalchemy import select
from sqlalchemy.orm import Session, sessionmaker

from app.core.errors import (
    InvalidRequestError,
    NotFoundError,
    PayloadTooLargeError,
    UnsupportedMediaTypeError,
)
from app.db.types import utc_now
from app.models.learning import LearningItem
from app.models.review import Answer
from app.services import managed_courses
from app.services.courses.service import get_owned_course
from app.services.learning.service import get_owned_item
from app.storage.documents import DocumentStorage, StoredFileMissingError

MAX_DRAWING_BYTES = 3 * 1024 * 1024
_DATA_URL = re.compile(r"^data:image/[a-z+.-]+;base64,(?P<data>[A-Za-z0-9+/=\s]+)$")


def image_type(data: bytes) -> str:
    """The media type, read from the bytes themselves (never from a name or a header)."""
    if len(data) > MAX_DRAWING_BYTES:
        raise PayloadTooLargeError("The drawing is too large (3 MB at most).")
    if data.startswith(b"\x89PNG\r\n\x1a\n"):
        return "image/png"
    if data.startswith(b"\xff\xd8\xff"):
        return "image/jpeg"
    if data[:4] == b"RIFF" and data[8:12] == b"WEBP":
        return "image/webp"
    raise UnsupportedMediaTypeError("A drawing must be a PNG, JPEG or WebP image.")


def decode_data_url(value: str) -> tuple[bytes, str]:
    """A drawing sent inline by the browser ("data:image/png;base64,...")."""
    match = _DATA_URL.match(value.strip())
    if match is None:
        raise InvalidRequestError("The drawing isn't a valid image.")
    try:
        data = base64.b64decode(match.group("data"), validate=False)
    except (binascii.Error, ValueError) as exc:
        raise InvalidRequestError("The drawing isn't a valid image.") from exc
    return data, image_type(data)


def reference_key(item: LearningItem) -> str:
    return f"courses/{item.course_id}/drawings/items/{item.id}"


def answer_key(answer: Answer) -> str:
    return f"courses/{answer.course_id}/drawings/answers/{answer.id}"


# --- Reference drawings (the answer a drawing question expects) ---


def set_reference(
    db: Session, storage: DocumentStorage, user_id: uuid.UUID, item_id: uuid.UUID, data: bytes
) -> LearningItem:
    """Makes the item a drawing question with this reference drawing (replacing any earlier one)."""
    item = get_owned_item(db, user_id, item_id)
    managed_courses.ensure_editable(get_owned_course(db, user_id, item.course_id))
    media_type = image_type(data)
    storage.save(reference_key(item), data)
    item.answer_format = "DRAWING"
    item.reference_drawing_type = media_type
    db.commit()
    db.refresh(item)
    return item


def remove_reference(
    db: Session, storage: DocumentStorage, user_id: uuid.UUID, item_id: uuid.UUID
) -> LearningItem:
    """Back to a text question. Drawn answers already given keep their own images."""
    item = get_owned_item(db, user_id, item_id)
    managed_courses.ensure_editable(get_owned_course(db, user_id, item.course_id))
    if item.reference_drawing_type is not None:
        storage.delete(reference_key(item))
    item.answer_format = "TEXT"
    item.reference_drawing_type = None
    db.commit()
    db.refresh(item)
    return item


def load_reference(
    db: Session, storage: DocumentStorage, user_id: uuid.UUID, item_id: uuid.UUID
) -> tuple[bytes, str]:
    item = get_owned_item(db, user_id, item_id)
    if item.reference_drawing_type is None:
        raise NotFoundError("This question has no reference drawing.")
    return _load(storage, reference_key(item)), item.reference_drawing_type


def load_answer_drawing(
    db: Session, storage: DocumentStorage, user_id: uuid.UUID, answer_id: uuid.UUID
) -> tuple[bytes, str]:
    answer = db.get(Answer, answer_id)
    if answer is None or answer.user_id != user_id or answer.drawing_type is None:
        raise NotFoundError("Drawing not found")
    get_owned_course(db, user_id, answer.course_id)
    return _load(storage, answer_key(answer)), answer.drawing_type


def _load(storage: DocumentStorage, key: str) -> bytes:
    try:
        return storage.load(key)
    except StoredFileMissingError as exc:
        raise NotFoundError("The drawing file is missing.") from exc


def course_drawing_keys(db: Session, course_id: uuid.UUID) -> list[str]:
    """Every drawing file of a Course, so deleting the Course deletes them too (spec §70)."""
    items = db.scalars(
        select(LearningItem).where(
            LearningItem.course_id == course_id, LearningItem.reference_drawing_type.is_not(None)
        )
    )
    answers = db.scalars(
        select(Answer).where(Answer.course_id == course_id, Answer.drawing_type.is_not(None))
    )
    return [*(reference_key(i) for i in items), *(answer_key(a) for a in answers)]


# --- Files left behind ---

# A drawing is saved just before its answer row is committed; younger files are left alone.
SWEEP_MIN_AGE = timedelta(minutes=10)
logger = logging.getLogger(__name__)


def sweep(
    db: Session, storage: DocumentStorage, course_id: uuid.UUID, now: datetime | None = None
) -> int:
    """Deletes the Course's drawing files that no question or answer has any more: deleting a
    question, concept, topic or chapter removes rows by cascade, not their files. Returns how
    many went."""
    kept = set(course_drawing_keys(db, course_id))
    oldest = (now or utc_now()) - SWEEP_MIN_AGE
    gone = 0
    for stored in storage.list(f"courses/{course_id}/drawings/"):
        if stored.key not in kept and stored.modified_at <= oldest:
            storage.delete(stored.key)
            gone += 1
    return gone


def sweep_job(
    session_factory: sessionmaker[Session], storage: DocumentStorage, course_id: uuid.UUID
) -> None:
    """`sweep` as a background task, after a request that deleted questions."""
    try:
        with session_factory() as db:
            gone = sweep(db, storage, course_id)
        if gone:
            logger.info("drawings course=%s swept=%d", course_id, gone)
    except Exception:
        # Housekeeping: a failure here must never surface to the user; the next sweep retries.
        logger.exception("drawings sweep failed course=%s", course_id)
