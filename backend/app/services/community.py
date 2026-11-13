"""The community: leaderboards, profiles, friends and blocks (docs/COMMUNITY.md).

Everything here is opt-in: a user who hasn't turned on `community_visible` appears on no
leaderboard, can't be found or asked to be a friend, and has no profile page. Friendship is
mutual: one person asks, the other accepts or declines (the old one-way "follow" is gone).

Rankings come from the XP ledger (`xp_awards`), the same source as the dashboard's XP, over
UTC calendar windows so all learners are compared on the same clock: day (since 00:00 UTC),
week (since Monday), month (since the 1st), or all time.
"""

import uuid
from datetime import UTC, datetime, timedelta

from sqlalchemy import ColumnElement, and_, delete, func, or_, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.core.errors import ConflictError, InvalidRequestError, NotFoundError
from app.db.types import utc_now
from app.models.community import ACCEPTED, PENDING, Block, Friendship, pair_key
from app.models.course import Course
from app.models.marketplace import MarketplaceListing
from app.models.rewards import XpAward
from app.models.user import User
from app.schemas.community import (
    BlockedPerson,
    CourseLeaderboard,
    FriendRequests,
    Leaderboard,
    LeaderboardEntry,
    Period,
    Person,
    Profile,
    Relation,
    Scope,
)
from app.services import notifications
from app.services.courses.service import get_owned_course
from app.services.dashboard.service import current_streak
from app.services.rewards.service import local_day

LIST_LIMIT = 50
SEARCH_LIMIT = 20
ANONYMOUS = "A Recallable user"


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


def shown_name(display_name: str | None, username: str | None) -> str:
    """How someone is shown to others: their display name, else their @username."""
    return display_name or (f"@{username}" if username else ANONYMOUS)


def _name(user: User) -> str:
    return shown_name(user.display_name, user.username)


def reachable() -> ColumnElement[bool]:
    """People others can find, ask to be friends and write to: whoever joined the community,
    and whoever has a username (found only by typing it exactly, or from their own link).
    Leaderboards stay for those who joined."""
    return or_(User.community_visible.is_(True), User.username.is_not(None))


def _is_reachable(user: User) -> bool:
    return user.community_visible or user.username is not None


def _relations(db: Session, user_id: uuid.UUID) -> dict[uuid.UUID, Relation]:
    """Everyone the user has a friendship or a pending request with."""
    rows = db.execute(
        select(Friendship.requester_id, Friendship.addressee_id, Friendship.status).where(
            or_(Friendship.requester_id == user_id, Friendship.addressee_id == user_id)
        )
    ).all()
    result: dict[uuid.UUID, Relation] = {}
    for requester_id, addressee_id, status in rows:
        mine = requester_id == user_id
        other = addressee_id if mine else requester_id
        if status == ACCEPTED:
            result[other] = Relation.FRIENDS
        else:
            result[other] = Relation.REQUEST_SENT if mine else Relation.REQUEST_RECEIVED
    return result


def friend_ids(db: Session, user_id: uuid.UUID) -> set[uuid.UUID]:
    return {
        other for other, relation in _relations(db, user_id).items() if relation is Relation.FRIENDS
    }


def are_friends(db: Session, a: uuid.UUID, b: uuid.UUID) -> bool:
    return (
        db.scalar(
            select(Friendship.id).where(
                Friendship.pair_key == pair_key(a, b), Friendship.status == ACCEPTED
            )
        )
        is not None
    )


def blocked_between(db: Session, a: uuid.UUID, b: uuid.UUID) -> bool:
    """Either blocked the other."""
    return (
        db.scalar(
            select(Block.id).where(
                or_(
                    and_(Block.blocker_id == a, Block.blocked_id == b),
                    and_(Block.blocker_id == b, Block.blocked_id == a),
                )
            )
        )
        is not None
    )


def _hidden_from(db: Session, user_id: uuid.UUID) -> set[uuid.UUID]:
    """People the user blocked or who blocked them: neither finds the other."""
    rows = db.execute(
        select(Block.blocker_id, Block.blocked_id).where(
            or_(Block.blocker_id == user_id, Block.blocked_id == user_id)
        )
    ).all()
    return {blocked if blocker == user_id else blocker for blocker, blocked in rows}


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
    relations = _relations(db, viewer.id)
    if scope is Scope.FRIENDS:
        friends = {u for u, r in relations.items() if r is Relation.FRIENDS}
        stmt = stmt.where(User.id.in_(friends | {viewer.id}))
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
                relation=relations.get(user_id, Relation.NONE),
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


