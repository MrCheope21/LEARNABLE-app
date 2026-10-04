"""Drawn answers: image checks and where the files live.

A reference drawing belongs to a Learning Item; a drawn answer to an Answer. Both are stored with
the Course's other files (DocumentStorage), under keys derived from their ids, and only served
after an ownership check.
"""

import base64
import binascii
import re

from app.core.errors import InvalidRequestError, PayloadTooLargeError, UnsupportedMediaTypeError
from app.models.learning import LearningItem
from app.models.review import Answer

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
