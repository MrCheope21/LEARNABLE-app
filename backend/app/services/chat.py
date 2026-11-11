"""Private messages between friends (docs/COMMUNITY.md §4).

Only two friends can write to each other; ending the friendship or blocking stops new
messages and leaves the history readable. Messages are plain text. The app polls: there is no
push channel on the small server this runs on.
"""

import uuid

from sqlalchemy import func, or_, select, update
from sqlalchemy.orm import Session

from app.core.errors import ForbiddenError, NotFoundError
from app.db.types import utc_now
from app.models.community import Message, pair_key
from app.models.user import User
from app.schemas.community import ChatMessage, Conversation, Thread
from app.services import community

PAGE = 50
PREVIEW = 140
ANONYMOUS = community.ANONYMOUS


def _can_send(db: Session, viewer: User, other: User | None) -> bool:
    return (
        other is not None
        and other.is_active
        and community.are_friends(db, viewer.id, other.id)
        and not community.blocked_between(db, viewer.id, other.id)
    )


def unread_count(db: Session, user_id: uuid.UUID) -> int:
    return int(
        db.scalar(
            select(func.count())
            .select_from(Message)
            .where(Message.recipient_id == user_id, Message.read_at.is_(None))
        )
        or 0
    )


def conversations(db: Session, viewer: User) -> list[Conversation]:
    """Every chat the viewer has, the most recent first, then friends never written to."""
    latest = (
        select(Message.pair_key, func.max(Message.created_at).label("last_at"))
        .where(or_(Message.sender_id == viewer.id, Message.recipient_id == viewer.id))
        .group_by(Message.pair_key)
        .subquery()
    )
    rows = db.scalars(
        select(Message)
        .join(
            latest,
            (Message.pair_key == latest.c.pair_key) & (Message.created_at == latest.c.last_at),
        )
        .order_by(Message.created_at.desc())
    ).all()
    unread = dict(
        db.execute(
            select(Message.sender_id, func.count())
            .where(Message.recipient_id == viewer.id, Message.read_at.is_(None))
            .group_by(Message.sender_id)
        )
        .tuples()
        .all()
    )
    seen: set[uuid.UUID] = set()
    result: list[Conversation] = []
    for row in rows:
        other_id = row.recipient_id if row.sender_id == viewer.id else row.sender_id
        if other_id in seen:
            continue  # two messages in the same instant
        seen.add(other_id)
        other = db.get(User, other_id)
        result.append(
            Conversation(
                user_id=other_id,
                name=(other.display_name if other else None) or ANONYMOUS,
                last_message=row.body[:PREVIEW],
                last_mine=row.sender_id == viewer.id,
                last_at=row.created_at,
                unread=int(unread.get(other_id, 0)),
                can_send=_can_send(db, viewer, other),
            )
        )
    return result


def thread(
    db: Session, viewer: User, user_id: uuid.UUID, before: uuid.UUID | None = None
) -> Thread:
    """The messages with one person, oldest first (the latest page, or the page before a
    message). Reading it marks what they sent as read."""
    other = db.get(User, user_id)
    key = pair_key(viewer.id, user_id)
    can_send = _can_send(db, viewer, other)
    stmt = select(Message).where(Message.pair_key == key)
    if before is not None:
        pivot = db.get(Message, before)
        if pivot is None or pivot.pair_key != key:
            raise NotFoundError("Message not found")
        stmt = stmt.where(Message.created_at < pivot.created_at)
    rows = list(
        db.scalars(stmt.order_by(Message.created_at.desc(), Message.id).limit(PAGE + 1)).all()
    )
    if other is None or (not rows and not can_send and before is None):
        # No history and no right to write: this chat doesn't exist for the viewer.
        raise NotFoundError("Conversation not found")
    has_more = len(rows) > PAGE
    rows = rows[:PAGE][::-1]
    db.execute(
        update(Message)
        .where(
            Message.pair_key == key,
            Message.recipient_id == viewer.id,
            Message.read_at.is_(None),
        )
        .values(read_at=utc_now())
    )
    db.commit()
    return Thread(
        user_id=other.id,
        name=other.display_name or ANONYMOUS,
        can_send=can_send,
        messages=[_read(row, viewer.id) for row in rows],
        has_more=has_more,
    )


def send(db: Session, viewer: User, user_id: uuid.UUID, body: str) -> ChatMessage:
    other = db.get(User, user_id)
    if not _can_send(db, viewer, other):
        raise ForbiddenError("You can only write to your friends.")
    message = Message(
        pair_key=pair_key(viewer.id, user_id),
        sender_id=viewer.id,
        recipient_id=user_id,
        body=body,
    )
    db.add(message)
    db.commit()
    db.refresh(message)
    return _read(message, viewer.id)


def _read(row: Message, viewer_id: uuid.UUID) -> ChatMessage:
    return ChatMessage(
        id=row.id,
        mine=row.sender_id == viewer_id,
        body=row.body,
        created_at=row.created_at,
        read=row.read_at is not None,
    )