# --- Profiles ---


def _visible_user(db: Session, viewer: User, user_id: uuid.UUID) -> User:
    user = db.get(User, user_id)
    # Someone who hasn't opted in doesn't exist for others (404, like any private resource).
    if user is None or (user.id != viewer.id and not _is_reachable(user)):
        raise NotFoundError("Profile not found")
    return user


def _block_of(db: Session, blocker_id: uuid.UUID, blocked_id: uuid.UUID) -> Block | None:
    return db.scalar(
        select(Block).where(Block.blocker_id == blocker_id, Block.blocked_id == blocked_id)
    )


def profile(db: Session, viewer: User, user_id: uuid.UUID) -> Profile:
    user = _visible_user(db, viewer, user_id)
    # Someone who blocked the viewer has no page for them.
    if user.id != viewer.id and _block_of(db, user.id, viewer.id) is not None:
        raise NotFoundError("Profile not found")
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
    friends = friend_ids(db, user.id)
    return Profile(
        user_id=user.id,
        name=_name(user),
        member_since=user.created_at,
        xp_total=int(xp_total or 0),
        xp_week=int(xp_week or 0),
        streak=current_streak(db, user.id, local_day(user.timezone, now)),
        friends=len(_visible_ids(db, friends)),
        is_me=user.id == viewer.id,
        relation=_relations(db, viewer.id).get(user.id, Relation.NONE),
        blocked=_block_of(db, viewer.id, user.id) is not None,
    )


def _visible_ids(db: Session, ids: set[uuid.UUID]) -> set[uuid.UUID]:
    if not ids:
        return set()
    return set(db.scalars(select(User.id).where(User.id.in_(ids), reachable())))


# --- Friends: ask, accept, decline, cancel, remove ---


def _friendship(db: Session, a: uuid.UUID, b: uuid.UUID) -> Friendship | None:
    return db.scalar(select(Friendship).where(Friendship.pair_key == pair_key(a, b)))


def befriend(db: Session, viewer: User, user_id: uuid.UUID) -> Profile:
    """Sends a friend request; when the other person had already asked, accepts theirs.
    Asking twice, or asking a friend, changes nothing."""
    if user_id == viewer.id:
        raise ConflictError("You can't add yourself.", details={"reason": "self_friend"})
    if not _is_reachable(viewer):
        raise ConflictError(
            "Choose a username or join the community first: people need to see who is asking.",
            details={"reason": "not_visible"},
        )
    other = _visible_user(db, viewer, user_id)
    if blocked_between(db, viewer.id, other.id):
        # The same answer whoever blocked whom: a block is never revealed.
        raise NotFoundError("Profile not found")
    row = _friendship(db, viewer.id, other.id)
    if row is None:
        db.add(
            Friendship(
                pair_key=pair_key(viewer.id, other.id),
                requester_id=viewer.id,
                addressee_id=other.id,
            )
        )
        notifications.notify(
            db, other.id, "friend_request", actor_id=viewer.id, link="/community/friends"
        )
        try:
            db.commit()
        except IntegrityError:
            # The two asked each other at the same moment: the other request exists now.
            db.rollback()
            return befriend(db, viewer, user_id)
    elif row.status == PENDING and row.addressee_id == viewer.id:
        row.status = ACCEPTED
        row.responded_at = utc_now()
        notifications.withdraw(db, viewer.id, "friend_request", other.id)
        notifications.notify(
            db,
            other.id,
            "friend_accepted",
            actor_id=viewer.id,
            link=f"/community/users/{viewer.id}",
        )
        db.commit()
    return profile(db, viewer, user_id)


def unfriend(db: Session, viewer: User, user_id: uuid.UUID) -> None:
    """Whatever there is between the two goes: a request the viewer sent (cancel), one they
    received (decline) or the friendship (remove). The other person isn't notified."""
    row = _friendship(db, viewer.id, user_id)
    if row is None:
        return
    if row.status == PENDING:
        # The request's notification goes with it, whoever it was for.
        notifications.withdraw(db, row.addressee_id, "friend_request", row.requester_id)
    db.delete(row)
    db.commit()


