"""Community API shapes. Other users are shown by display name only: never an email, never
anything about their courses or answers. Only people who opted in appear at all."""

from enum import StrEnum
from uuid import UUID

from pydantic import BaseModel

from app.schemas.common import UTCTimestamp


class Period(StrEnum):
    DAY = "day"
    WEEK = "week"
    MONTH = "month"
    ALL = "all"


class Scope(StrEnum):
    EVERYONE = "everyone"
    FRIENDS = "friends"


class LeaderboardEntry(BaseModel):
    rank: int
    user_id: UUID
    name: str
    xp: int
    is_me: bool
    # The viewer follows them.
    following: bool


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
    followers: int
    following: int
    is_me: bool
    i_follow: bool
    follows_me: bool


class Person(BaseModel):
    """A listed person: someone you follow, a follower, or a search result."""

    user_id: UUID
    name: str
    xp_today: int
    streak: int
    last_active: UTCTimestamp | None
    i_follow: bool
    follows_me: bool
