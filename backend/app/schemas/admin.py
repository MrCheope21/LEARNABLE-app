import uuid
from typing import Literal

from pydantic import BaseModel, EmailStr, Field

from app.schemas.common import InputModel, UTCTimestamp

InvitationStatus = Literal["pending", "used", "revoked", "expired"]


class AdminUser(BaseModel):
    id: uuid.UUID
    email: EmailStr
    username: str | None
    display_name: str | None
    created_at: UTCTimestamp
    last_active_at: UTCTimestamp | None
    is_admin: bool
    is_active: bool
    course_count: int
    answer_count: int
    storage_bytes: int
    # Today's AI requests against the day's allowance (a limit of 0 is unlimited for admins).
    evaluations_today: int
    generations_today: int
    evaluations_limit: int
    generations_limit: int
    storage_limit_bytes: int
    # True when the account has its own limits instead of the server's defaults.
    custom_limits: bool


class AdminUserUpdate(InputModel):
    """Omitted: unchanged. A limit set to null goes back to the server default."""

    is_active: bool | None = None
    limit_evaluations: int | None = Field(default=None, ge=0, le=100_000)
    limit_generations: int | None = Field(default=None, ge=0, le=100_000)
    limit_storage_mb: int | None = Field(default=None, ge=0, le=1_000_000)


class AdminSummary(BaseModel):
    users: int
    active_users: int
    ai_requests_today: int
    shared_daily_cap: int
    registration_open: bool
    default_evaluations: int
    default_generations: int
    default_storage_mb: int


class InvitationCreate(InputModel):
    email: EmailStr | None = None
    note: str = Field(default="", max_length=120)
    days: int | None = Field(default=None, ge=1, le=90)


class InvitationRead(BaseModel):
    id: uuid.UUID
    note: str
    email: str | None
    status: InvitationStatus
    created_at: UTCTimestamp
    expires_at: UTCTimestamp
    used_at: UTCTimestamp | None
    used_by_email: str | None


class InvitationCreated(InvitationRead):
    """Returned once, at creation: the code can't be read back afterwards."""

    link: str


class TemporaryPassword(BaseModel):
    password: str
