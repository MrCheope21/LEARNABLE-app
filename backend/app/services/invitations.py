"""Invitations: how people the administrator authorizes get an account."""

import hashlib
import secrets
import uuid
from datetime import timedelta

from sqlalchemy import select, update
from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.core.errors import InvitationInvalidError, NotFoundError
from app.db.types import utc_now
from app.models.auth import Invitation


def _hash(token: str) -> str:
    return hashlib.sha256(token.encode()).hexdigest()


def create(
    db: Session, admin_id: uuid.UUID, email: str | None, note: str, days: int | None
) -> tuple[Invitation, str]:
    """Returns the invitation and its code. The code is shown once and never stored."""
    token = secrets.token_urlsafe(24)
    ttl = days or get_settings().invitation_ttl_days
    invitation = Invitation(
        token_hash=_hash(token),
        created_by=admin_id,
        expires_at=utc_now() + timedelta(days=ttl),
        email=email.lower() if email else None,
        note=note.strip(),
    )
    db.add(invitation)
    db.commit()
    db.refresh(invitation)
    return invitation, token


def invitation_email(link: str, days: int, inviter: str | None) -> tuple[str, str]:
    who = inviter or "Un amministratore / An administrator"
    subject = "Invito a Recallable / You're invited to Recallable"
    body = (
        f"{who} ti ha invitato a Recallable, l'app per studiare e ripassare nel momento giusto.\n\n"
        f"Crea il tuo account da qui (il link vale per una persona, per {days} giorni):\n{link}\n\n"
        "Se non te l'aspettavi, ignora questa email.\n\n"
        "---\n\n"
        f"{who} invited you to Recallable, the app to study and review at the right time.\n\n"
        f"Create your account here (the link works for one person, for {days} days):\n{link}\n\n"
        "If you weren't expecting this, ignore this email.\n"
    )
    return subject, body


def status_of(invitation: Invitation) -> str:
    if invitation.used_at is not None:
        return "used"
    if invitation.revoked_at is not None:
        return "revoked"
    if invitation.expires_at <= utc_now():
        return "expired"
    return "pending"


def revoke(db: Session, invitation_id: uuid.UUID) -> Invitation:
    invitation = db.get(Invitation, invitation_id)
    if invitation is None:
        raise NotFoundError("Invitation not found")
    if invitation.used_at is None and invitation.revoked_at is None:
        invitation.revoked_at = utc_now()
        db.commit()
        db.refresh(invitation)
    return invitation


def check(db: Session, token: str | None, email: str) -> Invitation:
    """The usable invitation for this code and address, or InvitationInvalidError. One message for
    every reason, so a stranger learns nothing about which codes exist."""
    invalid = InvitationInvalidError(
        "An invitation from the administrator is needed to create an account."
    )
    if not token:
        raise invalid
    invitation = db.scalar(select(Invitation).where(Invitation.token_hash == _hash(token.strip())))
    if invitation is None or status_of(invitation) != "pending":
        raise invalid
    if invitation.email and invitation.email != email.lower():
        raise invalid
    return invitation


def consume(db: Session, invitation: Invitation, user_id: uuid.UUID) -> None:
    """Marks it used, atomically: of two simultaneous sign-ups with one code, one fails."""
    result = db.execute(
        update(Invitation)
        .where(Invitation.id == invitation.id, Invitation.used_at.is_(None))
        .values(used_at=utc_now(), used_by=user_id)
    )
    if result.rowcount != 1:  # type: ignore[attr-defined]
        raise InvitationInvalidError(
            "An invitation from the administrator is needed to create an account."
        )
