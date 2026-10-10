"""Community endpoints: leaderboards, profiles, following. Opt-in only (docs/API.md)."""

import uuid

from fastapi import APIRouter, Depends, Query, status
from sqlalchemy.orm import Session

from app.auth.dependencies import get_current_user
from app.core.rate_limit import per_user
from app.db.session import get_db
from app.models.user import User
from app.schemas.community import (
    CourseLeaderboard,
    Leaderboard,
    Period,
    Person,
    Profile,
    Scope,
)
from app.services import community

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


@router.get("/community/following", response_model=list[Person])
def following(db: Session = DB, user: User = CurrentUser) -> list[Person]:
    return community.following(db, user)


@router.get("/community/followers", response_model=list[Person])
def followers(db: Session = DB, user: User = CurrentUser) -> list[Person]:
    return community.followers(db, user)


@router.get("/community/users/{user_id}", response_model=Profile)
def profile(user_id: uuid.UUID, db: Session = DB, user: User = CurrentUser) -> Profile:
    return community.profile(db, user, user_id)


@router.put(
    "/community/users/{user_id}/follow",
    response_model=Profile,
    dependencies=[Depends(per_user("community_follow", 120, 3600))],
)
def follow(user_id: uuid.UUID, db: Session = DB, user: User = CurrentUser) -> Profile:
    return community.follow(db, user, user_id)


@router.delete("/community/users/{user_id}/follow", status_code=status.HTTP_204_NO_CONTENT)
def unfollow(user_id: uuid.UUID, db: Session = DB, user: User = CurrentUser) -> None:
    community.unfollow(db, user, user_id)
