"""In-app notifications: written by the service where the thing happens, in the same
transaction, and read by the bell in the app. Kinds and their `data`:

    friend_request      {}                                   actor = who asked
    friend_accepted     {}                                   actor = who accepted
    course_update       {listing_id, title, version, note}   actor = the author
    course_announcement {listing_id, title, message}         actor = the author
    course_review       {listing_id, title, rating}          actor = the reviewer
    review_reply        {listing_id, title}                  actor = the author
    course_sold         {listing_id, title, amount_cents, currency}   actor = the buyer
    order_refunded      {listing_id, title, amount_cents, currency}   actor = the author
    course_new          {listing_id, title, tag}             actor = the author; `tag` is the
                        followed tag that matched (services/interests.py)
"""

import uuid
from typing import Any

from sqlalchemy import delete, func, select, update
from sqlalchemy.orm import Session

from app.db.types import utc_now
from app.models.community import Notification
from app.models.user import User
from app.schemas.community import NotificationRead, Notifications

LIST_LIMIT = 50
# Per user; older ones go when a new one arrives.
KEEP = 200


def notify(
    db: Session,
    user_id: uuid.UUID,
    kind: str,
    *,
    actor_id: uuid.UUID | None = None,
    data: dict[str, Any] | None = None,
    link: str = "",
) -> None:
    """Adds a notification (the caller commits)."""
    db.add(Notification(user_id=user_id, kind=kind, actor_id=actor_id, data=data or {}, link=link))


def withdraw(db: Session, user_id: uuid.UUID, kind: str, actor_id: uuid.UUID) -> None:
    """Removes what is no longer true, e.g. a friend request that was cancelled."""
    db.execute(
        delete(Notification).where(
            Notification.user_id == user_id,
            Notification.kind == kind,
            Notification.actor_id == actor_id,
        )
    )


def unread_count(db: Session, user_id: uuid.UUID) -> int:
    return int(
        db.scalar(
            select(func.count())
            .select_from(Notification)
            .where(Notification.user_id == user_id, Notification.read_at.is_(None))
        )
        or 0
    )


def listed(db: Session, user: User) -> Notifications:
    rows = db.scalars(
        select(Notification)
        .where(Notification.user_id == user.id)
        .order_by(Notification.created_at.desc(), Notification.id)
        .limit(LIST_LIMIT)
    ).all()
    actor_ids = {row.actor_id for row in rows if row.actor_id}
    names: dict[uuid.UUID, str | None] = {}
    if actor_ids:
        names = {
            user_id: display_name or (f"@{username}" if username else None)
            for user_id, display_name, username in db.execute(
                select(User.id, User.display_name, User.username).where(User.id.in_(actor_ids))
            ).all()
        }
    _trim(db, user.id)
    return Notifications(
        items=[
            NotificationRead(
                id=row.id,
                kind=row.kind,
                actor=(names.get(row.actor_id) or None) if row.actor_id else None,
                data=dict(row.data or {}),
                link=row.link,
                created_at=row.created_at,
                read=row.read_at is not None,
            )
            for row in rows
        ],
        unread=unread_count(db, user.id),
    )


def mark_read(db: Session, user_id: uuid.UUID, ids: list[uuid.UUID] | None = None) -> None:
    """All of them, or the listed ones."""
    stmt = (
        update(Notification)
        .where(Notification.user_id == user_id, Notification.read_at.is_(None))
        .values(read_at=utc_now())
    )
    if ids is not None:
        stmt = stmt.where(Notification.id.in_(ids))
    db.execute(stmt)
    db.commit()


def _trim(db: Session, user_id: uuid.UUID) -> None:
    old = db.scalars(
        select(Notification.id)
        .where(Notification.user_id == user_id)
        .order_by(Notification.created_at.desc(), Notification.id)
        .offset(KEEP)
    ).all()
    if old:
        db.execute(delete(Notification).where(Notification.id.in_(old)))
        db.commit()