def block(db: Session, viewer: User, user_id: uuid.UUID) -> None:
    """Ends any friendship or request and stops requests and messages both ways."""
    if user_id == viewer.id:
        raise ConflictError("You can't block yourself.", details={"reason": "self_block"})
    if db.get(User, user_id) is None:
        raise NotFoundError("Profile not found")
    row = _friendship(db, viewer.id, user_id)
    if row is not None:
        if row.status == PENDING:
            notifications.withdraw(db, row.addressee_id, "friend_request", row.requester_id)
        db.delete(row)
    if _block_of(db, viewer.id, user_id) is None:
        db.add(Block(blocker_id=viewer.id, blocked_id=user_id))
    db.commit()


def unblock(db: Session, viewer: User, user_id: uuid.UUID) -> None:
    db.execute(delete(Block).where(Block.blocker_id == viewer.id, Block.blocked_id == user_id))
    db.commit()


def blocked(db: Session, viewer: User) -> list[BlockedPerson]:
    rows = db.execute(
        select(User.id, User.display_name, User.username)
        .join(Block, Block.blocked_id == User.id)
        .where(Block.blocker_id == viewer.id)
        .order_by(User.display_name)
    ).all()
    return [BlockedPerson(user_id=row[0], name=shown_name(row[1], row[2])) for row in rows]


def _people(
    db: Session,
    viewer: User,
    users: list[User],
    requested_at: dict[uuid.UUID, datetime] | None = None,
) -> list[Person]:
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
    relations = _relations(db, viewer.id)
    now = utc_now()
    return [
        Person(
            user_id=u.id,
            name=_name(u),
            xp_today=int(xp_today.get(u.id, 0)),
            streak=current_streak(db, u.id, local_day(u.timezone, now)),
            last_active=last.get(u.id),
            relation=relations.get(u.id, Relation.NONE),
            requested_at=(requested_at or {}).get(u.id),
        )
        for u in users
    ]


def friends(db: Session, viewer: User) -> list[Person]:
    return _listed(db, viewer, friend_ids(db, viewer.id))


def friend_requests(db: Session, viewer: User) -> FriendRequests:
    rows = db.execute(
        select(Friendship.requester_id, Friendship.addressee_id, Friendship.created_at).where(
            Friendship.status == PENDING,
            or_(Friendship.requester_id == viewer.id, Friendship.addressee_id == viewer.id),
        )
    ).all()
    incoming = {r[0]: r[2] for r in rows if r[1] == viewer.id}
    outgoing = {r[1]: r[2] for r in rows if r[0] == viewer.id}
    return FriendRequests(
        incoming=_listed(db, viewer, set(incoming), incoming),
        outgoing=_listed(db, viewer, set(outgoing), outgoing),
    )


def pending_requests(db: Session, user_id: uuid.UUID) -> int:
    """Requests waiting for the user's answer, from people still visible."""
    return int(
        db.scalar(
            select(func.count())
            .select_from(Friendship)
            .join(User, User.id == Friendship.requester_id)
            .where(
                Friendship.addressee_id == user_id,
                Friendship.status == PENDING,
                reachable(),
            )
        )
        or 0
    )


def _listed(
    db: Session,
    viewer: User,
    ids: set[uuid.UUID],
    requested_at: dict[uuid.UUID, datetime] | None = None,
) -> list[Person]:
    if not ids:
        return []
    users = db.scalars(
        select(User)
        .where(User.id.in_(ids), reachable())
        .order_by(func.lower(func.coalesce(User.display_name, User.username)))
    ).all()
    return _people(db, viewer, list(users), requested_at)


def search(db: Session, viewer: User, query: str) -> list[Person]:
    """By part of the display name, or by the exact username (never by email)."""
    needle = " ".join(query.split()).lower()
    if len(needle) < 2:
        raise InvalidRequestError("Type at least 2 letters of a name.")
    escaped = needle.replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_")
    stmt = (
        select(User)
        .where(
            User.id != viewer.id,
            User.is_active,
            or_(
                # Part of the name: only people who joined the community.
                and_(
                    User.community_visible.is_(True),
                    func.lower(User.display_name).like(f"%{escaped}%", escape="\\"),
                ),
                # The exact username finds its owner, in the community or not.
                func.lower(User.username) == needle.removeprefix("@"),
            ),
        )
        .order_by(func.lower(User.display_name))
        .limit(SEARCH_LIMIT)
    )
    hidden = _hidden_from(db, viewer.id)
    if hidden:
        stmt = stmt.where(User.id.notin_(hidden))
    return _people(db, viewer, list(db.scalars(stmt).all()))
