"""Where Knowledge Repository files live (docs/PROJECT_SPEC.md §16, §70; docs/DEPLOYMENT.md §3).

Services depend on the DocumentStorage protocol. STORAGE_BACKEND picks the implementation:
- local: a directory. Survives restarts; survives redeploys only on a persistent volume.
- s3: a private bucket on any S3-compatible service. Objects are never public: the API streams
  a file only after checking that the signed-in user owns its Course.

Keys are built only from server-generated ids, never from the user's filename.
"""

import os
import uuid
from dataclasses import dataclass
from datetime import UTC, datetime
from functools import lru_cache
from pathlib import Path
from typing import Any, Protocol

from app.core.config import Settings, get_settings


@dataclass(frozen=True)
class StoredFile:
    key: str
    modified_at: datetime


class DocumentStorage(Protocol):
    def save(self, key: str, data: bytes) -> None: ...

    def load(self, key: str) -> bytes: ...

    def delete(self, key: str) -> None: ...

    def list(self, prefix: str) -> list[StoredFile]:
        """Every file whose key starts with `prefix` (a directory-like prefix ending in "/")."""
        ...


class StoredFileMissingError(Exception):
    """The database has the document but the storage doesn't have its file."""


def document_storage_key(course_id: uuid.UUID, document_id: uuid.UUID) -> str:
    # Built only from server-generated ids — never from the user's filename — so an upload can't
    # choose where it lands.
    return f"courses/{course_id}/documents/{document_id}"


class LocalDocumentStorage:
    def __init__(self, root: Path) -> None:
        self._root = root.resolve()

    def _path(self, key: str) -> Path:
        path = (self._root / key).resolve()
        # Defense in depth: keys are server-generated, but never touch anything outside the root.
        if not path.is_relative_to(self._root):
            raise ValueError("storage key escapes the storage root")
        return path

    def save(self, key: str, data: bytes) -> None:
        path = self._path(key)
        path.parent.mkdir(parents=True, exist_ok=True)
        # Write-then-rename, so a crash mid-write never leaves a truncated file under the key.
        tmp = path.with_name(path.name + ".partial")
        try:
            tmp.write_bytes(data)
            os.replace(tmp, path)
        finally:
            # A failed write (disk full, permissions) leaves no temporary file behind.
            tmp.unlink(missing_ok=True)

    def load(self, key: str) -> bytes:
        try:
            return self._path(key).read_bytes()
        except FileNotFoundError as exc:
            raise StoredFileMissingError(key) from exc

    def delete(self, key: str) -> None:
        self._path(key).unlink(missing_ok=True)

    def list(self, prefix: str) -> list[StoredFile]:
        folder = self._path(prefix)
        if not folder.is_dir():
            return []
        return [
            StoredFile(
                key=path.relative_to(self._root).as_posix(),
                modified_at=datetime.fromtimestamp(path.stat().st_mtime, UTC),
            )
            for path in folder.rglob("*")
            if path.is_file() and not path.name.endswith(".partial")
        ]


class S3DocumentStorage:
    """Private objects in an S3-compatible bucket. `client` is a boto3 S3 client (injected, so
    tests can use botocore's Stubber)."""

    def __init__(self, client: Any, bucket: str, prefix: str = "") -> None:
        self._client = client
        self._bucket = bucket
        self._prefix = prefix

    def _key(self, key: str) -> str:
        return f"{self._prefix}{key}"

    def save(self, key: str, data: bytes) -> None:
        self._client.put_object(Bucket=self._bucket, Key=self._key(key), Body=data)

    def load(self, key: str) -> bytes:
        try:
            response = self._client.get_object(Bucket=self._bucket, Key=self._key(key))
        except self._client.exceptions.NoSuchKey as exc:
            raise StoredFileMissingError(key) from exc
        body: bytes = response["Body"].read()
        return body

    def delete(self, key: str) -> None:
        # S3 deletes are idempotent: deleting a missing key succeeds.
        self._client.delete_object(Bucket=self._bucket, Key=self._key(key))

    def list(self, prefix: str) -> list[StoredFile]:
        files = []
        pages = self._client.get_paginator("list_objects_v2").paginate(
            Bucket=self._bucket, Prefix=self._key(prefix)
        )
        for page in pages:
            for item in page.get("Contents", []):
                files.append(
                    StoredFile(
                        key=item["Key"][len(self._prefix) :], modified_at=item["LastModified"]
                    )
                )
        return files


def build_storage(settings: Settings) -> DocumentStorage:
    if settings.storage_backend == "s3":
        import boto3  # only needed when S3 is configured

        client = boto3.client(
            "s3",
            endpoint_url=settings.storage_endpoint or None,
            region_name=settings.storage_region or None,
            aws_access_key_id=settings.storage_access_key_id or None,
            aws_secret_access_key=settings.storage_secret_access_key.get_secret_value() or None,
        )
        return S3DocumentStorage(client, settings.storage_bucket, settings.storage_prefix)
    return LocalDocumentStorage(settings.storage_local_dir)


@lru_cache
def _configured_storage() -> DocumentStorage:
    return build_storage(get_settings())


def get_document_storage() -> DocumentStorage:
    """FastAPI dependency (tests override it with a temporary directory)."""
    return _configured_storage()
