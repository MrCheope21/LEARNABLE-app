"""Community API shapes. Other users are shown by display name only: never an email, never
anything about their courses or answers. Only people who opted in appear at all."""

from enum import StrEnum
from typing import Annotated, Any, Literal
from uuid import UUID

from pydantic import BaseModel, Field

from app.schemas.common import InputModel, UTCTimestamp


class Period(StrEnum):
    DAY = "day"
    WEEK = "week"
    MONTH = "month"
    ALL = "all"


class Scope(StrEnum):
    EVERYONE = "everyone"
    FRIENDS = "friends"


class Relation(StrEnum):
    """What another person is to the viewer."""

    NONE = "none"
    FRIENDS = "friends"
    # The viewer asked; they haven't answered.
    REQUEST_SENT = "request_sent"
    # They asked; the viewer can accept or decline.
    REQUEST_RECEIVED = "request_received"


class LeaderboardEntry(BaseModel):
    rank: int
    user_id: UUID
    name: str
    xp: int
    is_me: bool
    relation: Relation


class Leaderboard(BaseModel):
    period: Period
    scope: Scope
    # The window's start (UTC); null for all time.
    since: UTCTimestamp | None
    entries: list[LeaderboardEntry]
    # The viewer's own place, even past the listed ones; null when they aren't on it (not
    # visible in the community, or no XP in this window).
    me: LeaderboardEntry | None
    # The viewer isn't visible, so they can't appear: the page invites them to join.
    me_hidden: bool


class CourseLeaderboard(Leaderboard):
    # How many people share this course: 1 for a private course.
    participants: int


class Profile(BaseModel):
    user_id: UUID
    name: str
    member_since: UTCTimestamp
    xp_total: int
    xp_week: int
    streak: int
    friends: int
    is_me: bool
    relation: Relation
    # The viewer blocked this person (they can still see the page to unblock).
    blocked: bool


class Person(BaseModel):
    """A listed person: a friend, someone in a friend request, or a search result."""

    user_id: UUID
    name: str
    xp_today: int
    streak: int
    last_active: UTCTimestamp | None
    relation: Relation
    # When the friend request was sent (requests only).
    requested_at: UTCTimestamp | None = None


class FriendRequests(BaseModel):
    incoming: list[Person]
    outgoing: list[Person]


class BlockedPerson(BaseModel):
    user_id: UUID
    name: str


# --- Messages ---


class MessageCreate(InputModel):
    body: Annotated[str, Field(min_length=1, max_length=2000)]


class ChatMessage(BaseModel):
    id: UUID
    mine: bool
    body: str
    created_at: UTCTimestamp
    read: bool


class Conversation(BaseModel):
    """A chat with one friend, in the list of chats."""

    user_id: UUID
    name: str
    last_message: str
    last_mine: bool
    last_at: UTCTimestamp
    unread: int
    # False when you're no longer friends (or one blocked the other): the history stays
    # readable, nothing new can be sent.
    can_send: bool


class Thread(BaseModel):
    user_id: UUID
    name: str
    can_send: bool
    messages: list[ChatMessage]
    # Older messages exist: ask again with `before` = the first message's id.
    has_more: bool


# --- Notifications ---


class NotificationRead(BaseModel):
    id: UUID
    kind: str
    # The display name of who caused it, when it was a person.
    actor: str | None
    data: dict[str, Any]
    link: str
    created_at: UTCTimestamp
    read: bool


class Notifications(BaseModel):
    items: list[NotificationRead]
    unread: int


class Inbox(BaseModel):
    """The counts behind the badges, polled by the app."""

    notifications: int
    messages: int
    friend_requests: int


# --- Push notifications ---


class PushKeys(InputModel):
    p256dh: Annotated[str, Field(min_length=10, max_length=200)]
    auth: Annotated[str, Field(min_length=4, max_length=100)]


class PushSubscribe(InputModel):
    """What the browser's `pushManager.subscribe()` returns."""

    endpoint: Annotated[str, Field(min_length=10, max_length=1000, pattern=r"^https://")]
    keys: PushKeys


class PushUnsubscribe(InputModel):
    endpoint: Annotated[str, Field(min_length=10, max_length=1000)]


class ReminderUpdate(InputModel):
    # The local hour (0-23) to be reminded from; null turns reminders off.
    hour: Annotated[int, Field(ge=0, le=23)] | None


class PushStatus(BaseModel):
    # The server can send push notifications.
    enabled: bool
    # The key the browser subscribes with.
    public_key: str
    # How many of the user's browsers and devices are subscribed.
    devices: int
    reminder_hour: int | None


class PushTest(BaseModel):
    sent: int


# --- Interests: tags the user wants to hear about ---


class TagFollow(InputModel):
    tag: Annotated[str, Field(min_length=2, max_length=40)]


class Interests(BaseModel):
    # Followed tags, lowercased, in the order they were added.
    tags: list[str]
    # Tags of published courses the user doesn't follow yet, most used first.
    suggestions: list[str]


# --- Reports to the administrator ---


class ReportKind(StrEnum):
    USER = "user"
    MESSAGE = "message"
    REVIEW = "review"


class ReportCreate(InputModel):
    kind: ReportKind
    # The user's, the message's or the review's id.
    target_id: UUID
    reason: Annotated[str, Field(max_length=1000)] = ""


class ReportRead(BaseModel):
    """What the administrator sees: who reported, about whom, and the reported text itself
    (copied when the report was made)."""

    id: UUID
    kind: ReportKind
    target_id: UUID
    reporter: str
    reporter_email: str
    subject_id: UUID | None
    subject: str | None
    subject_email: str | None
    reason: str
    excerpt: str
    status: Literal["OPEN", "RESOLVED"]
    created_at: UTCTimestamp
    resolved_at: UTCTimestamp | None
    # How many reports, open or not, are about the same person.
    subject_reports: int
