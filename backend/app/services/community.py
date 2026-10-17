"""The community: leaderboards, profiles and following (Duolingo-style friends).

Everything here is opt-in: a user who hasn't turned on `community_visible` appears on no
leaderboard, can't be found or followed, and has no profile page. Rankings come from the XP
ledger (`xp_awards`), the same source as the dashboard's XP, over UTC calendar windows so all
learners are compared on the same clock: day (since 00:00 UTC), week (since Monday), month
(since the 1st), or all time.
"""

import uuid
from datetime import UTC, datetime, timedelta

from sqlalchemy import func, or_, select
from sqlalchemy.orm import Session

from app.core.errors import ConflictError, InvalidRequestError, NotFoundError
from app.db.types import utc_now
from app.models.community import Follow
from app.models.course import Course
from app.models.marketplace import MarketplaceListing
from app.models.rewards import XpAward
from app.models.user import User
from app.schemas.community import (
    CourseLeaderboard,
    Leaderboard,
    LeaderboardEntry,
    Period,
    Person,
    Profile,
    Scope,
)
from app.services.courses.service import get_owned_course
from app.services.dashboard.service import current_streak
from app.services.rewards.service import local_day

LIST_LIMIT = 50
SEARCH_LIMIT = 20
ANONYMOUS = "A LEARNABLE user"


def window_start(period: Period, now: datetime | None = None) -> datetime | None:
    now = (now or utc_now()).astimezone(UTC)
    midnight = now.replace(hour=0, minute=0, second=0, microsecond=0)
    if period is Period.DAY:
        return midnight
    if period is Period.WEEK:
        return midnight - timedelta(days=midnight.weekday())
    if period is Period.MONTH:
        return midnight.replace(day=1)
    return None


def _name(user: User) -> str:
    return user.display_name or ANONYMOUS


def _following_ids(db: Session, user_id: uuid.UUID) -> set[uuid.UUID]:
    return set(db.scalars(select(Follow.followee_id).where(Follow.follower_id == user_id)))


def _followers_ids(db: Session, user_id: uuid.UUID) -> set[uuid.UUID]:
    return set(db.scalars(select(Follow.follower_id).where(Follow.followee_id == user_id)))


# --- Settings ---


def check_can_be_visible(user: User) -> None:
    if not user.display_name:
        raise InvalidRequestError(
            "Choose a display name first: it's how other people will see you (your email is "
            "never shown)."
        )


# --- Leaderboards ---


def _ranked(
    db: Session,
    viewer: User,
    *,
    period: Period,
    scope: Scope,
    course_ids: list[uuid.UUID] | None,
    limit: int,
) -> Leaderboard:
    since = window_start(period)
    xp = func.coalesce(func.sum(XpAward.xp), 0)
    stmt = (
        select(User.id, User.display_name, xp.label("xp"))
        .join(XpAward, XpAward.user_id == User.id)
        .where(User.community_visible.is_(True))
        .group_by(User.id, User.display_name, User.created_at)
        .having(xp > 0)
    )
    if since is not None:
        stmt = stmt.where(XpAward.awarded_at >= since)
    if course_ids is not None:
        stmt = stmt.where(XpAward.course_id.in_(course_ids))
    following = _following_ids(db, viewer.id)
    if scope is Scope.FRIENDS:
        stmt = stmt.where(User.id.in_(following | {viewer.id}))
    rows = db.execute(stmt.order_by(xp.desc(), User.created_at, User.id)).all()

    entries: list[LeaderboardEntry] = []
    rank, previous = 0, None
    for position, (user_id, display_name, total) in enumerate(rows, start=1):
        total = int(total)
        if total != previous:
            rank, previous = position, total  # equal XP shares a place
        entries.append(
            LeaderboardEntry(
                rank=rank,
                user_id=user_id,
                name=display_name or ANONYMOUS,
                xp=total,
                is_me=user_id == viewer.id,
                following=user_id in following,
            )
        )
    me = next((e for e in entries if e.is_me), None)
    return Leaderboard(
        period=period,
        scope=scope,
        since=since,
        entries=entries[:limit],
        me=me,
        me_hidden=not viewer.community_visible,
    )


def leaderboard(
    db: Session, viewer: User, period: Period, scope: Scope, limit: int = LIST_LIMIT
) -> Leaderboard:
    return _ranked(db, viewer, period=period, scope=scope, course_ids=None, limit=limit)


def course_group(db: Session, course: Course) -> list[uuid.UUID]:
    """The courses whose XP is compared with this one: a marketplace course's author and
    everyone who has it. A private course is alone."""
    listing_id = course.marketplace_listing_id or db.scalar(
        select(MarketplaceListing.id).where(MarketplaceListing.source_course_id == course.id)
    )
    if listing_id is None:
        return [course.id]
    ids = set(db.scalars(select(Course.id).where(Course.marketplace_listing_id == listing_id)))
    source = db.scalar(
        select(MarketplaceListing.source_course_id).where(MarketplaceListing.id == listing_id)
    )
    if source is not None:
        ids.add(source)
    ids.add(course.id)
    return list(ids)


