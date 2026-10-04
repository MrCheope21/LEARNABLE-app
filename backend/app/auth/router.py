from fastapi import APIRouter, BackgroundTasks, Depends, Response, status
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.auth import passwords
from app.auth.dependencies import get_current_user
from app.auth.schemas import (
    MessageRead,
    PasswordChange,
    PasswordResetConfirm,
    PasswordResetRequest,
    Token,
    UserCreate,
    UserLogin,
    UserPreferencesUpdate,
    UserRead,
)
from app.auth.security import (
    create_access_token,
    hash_password,
    password_needs_rehash,
    spend_equivalent_verification_time,
    verify_password,
)
from app.core.config import get_settings
from app.core.errors import AuthenticationError, ConflictError, InvalidRequestError
from app.core.rate_limit import limiter, per_ip, per_user
from app.db.session import get_db
from app.email.sender import EmailSender, get_email_sender
from app.models.user import User

router = APIRouter(prefix="/auth", tags=["auth"])

_FAILED_LOGINS = 10
_FAILED_LOGIN_WINDOW = 900

_INVALID_CREDENTIALS = "Incorrect email or password"


@router.post(
    "/register",
    response_model=UserRead,
    status_code=status.HTTP_201_CREATED,
    dependencies=[Depends(per_ip("register", 10, 3600))],
)
def register(payload: UserCreate, db: Session = Depends(get_db)) -> User:
    if db.scalar(select(User).where(User.email == payload.email)) is not None:
        raise ConflictError("Email already registered")
    user = User(
        email=payload.email,
        hashed_password=hash_password(payload.password),
        timezone=payload.timezone or "UTC",
        language=payload.language,
    )
    db.add(user)
    try:
        db.commit()
    except IntegrityError as exc:
        # Two concurrent registrations for the same email both pass the check above; the unique
        # index catches the loser.
        db.rollback()
        raise ConflictError("Email already registered") from exc
    db.refresh(user)
    return user


@router.post("/login", response_model=Token, dependencies=[Depends(per_ip("login", 30, 300))])
def login(payload: UserLogin, db: Session = Depends(get_db)) -> Token:
    # Wrong passwords for one address, from anywhere: slows guessing spread over many IPs.
    # Unknown addresses count the same, so the limit doesn't reveal who is registered.
    failures = f"login-failures:{payload.email}"
    limiter.hit_check(failures, _FAILED_LOGINS, _FAILED_LOGIN_WINDOW)
    user = db.scalar(select(User).where(User.email == payload.email))
    if user is None:
        spend_equivalent_verification_time(payload.password)
        limiter.record(failures, _FAILED_LOGIN_WINDOW)
        raise AuthenticationError(_INVALID_CREDENTIALS)
    if not verify_password(payload.password, user.hashed_password):
        limiter.record(failures, _FAILED_LOGIN_WINDOW)
        raise AuthenticationError(_INVALID_CREDENTIALS)
    if password_needs_rehash(user.hashed_password):
        user.hashed_password = hash_password(payload.password)
        db.commit()
    return Token(access_token=create_access_token(user.id, user.token_version))


@router.get("/me", response_model=UserRead)
def me(current_user: User = Depends(get_current_user)) -> User:
    return current_user


@router.patch("/me", response_model=UserRead)
def update_preferences(
    payload: UserPreferencesUpdate,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> User:
    """Profile and preferences: display name, interface language, timezone, daily goal. A new
    timezone applies from now on: days already recorded keep the date they were recorded under
    (docs/XP_AND_ACTIVITY.md §5)."""
    if payload.timezone is not None:
        current_user.timezone = payload.timezone
    if payload.daily_goal is not None:
        current_user.daily_goal = payload.daily_goal
    if payload.language is not None:
        current_user.language = payload.language
    if payload.display_name is not None:
        current_user.display_name = " ".join(payload.display_name.split()) or None
    db.commit()
    db.refresh(current_user)
    return current_user


_RESET_ACCEPTED = (
    "If an account exists for this email, a link to reset its password is on its way. "
    "Check your inbox (and spam folder)."
)


@router.post(
    "/password-reset/request",
    response_model=MessageRead,
    status_code=status.HTTP_202_ACCEPTED,
    dependencies=[Depends(per_ip("password-reset", 10, 3600))],
)
def request_password_reset(
    payload: PasswordResetRequest,
    background_tasks: BackgroundTasks,
    db: Session = Depends(get_db),
    sender: EmailSender = Depends(get_email_sender),
) -> MessageRead:
    """ "Forgot your password?". Always the same 202 answer, whether or not the email has an
    account, so it can't be used to find out who is registered. At most 3 links per account per
    hour; each link works once, for PASSWORD_RESET_TTL_MINUTES, and retires the older ones."""
    user = db.scalar(select(User).where(User.email == payload.email))
    if user is not None:
        link = passwords.issue_reset_link(db, user)
        db.commit()
        if link is not None:
            subject, body = passwords.reset_email(link, get_settings().password_reset_ttl_minutes)
            # Sent after the response, so timing doesn't reveal whether the account exists.
            background_tasks.add_task(sender.send, user.email, subject, body)
    return MessageRead(detail=_RESET_ACCEPTED)


@router.post(
    "/password-reset/confirm",
    status_code=status.HTTP_204_NO_CONTENT,
    dependencies=[Depends(per_ip("password-reset-confirm", 20, 3600))],
)
def confirm_password_reset(
    payload: PasswordResetConfirm, db: Session = Depends(get_db)
) -> Response:
    """Sets the new password from a valid link (422 `invalid_reset_token` otherwise). Every
    existing session of the account ends; sign in again with the new password."""
    passwords.reset_with_token(db, payload.token, payload.new_password)
    db.commit()
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.post(
    "/change-password",
    response_model=Token,
    dependencies=[Depends(per_user("change-password", 10, 900))],
)
def change_password(
    payload: PasswordChange,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> Token:
    """Needs the current password (422 `wrong_password`). Ends every other session and returns
    a fresh token for this one."""
    if not verify_password(payload.current_password, current_user.hashed_password):
        raise InvalidRequestError(
            "Your current password is incorrect.", details={"reason": "wrong_password"}
        )
    passwords.set_password(db, current_user, payload.new_password)
    db.commit()
    db.refresh(current_user)
    return Token(access_token=create_access_token(current_user.id, current_user.token_version))
