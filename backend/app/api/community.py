"""Community endpoints: leaderboards, profiles, friends, blocks, messages and notifications
(docs/COMMUNITY.md). Opt-in only."""

import uuid

from fastapi import APIRouter, Depends, Query, status
from sqlalchemy.orm import Session

from app.auth.dependencies import get_current_user
from app.core.config import get_settings
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
    Interests,
    Leaderboard,
    MessageCreate,
    Notifications,
    Period,
    Person,
    Profile,
    PushStatus,
    PushSubscribe,
    PushTest,
    PushUnsubscribe,
    ReminderUpdate,
    ReportCreate,
    Scope,
    TagFollow,
    Thread,
)
from app.services import chat, community, interests, moderation, notifications, push
from app.services.push import PushSender, get_push_sender

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


# --- Push notifications: review reminders ---

Sender = Depends(get_push_sender)


def _push_status(db: Session, user: User, sender: PushSender | None) -> PushStatus:
    return PushStatus(
        enabled=sender is not None,
        public_key=get_settings().push_vapid_public_key if sender is not None else "",
        devices=push.devices(db, user.id),
        reminder_hour=user.reminder_hour,
    )


@router.get("/push", response_model=PushStatus)
def push_status(
    db: Session = DB, user: User = CurrentUser, sender: PushSender | None = Sender
) -> PushStatus:
    return _push_status(db, user, sender)


@router.post(
    "/push/subscribe",
    response_model=PushStatus,
    dependencies=[Depends(per_user("push_subscribe", 60, 3600))],
)
def push_subscribe(
    payload: PushSubscribe,
    db: Session = DB,
    user: User = CurrentUser,
    sender: PushSender | None = Sender,
) -> PushStatus:
    """This browser agreed to notifications: remember where to send them."""
    push.subscribe(db, user, payload.endpoint, payload.keys.p256dh, payload.keys.auth)
    return _push_status(db, user, sender)


@router.post("/push/unsubscribe", response_model=PushStatus)
def push_unsubscribe(
    payload: PushUnsubscribe,
    db: Session = DB,
    user: User = CurrentUser,
    sender: PushSender | None = Sender,
) -> PushStatus:
    push.unsubscribe(db, user, payload.endpoint)
    return _push_status(db, user, sender)


@router.put("/push/reminder", response_model=PushStatus)
def push_reminder(
    payload: ReminderUpdate,
    db: Session = DB,
    user: User = CurrentUser,
    sender: PushSender | None = Sender,
) -> PushStatus:
    """The hour of the daily review reminder (null: no reminder)."""
    user.reminder_hour = payload.hour
    user.last_reminded_on = None
    db.commit()
    return _push_status(db, user, sender)


@router.post(
    "/push/test",
    response_model=PushTest,
    dependencies=[Depends(per_user("push_test", 10, 3600))],
)
def push_test(
    db: Session = DB, user: User = CurrentUser, sender: PushSender | None = Sender
) -> PushTest:
    return PushTest(sent=push.send_test(db, user, sender))


# --- Interests: tags to hear about ---


@router.get("/interests", response_model=Interests)
def list_interests(db: Session = DB, user: User = CurrentUser) -> Interests:
    """The tags the user follows, and tags of published courses they could follow."""
    return interests.interests(db, user.id)


@router.put(
    "/interests",
    response_model=Interests,
    dependencies=[Depends(per_user("interests", 120, 3600))],
)
def follow_tag(payload: TagFollow, db: Session = DB, user: User = CurrentUser) -> Interests:
    """Follow a tag: a notification when a course carrying it is first published."""
    return interests.follow(db, user.id, payload.tag)


@router.delete("/interests", response_model=Interests)
def unfollow_tag(
    tag: str = Query(max_length=40), db: Session = DB, user: User = CurrentUser
) -> Interests:
    return interests.unfollow(db, user.id, tag)


# --- Reports to the administrator ---


@router.post(
    "/reports",
    status_code=status.HTTP_204_NO_CONTENT,
    dependencies=[Depends(per_user("reports", 20, 3600))],
)
def report(payload: ReportCreate, db: Session = DB, user: User = CurrentUser) -> None:
    """Tell the administrator about a person, a message you received or a review."""
    moderation.report(db, user, payload.kind, payload.target_id, payload.reason)