def course_leaderboard(
    db: Session, viewer: User, course_id: uuid.UUID, period: Period, scope: Scope
) -> CourseLeaderboard:
    course = get_owned_course(db, viewer.id, course_id)
    ids = course_group(db, course)
    board = _ranked(db, viewer, period=period, scope=scope, course_ids=ids, limit=LIST_LIMIT)
    owners = db.scalar(select(func.count(func.distinct(Course.user_id))).where(Course.id.in_(ids)))
    return CourseLeaderboard(**board.model_dump(), participants=int(owners or 1))


# --- Profiles and following ---


def _visible_user(db: Session, viewer: User, user_id: uuid.UUID) -> User:
    user = db.get(User, user_id)
    # Someone who hasn't opted in doesn't exist for others (404, like any private resource).
    if user is None or (user.id != viewer.id and not user.community_visible):
        raise NotFoundError("Profile not found")
    return user


def profile(db: Session, viewer: User, user_id: uuid.UUID) -> Profile:
    user = _visible_user(db, viewer, user_id)
    now = utc_now()
    xp_total = db.scalar(
        select(func.coalesce(func.sum(XpAward.xp), 0)).where(XpAward.user_id == user.id)
    )
    week = window_start(Period.WEEK, now)
    xp_week = db.scalar(
        select(func.coalesce(func.sum(XpAward.xp), 0)).where(
            XpAward.user_id == user.id, XpAward.awarded_at >= week
        )
    )
    followers, following = _followers_ids(db, user.id), _following_ids(db, user.id)
    return Profile(
        user_id=user.id,
        name=_name(user),
        member_since=user.created_at,
        xp_total=int(xp_total or 0),
        xp_week=int(xp_week or 0),
        streak=current_streak(db, user.id, local_day(user.timezone, now)),
        followers=len(followers & _visible_ids(db, followers)),
        following=len(following & _visible_ids(db, following)),
        is_me=user.id == viewer.id,
        i_follow=user.id in _following_ids(db, viewer.id),
        follows_me=viewer.id in following,
    )


def _visible_ids(db: Session, ids: set[uuid.UUID]) -> set[uuid.UUID]:
    if not ids:
        return set()
    return set(
        db.scalars(select(User.id).where(User.id.in_(ids), User.community_visible.is_(True)))
    )


def follow(db: Session, viewer: User, user_id: uuid.UUID) -> Profile:
    if user_id == viewer.id:
        raise ConflictError("You can't follow yourself.", details={"reason": "self_follow"})
    _visible_user(db, viewer, user_id)
    exists = db.scalar(
        select(Follow.id).where(Follow.follower_id == viewer.id, Follow.followee_id == user_id)
    )
    if exists is None:
        db.add(Follow(follower_id=viewer.id, followee_id=user_id))
        db.commit()
    return profile(db, viewer, user_id)


def unfollow(db: Session, viewer: User, user_id: uuid.UUID) -> None:
    row = db.scalar(
        select(Follow).where(Follow.follower_id == viewer.id, Follow.followee_id == user_id)
    )
    if row is not None:
        db.delete(row)
        db.commit()


def _people(db: Session, viewer: User, users: list[User]) -> list[Person]:
    if not users:
        return []
    ids = [u.id for u in users]
    today = window_start(Period.DAY)
    xp_today = dict(
        db.execute(
            select(XpAward.user_id, func.sum(XpAward.xp))
            .where(XpAward.user_id.in_(ids), XpAward.awarded_at >= today)
            .group_by(XpAward.user_id)
        )
        .tuples()
        .all()
    )
    last = dict(
        db.execute(
            select(XpAward.user_id, func.max(XpAward.awarded_at))
            .where(XpAward.user_id.in_(ids))
            .group_by(XpAward.user_id)
        )
        .tuples()
        .all()
    )
    mine, theirs = _following_ids(db, viewer.id), _followers_ids(db, viewer.id)
    now = utc_now()
    return [
        Person(
            user_id=u.id,
            name=_name(u),
            xp_today=int(xp_today.get(u.id, 0)),
            streak=current_streak(db, u.id, local_day(u.timezone, now)),
            last_active=last.get(u.id),
            i_follow=u.id in mine,
            follows_me=u.id in theirs,
        )
        for u in users
    ]


def following(db: Session, viewer: User) -> list[Person]:
    return _listed(db, viewer, _following_ids(db, viewer.id))


def followers(db: Session, viewer: User) -> list[Person]:
    return _listed(db, viewer, _followers_ids(db, viewer.id))


def _listed(db: Session, viewer: User, ids: set[uuid.UUID]) -> list[Person]:
    if not ids:
        return []
    users = db.scalars(
        select(User)
        .where(User.id.in_(ids), User.community_visible.is_(True))
        .order_by(User.display_name)
    ).all()
    # Friends first (they follow back), then by recent activity in the UI.
    return _people(db, viewer, list(users))


def search(db: Session, viewer: User, query: str) -> list[Person]:
    needle = " ".join(query.split()).lower()
    if len(needle) < 2:
        raise InvalidRequestError("Type at least 2 letters of a name.")
    escaped = needle.replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_")
    users = db.scalars(
        select(User)
        .where(
            User.community_visible.is_(True),
            User.id != viewer.id,
            or_(func.lower(User.display_name).like(f"%{escaped}%", escape="\\")),
        )
        .order_by(User.display_name)
        .limit(SEARCH_LIMIT)
    ).all()
    return _people(db, viewer, list(users))
