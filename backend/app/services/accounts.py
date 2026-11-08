"""Administration and removal of accounts: suspending, and deleting one with everything it owns."""

import uuid

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.errors import NotFoundError
from app.models.course import Course
from app.models.user import User
from app.services.courses import service as courses
from app.services.documents.service import delete_course_files
from app.storage.documents import DocumentStorage


def set_active(db: Session, user_id: uuid.UUID, active: bool) -> User:
    """Suspends or reactivates an account. Suspending also ends every session at once (the token
    version moves on, and a suspended account is refused by the API in any case)."""
    user = db.get(User, user_id)
    if user is None:
        raise NotFoundError("Account not found")
    user.is_active = active
    if not active:
        user.token_version += 1
    db.commit()
    db.refresh(user)
    return user


def delete_account(db: Session, storage: DocumentStorage, user_id: uuid.UUID) -> None:
    """Deletes the account and all its data: courses (with their uploaded files and drawings),
    answers, XP, follows, marketplace pages. Rows cascade; files are removed explicitly."""
    user = db.get(User, user_id)
    if user is None:
        raise NotFoundError("Account not found")
    for course_id in db.scalars(select(Course.id).where(Course.user_id == user_id)).all():
        delete_course_files(storage, courses.delete_course(db, user_id, course_id))
    db.delete(user)
    db.commit()
