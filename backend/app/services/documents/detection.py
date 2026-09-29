"""Identify an upload's real type from its bytes (docs/PROJECT_SPEC.md §16).

The client's filename and Content-Type are never trusted for this: an executable renamed to
.pdf must not be treated as a PDF. The extension is used only to tell plain text from Markdown,
which have no magic bytes.
"""

import zipfile
from dataclasses import dataclass
from io import BytesIO
from pathlib import PureWindowsPath

from app.models.enums import DocumentKind


@dataclass(frozen=True)
class DetectedType:
    kind: DocumentKind
    mime_type: str


SUPPORTED_DESCRIPTION = "PDF, Word (.docx), PowerPoint (.pptx), text (.txt), Markdown (.md), images"

_DOCX_MIME = "application/vnd.openxmlformats-officedocument.wordprocessingml.document"
_PPTX_MIME = "application/vnd.openxmlformats-officedocument.presentationml.presentation"
_HEIF_BRANDS = {b"heic", b"heix", b"hevc", b"mif1", b"msf1"}
_TEXT_SNIFF_BYTES = 8192


def detect_type(filename: str, data: bytes) -> DetectedType | None:
    if data.startswith(b"%PDF-"):
        return DetectedType(DocumentKind.PDF, "application/pdf")
    if data.startswith(b"\x89PNG\r\n\x1a\n"):
        return DetectedType(DocumentKind.IMAGE, "image/png")
    if data.startswith(b"\xff\xd8\xff"):
        return DetectedType(DocumentKind.IMAGE, "image/jpeg")
    if data[:4] in (b"II*\x00", b"MM\x00*"):
        return DetectedType(DocumentKind.IMAGE, "image/tiff")
    if data[4:8] == b"ftyp" and data[8:12] in _HEIF_BRANDS:
        # iPhone camera photos.
        return DetectedType(DocumentKind.IMAGE, "image/heic")
    if data.startswith(b"PK\x03\x04"):
        return _detect_office(data)

    suffix = PureWindowsPath(filename).suffix.lower()
    if suffix in {".txt", ".md", ".markdown"} and _looks_like_text(data):
        if suffix == ".txt":
            return DetectedType(DocumentKind.TEXT, "text/plain")
        return DetectedType(DocumentKind.MARKDOWN, "text/markdown")
    return None


def _detect_office(data: bytes) -> DetectedType | None:
    try:
        with zipfile.ZipFile(BytesIO(data)) as archive:
            names = set(archive.namelist())
    except zipfile.BadZipFile:
        return None
    if "word/document.xml" in names:
        return DetectedType(DocumentKind.DOCX, _DOCX_MIME)
    if "ppt/presentation.xml" in names:
        return DetectedType(DocumentKind.PPTX, _PPTX_MIME)
    return None


def _looks_like_text(data: bytes) -> bool:
    # Text files don't contain NUL bytes; binaries almost always do near the start.
    return b"\x00" not in data[:_TEXT_SNIFF_BYTES]


def clean_filename(name: str | None) -> str:
    """The user's filename as display metadata: no directory parts, no control characters."""
    base = PureWindowsPath(name or "").name  # strips both "/" and "\" path components
    base = "".join(ch for ch in base if ch.isprintable()).strip()
    return base[:255] or "untitled"
