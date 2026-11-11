"""Administration: invitations, accounts and limits. Administrators only (docs/MULTI_USER.md).

An administrator sees how much each account uses, never what it studies: courses, material and
answers stay private.
"""

import secrets
import uuid

from fastapi import APIRouter, BackgroundTasks, Depends, Response, status
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.auth import passwords
from app.auth.dependencies import require_admin
from app.core.config import get_settings
from app.core.errors import ConflictError, NotFoundError
from app.db.session import get_db
from app.email.sender import EmailSender, get_email_sender
from app.models.auth import Invitation
from app.models.course import Course
from app.models.document import Document
from app.models.review import Answer
from app.models.user import User
from app.schemas.admin import (
    AdminSummary,
    AdminUser,
    AdminUserUpdate,
    InvitationCreate,
    InvitationCreated,
    InvitationRead,
    TemporaryPassword,
)
from app.schemas.community import ReportRead
from app.services import accounts, invitations, marketplace, moderation, quota
from app.storage.documents import DocumentStorage, get_document_storage

router = APIRouter(prefix="/admin", tags=["admin"], dependencies=[Depends(require_admin)])

DB = Depends(get_db)


def _invitation_read(db: Session, invitation: Invitation) -> InvitationRead:
    used_by = db.get(User, invitation.used_by) if invitation.used_by else None
    return InvitationRead(
        id=invitation.id,
        note=invitation.note,
        email=invitation.email,
        status=invitations.status_of(invitation),  # type: ignore[arg-type]
        created_at=invitation.created_at,
        expires_at=invitation.expires_at,
        used_at=invitation.used_at,
        used_by_email=used_by.email if used_by else None,
    )


def _admin_user(db: Session, user: User) -> AdminUser:
    last = db.scalar(select(func.max(Answer.created_at)).where(Answer.user_id == user.id))
    courses = db.scalar(select(func.count()).select_from(Course).where(Course.user_id == user.id))
    answers = db.scalar(select(func.count()).select_from(Answer).where(Answer.user_id == user.id))
    storage = db.scalar(
        select(func.coalesce(func.sum(Document.size_bytes), 0))
        .join(Course, Course.id == Document.course_id)
        .where(Course.user_id == user.id)
    )
    return AdminUser(
        id=user.id,
        email=user.email,
        username=user.username,
        display_name=user.display_name,
        created_at=user.created_at,
        last_active_at=last,
        is_admin=user.is_admin,
        is_active=user.is_active,
        course_count=courses or 0,
        answer_count=answers or 0,
        storage_bytes=storage or 0,
        evaluations_today=quota.used_today(db, user.id, quota.EVALUATION),
        generations_today=quota.used_today(db, user.id, quota.GENERATION),
        evaluations_limit=quota.limit_for(user, quota.EVALUATION),
        generations_limit=quota.limit_for(user, quota.GENERATION),
        storage_limit_bytes=quota.storage_limit_bytes(user),
        custom_limits=any(
            v is not None
            for v in (user.limit_evaluations, user.limit_generations, user.limit_storage_mb)
        ),
    )


def _user(db: Session, user_id: uuid.UUID) -> User:
    user = db.get(User, user_id)
    if user is None:
        raise NotFoundError("Account not found")
    return user


@router.get("/summary", response_model=AdminSummary)
def summary(db: Session = DB) -> AdminSummary:
    settings = get_settings()
    total = db.scalar(select(func.count()).select_from(User)) or 0
    active = db.scalar(select(func.count()).select_from(User).where(User.is_active)) or 0
    return AdminSummary(
        users=total,
        active_users=active,
        ai_requests_today=quota.total_today(db),
        shared_daily_cap=settings.ai_shared_daily_cap,
        registration_open=settings.registration_open,
        email_enabled=settings.email_backend == "smtp",
        default_evaluations=settings.ai_daily_evaluations,
        default_generations=settings.ai_daily_generations,
        default_storage_mb=settings.storage_limit_mb,
        open_reports=moderation.open_count(db),
    )


@router.get("/users", response_model=list[AdminUser])
def list_users(db: Session = DB) -> list[AdminUser]:
    users = db.scalars(select(User).order_by(User.created_at)).all()
    return [_admin_user(db, user) for user in users]


