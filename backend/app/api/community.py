"""Community endpoints: leaderboards, profiles, friends, blocks, messages and notifications
(docs/COMMUNITY.md). Opt-in only."""

import uuid

from fastapi import APIRouter, Depends, Query, status
from sqlalchemy.orm import Session

from app.auth.dependencies import get_current_user
from app.core.rate_limit import per_user
from app.db.session import get_db
from app.models.user import User
from app.schemas.common import InputModel
from app.schemas.community import (
    BlockedPerson,
    ChatMessage,
    Conversation,
    CourseLeaderboard,
    FriendRequests,
    Inbox,
    Leaderboard,
    MessageCreate,
    Notifications,
    Period,
    Person,
    Profile,
    Scope,
    Thread,
)
from app.services import chat, community, notifications

router = APIRouter(tags=["community"])

CurrentUser = Depends(get_current_user)
DB = Depends(get_db)


@router.get("/community/leaderboard", response_model=Leaderboard)
def leaderboard(
    period: Period = Period.WEEK,
    scope: Scope = Scope.EVERYONE,
    db: Session = DB,
    user: User = CurrentUser,
) -> Leaderboard:
    return community.leaderboard(db, user, period, scope)


@router.get("/courses/{course_id}/leaderboard", response_model=CourseLeaderboard)
def course_leaderboard(
    course_id: uuid.UUID,
    period: Period = Period.WEEK,
    scope: Scope = Scope.EVERYONE,
    db: Session = DB,
    user: User = CurrentUser,
) -> CourseLeaderboard:
    return community.course_leaderboard(db, user, course_id, period, scope)


@router.get("/community/people", response_model=list[Person])
def search_people(
    q: str = Query(max_length=80),
    db: Session = DB,
    user: User = CurrentUser,
    _: None = Depends(per_user("community_search", 60, 3600)),
) -> list[Person]:
    return community.search(db, user, q)


@router.get("/community/friends", response_model=list[Person])
def friends(db: Session = DB, user: User = CurrentUser) -> list[Person]:
    return community.friends(db, user)


@router.get("/community/friend-requests", response_model=FriendRequests)
def friend_requests(db: Session = DB, user: User = CurrentUser) -> FriendRequests:
    return community.friend_requests(db, user)


@router.get("/community/blocked", response_model=list[BlockedPerson])
def blocked(db: Session = DB, user: User = CurrentUser) -> list[BlockedPerson]:
    return community.blocked(db, user)


@router.get("/community/users/{user_id}", response_model=Profile)
def profile(user_id: uuid.UUID, db: Session = DB, user: User = CurrentUser) -> Profile:
    return community.profile(db, user, user_id)


@router.put(
    "/community/users/{user_id}/friend",
    response_model=Profile,
    dependencies=[Depends(per_user("community_friend", 60, 3600))],
)
def befriend(user_id: uuid.UUID, db: Session = DB, user: User = CurrentUser) -> Profile:
    """Ask to be friends, or accept their request."""
    return community.befriend(db, user, user_id)


@router.delete("/community/users/{user_id}/friend", status_code=status.HTTP_204_NO_CONTENT)
def unfriend(user_id: uuid.UUID, db: Session = DB, user: User = CurrentUser) -> None:
    """Cancel a request you sent, decline one you received, or remove a friend."""
    community.unfriend(db, user, user_id)


@router.put("/community/users/{user_id}/block", status_code=status.HTTP_204_NO_CONTENT)
def block(user_id: uuid.UUID, db: Session = DB, user: User = CurrentUser) -> None:
    community.block(db, user, user_id)


@router.delete("/community/users/{user_id}/block", status_code=status.HTTP_204_NO_CONTENT)
def unblock(user_id: uuid.UUID, db: Session = DB, user: User = CurrentUser) -> None:
    community.unblock(db, user, user_id)


# --- Messages ---


@router.get("/chats", response_model=list[Conversation])
def chats(db: Session = DB, user: User = CurrentUser) -> list[Conversation]:
    return chat.conversations(db, user)


@router.get("/chats/{user_id}", response_model=Thread)
def chat_thread(
    user_id: uuid.UUID,
    before: uuid.UUID | None = None,
    db: Session = DB,
    user: User = CurrentUser,
) -> Thread:
    return chat.thread(db, user, user_id, before)


@router.post(
    "/chats/{user_id}",
    response_model=ChatMessage,
    status_code=status.HTTP_201_CREATED,
    dependencies=[Depends(per_user("chat_send", 120, 600))],
)
def chat_send(
    user_id: uuid.UUID, payload: MessageCreate, db: Session = DB, user: User = CurrentUser
) -> ChatMessage:
    return chat.send(db, user, user_id, payload.body)


# --- Notifications ---


class MarkRead(InputModel):
    # Omitted: all of them.
    ids: list[uuid.UUID] | None = None


@router.get("/inbox", response_model=Inbox)
def inbox(db: Session = DB, user: User = CurrentUser) -> Inbox:
    """The counts behind the app's badges."""
    return Inbox(
        notifications=notifications.unread_count(db, user.id),
        messages=chat.unread_count(db, user.id),
        friend_requests=community.pending_requests(db, user.id),
    )


@router.get("/notifications", response_model=Notifications)
def list_notifications(db: Session = DB, user: User = CurrentUser) -> Notifications:
    return notifications.listed(db, user)


@router.post("/notifications/read", status_code=status.HTTP_204_NO_CONTENT)
def read_notifications(payload: MarkRead, db: Session = DB, user: User = CurrentUser) -> None:
    notifications.mark_read(db, user.id, payload.ids)
