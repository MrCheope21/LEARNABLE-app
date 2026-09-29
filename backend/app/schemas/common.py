from datetime import UTC, datetime
from typing import Annotated, Self

from pydantic import BaseModel, ConfigDict, PlainSerializer, model_validator


def _format_utc_timestamp(value: datetime) -> str:
    return value.astimezone(UTC).isoformat(timespec="milliseconds").replace("+00:00", "Z")


# API timestamp contract (docs/API.md): UTC, millisecond precision, "Z" suffix — e.g.
# "2026-09-23T08:42:33.720Z". Fixed so clients (iOS ISO8601DateFormatter) parse it reliably.
UTCTimestamp = Annotated[
    datetime, PlainSerializer(_format_utc_timestamp, return_type=str, when_used="json")
]


class InputModel(BaseModel):
    """Base for request bodies: trims whitespace and rejects unknown fields, so a typo'd or
    unexpected key (e.g. a client trying to send `user_id`) is a 422 instead of silently ignored."""

    model_config = ConfigDict(str_strip_whitespace=True, extra="forbid")


class PatchModel(InputModel):
    """Base for PATCH bodies: omitted fields are left unchanged, explicit nulls are rejected.

    Every patchable column is NOT NULL, so accepting `{"title": null}` would otherwise surface as
    a database integrity error (500) instead of a validation error (422).
    """

    @model_validator(mode="after")
    def _reject_explicit_nulls(self) -> Self:
        null_fields = sorted(f for f in self.model_fields_set if getattr(self, f) is None)
        if null_fields:
            raise ValueError(f"fields cannot be null: {', '.join(null_fields)}")
        return self
