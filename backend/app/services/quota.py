"""Daily AI limits and the storage limit per account.

Each AI-backed request counts once against its account for the UTC day (kind "evaluation" or
"generation"), stored in `ai_usage` so restarts don't reset it. An account's limit is its own
override, else the server default. Administrators have no limit. Because the provider's free
quota is shared by everybody, an optional guard stops everyone but administrators once the day's
total comes within the reserve of the shared cap.
"""

import uuid
from collections.abc import Callable
from datetime import UTC, date, datetime

from fastapi import Depends
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.auth.dependencies import get_current_user
from app.core.config import get_settings
from app.core.errors import QuotaExceededError, StorageQuotaExceededError
from app.db.session import get_db
from app.models.auth import AiUsage
from app.models.course import Course
from app.models.document import Document
from app.models.user import User

EVALUATION = "evaluation"
GENERATION = "generation"


def today() -> date:
    return datetime.now(UTC).date()


def limit_for(user: User, kind: str) -> int:
    settings = get_settings()
    if kind == EVALUATION:
        own, default = user.limit_evaluations, settings.ai_daily_evaluations
    else:
        own, default = user.limit_generations, settings.ai_daily_generations
    return default if own is None else own


def used_today(db: Session, user_id: uuid.UUID, kind: str) -> int:
    return (
        db.scalar(
            select(AiUsage.count).where(
                AiUsage.user_id == user_id, AiUsage.day == today(), AiUsage.kind == kind
            )
        )
        or 0
    )


def total_today(db: Session) -> int:
    return (
        db.scalar(select(func.coalesce(func.sum(AiUsage.count), 0)).where(AiUsage.day == today()))
        or 0
    )


def charge(db: Session, user: User, kind: str) -> None:
    """Counts one request or raises QuotaExceededError (429) when the account, or the shared
    quota, has nothing left today."""
    settings = get_settings()
    row = db.scalar(
        select(AiUsage).where(
            AiUsage.user_id == user.id, AiUsage.day == today(), AiUsage.kind == kind
        )
    )
    used = row.count if row else 0
    if not user.is_admin:
        if used >= limit_for(user, kind):
            raise QuotaExceededError(
                "You have used today's AI allowance. It renews at midnight UTC.",
                details={"reason": "daily_limit", "kind": kind},
            )
        cap = settings.ai_shared_daily_cap
        if cap and total_today(db) >= cap * (100 - settings.ai_admin_reserve_percent) // 100:
            raise QuotaExceededError(
                "The shared AI allowance for today is nearly used up. Try again tomorrow.",
                details={"reason": "shared_limit", "kind": kind},
            )
    if row is None:
        row = AiUsage(user_id=user.id, day=today(), kind=kind, count=0)
        db.add(row)
    row.count += 1
    db.commit()


def ai_quota(kind: str) -> Callable[..., None]:
    """A route dependency: counts the request against the account's daily AI allowance."""

    def dependency(user: User = Depends(get_current_user), db: Session = Depends(get_db)) -> None:
        charge(db, user, kind)

    return dependency


def storage_used_bytes(db: Session, user_id: uuid.UUID) -> int:
    return (
        db.scalar(
            select(func.coalesce(func.sum(Document.size_bytes), 0))
            .join(Course, Course.id == Document.course_id)
            .where(Course.user_id == user_id)
        )
        or 0
    )


def storage_limit_bytes(user: User) -> int:
    """0 means unlimited."""
    mb = (
        user.limit_storage_mb
        if user.limit_storage_mb is not None
        else get_settings().storage_limit_mb
    )
    return mb * 1024 * 1024


def check_storage(db: Session, user_id: uuid.UUID, new_bytes: int) -> None:
    user = db.get(User, user_id)
    if user is None or user.is_admin:
        return
    limit = storage_limit_bytes(user)
    if limit and storage_used_bytes(db, user_id) + new_bytes > limit:
        raise StorageQuotaExceededError(
            f"This would pass your storage limit of {limit // (1024 * 1024)} MB. "
            "Delete material you no longer need, or ask the administrator.",
            details={"reason": "storage_limit"},
        )