@router.patch("/users/{user_id}", response_model=AdminUser)
def update_user(
    user_id: uuid.UUID,
    payload: AdminUserUpdate,
    admin: User = Depends(require_admin),
    db: Session = DB,
) -> AdminUser:
    user = _user(db, user_id)
    fields = payload.model_fields_set
    if "is_active" in fields and payload.is_active is not None:
        if user.id == admin.id and not payload.is_active:
            raise ConflictError("You can't suspend your own account.")
        accounts.set_active(db, user.id, payload.is_active)
    for name in ("limit_evaluations", "limit_generations", "limit_storage_mb"):
        if name in fields:
            setattr(user, name, getattr(payload, name))
    db.commit()
    db.refresh(user)
    return _admin_user(db, user)


@router.delete("/users/{user_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_user(
    user_id: uuid.UUID,
    admin: User = Depends(require_admin),
    db: Session = DB,
    storage: DocumentStorage = Depends(get_document_storage),
) -> Response:
    if user_id == admin.id:
        raise ConflictError("You can't delete your own account here.")
    _user(db, user_id)
    accounts.delete_account(db, storage, user_id)
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.post("/users/{user_id}/password", response_model=TemporaryPassword)
def reset_password(user_id: uuid.UUID, db: Session = DB) -> TemporaryPassword:
    """For someone who lost their password and has no working email link: a new random password,
    shown once. Every session of that account ends. They should change it after signing in."""
    user = _user(db, user_id)
    password = secrets.token_urlsafe(12)
    passwords.set_password(db, user, password)
    db.commit()
    return TemporaryPassword(password=password)


@router.delete("/reviews/{review_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_review(review_id: uuid.UUID, db: Session = DB) -> None:
    """Moderation: removes a marketplace review (abuse, spam)."""
    marketplace.moderate_review(db, review_id)


@router.get("/reports", response_model=list[ReportRead])
def list_reports(db: Session = DB) -> list[ReportRead]:
    """What people reported (a person, a message, a review): open ones first."""
    return moderation.listed(db)


@router.post("/reports/{report_id}/resolve", status_code=status.HTTP_204_NO_CONTENT)
def resolve_report(report_id: uuid.UUID, db: Session = DB) -> None:
    moderation.set_resolved(db, report_id, True)


@router.post("/reports/{report_id}/reopen", status_code=status.HTTP_204_NO_CONTENT)
def reopen_report(report_id: uuid.UUID, db: Session = DB) -> None:
    moderation.set_resolved(db, report_id, False)


@router.get("/invitations", response_model=list[InvitationRead])
def list_invitations(db: Session = DB) -> list[InvitationRead]:
    rows = db.scalars(select(Invitation).order_by(Invitation.created_at.desc())).all()
    return [_invitation_read(db, row) for row in rows]


@router.post("/invitations", response_model=InvitationCreated, status_code=status.HTTP_201_CREATED)
def create_invitation(
    payload: InvitationCreate,
    background_tasks: BackgroundTasks,
    admin: User = Depends(require_admin),
    db: Session = DB,
    sender: EmailSender = Depends(get_email_sender),
) -> InvitationCreated:
    invitation, token = invitations.create(db, admin.id, payload.email, payload.note, payload.days)
    base = _invitation_read(db, invitation)
    settings = get_settings()
    link = f"{settings.public_app_url.rstrip('/')}/?invite={token}"
    emailed = bool(payload.email and payload.send_email and settings.email_backend == "smtp")
    if emailed:
        days = payload.days or settings.invitation_ttl_days
        subject, body = invitations.invitation_email(link, days, admin.display_name)
        background_tasks.add_task(sender.send, str(payload.email).lower(), subject, body)
    return InvitationCreated(**base.model_dump(), link=link, emailed=emailed)


@router.delete("/invitations/{invitation_id}", response_model=InvitationRead)
def revoke_invitation(invitation_id: uuid.UUID, db: Session = DB) -> InvitationRead:
    return _invitation_read(db, invitations.revoke(db, invitation_id))
