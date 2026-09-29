"""The study dashboard and activity calendar (docs/XP_AND_ACTIVITY.md)."""

import uuid

from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session

from app.auth.dependencies import get_current_user
from app.db.session import get_db
from app.models.user import User
from app.schemas.dashboard import Activity, CourseCard, Dashboard
from app.services.dashboard import service

router = APIRouter(tags=["dashboard"])

CurrentUser = Depends(get_current_user)
DB = Depends(get_db)


@router.get("/dashboard", response_model=Dashboard)
def dashboard(
    weeks: int = Query(default=service.DEFAULT_ACTIVITY_WEEKS, ge=1, le=service.MAX_ACTIVITY_WEEKS),
    db: Session = DB,
    user: User = CurrentUser,
) -> Dashboard:
    """Everything the dashboard shows, in the user's timezone and against one `as_of` time:
    the next recommended step, course cards, XP, streak, daily goal, review planner and the
    activity calendar."""
    return service.dashboard(db, user, weeks)


@router.get("/activity", response_model=Activity)
def activity(
    weeks: int = Query(default=52, ge=1, le=service.MAX_ACTIVITY_WEEKS),
    db: Session = DB,
    user: User = CurrentUser,
) -> Activity:
    """The longer activity calendar ("See more")."""
    return service.activity(db, user, weeks)


@router.get("/courses/{course_id}/summary", response_model=CourseCard)
def course_summary(course_id: uuid.UUID, db: Session = DB, user: User = CurrentUser) -> CourseCard:
    """One course's card: progress counts, due count and its Learn action."""
    return service.course_card(db, user, course_id)
