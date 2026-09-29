"""Progress and review load (docs/PROJECT_SPEC.md §52-54, §67-68)."""

import uuid

from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session

from app.auth.dependencies import get_current_user
from app.db.session import get_db
from app.models.user import User
from app.schemas.progress import CourseProgress, HomeSummary, ReviewLoad
from app.services.mastery import service

router = APIRouter(tags=["progress"])

CurrentUser = Depends(get_current_user)
DB = Depends(get_db)
# The user's offset from UTC in minutes (e.g. 120 for Italy in summer), so "today" and
# "tomorrow" are the user's calendar days.
UtcOffset = Query(default=0, ge=-14 * 60, le=14 * 60)


@router.get("/courses/{course_id}/progress", response_model=CourseProgress)
def course_progress(
    course_id: uuid.UUID,
    utc_offset_minutes: int = UtcOffset,
    db: Session = DB,
    user: User = CurrentUser,
) -> CourseProgress:
    return service.course_progress(db, user.id, course_id, utc_offset_minutes)


@router.get("/courses/{course_id}/review-load", response_model=ReviewLoad)
def review_load(
    course_id: uuid.UUID,
    utc_offset_minutes: int = UtcOffset,
    db: Session = DB,
    user: User = CurrentUser,
) -> ReviewLoad:
    return service.review_load(db, user.id, course_id, utc_offset_minutes)


@router.get("/home", response_model=HomeSummary)
def home(
    utc_offset_minutes: int = UtcOffset, db: Session = DB, user: User = CurrentUser
) -> HomeSummary:
    """The Home screen in one call: each of the user's Courses with its review load, active
    Concepts, mastery estimate and weakest Concepts."""
    return service.home_summary(db, user.id, utc_offset_minutes)
