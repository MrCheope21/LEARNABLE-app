"""Forgot / change / set password (docs/API.md "Auth")."""

import re
from datetime import timedelta

import pytest
from sqlalchemy import select

from app.auth.passwords import MAX_RESETS_PER_HOUR, set_password
from app.db.types import utc_now
from app.email.sender import get_email_sender
from app.main import app
from app.models.auth import PasswordResetToken
from app.models.user import User

EMAIL = "forgetful@example.com"
OLD = "old-password-123456"
NEW = "brand-new-password-789"


class Outbox:
    def __init__(self) -> None:
        self.messages: list[tuple[str, str, str]] = []

    def send(self, to: str, subject: str, body: str) -> None:
        self.messages.append((to, subject, body))

    def token(self, index: int = -1) -> str:
        match = re.search(r"reset-password\?token=([A-Za-z0-9_-]+)", self.messages[index][2])
        assert match, self.messages[index][2]
        return match.group(1)


@pytest.fixture
def outbox(client):
    box = Outbox()
    app.dependency_overrides[get_email_sender] = lambda: box
    return box


@pytest.fixture
def account(client, auth_headers):
    return auth_headers(EMAIL, OLD)


def request_reset(client, email=EMAIL):
    return client.post("/api/v1/auth/password-reset/request", json={"email": email})


def confirm(client, token, password=NEW):
    return client.post(
        "/api/v1/auth/password-reset/confirm", json={"token": token, "new_password": password}
    )


def login(client, password, email=EMAIL):
    return client.post("/api/v1/auth/login", json={"email": email, "password": password})


def test_reset_by_email_link(client, account, outbox):
    response = request_reset(client, " Forgetful@Example.com ")
    assert response.status_code == 202
    [(to, subject, body)] = outbox.messages
    assert to == EMAIL
    assert "Reset your LEARNABLE password" in subject
    assert "http://localhost:5173/reset-password?token=" in body

    assert confirm(client, outbox.token()).status_code == 204
    assert login(client, NEW).status_code == 200
    assert login(client, OLD).status_code == 401
    # The old session ended with the password change.
    assert client.get("/api/v1/auth/me", headers=account).status_code == 401


def test_unknown_emails_get_the_same_answer_and_no_email(client, account, outbox):
    known = request_reset(client)
    unknown = request_reset(client, "nobody@example.com")
    assert (known.status_code, unknown.status_code) == (202, 202)
    assert known.json() == unknown.json()
    assert [to for to, _, _ in outbox.messages] == [EMAIL]


def test_links_work_once_and_only_the_newest(client, account, outbox):
    request_reset(client)
    request_reset(client)
    older, newer = outbox.token(0), outbox.token(1)

    assert confirm(client, older).json()["details"]["reason"] == "invalid_reset_token"
    assert confirm(client, newer).status_code == 204
    reused = confirm(client, newer, "yet-another-password-1")
    assert reused.status_code == 422
    assert reused.json()["details"]["reason"] == "invalid_reset_token"
    assert confirm(client, "x" * 43).json()["details"]["reason"] == "invalid_reset_token"


def test_links_expire(client, account, outbox, db_session):
    request_reset(client)
    row = db_session.scalar(select(PasswordResetToken))
    row.expires_at = utc_now() - timedelta(seconds=1)
    db_session.commit()
    assert confirm(client, outbox.token()).json()["details"]["reason"] == "invalid_reset_token"
    assert login(client, OLD).status_code == 200


def test_reset_emails_are_rate_limited(client, account, outbox):
    for _ in range(MAX_RESETS_PER_HOUR + 2):
        assert request_reset(client).status_code == 202
    assert len(outbox.messages) == MAX_RESETS_PER_HOUR


def test_new_password_must_meet_the_policy(client, account, outbox):
    request_reset(client)
    assert confirm(client, outbox.token(), "short").status_code == 422
    # The link wasn't spent by a rejected password.
    assert confirm(client, outbox.token()).status_code == 204


def test_change_password_ends_other_sessions(client, account):
    other_device = login(client, OLD).json()["access_token"]
    wrong = client.post(
        "/api/v1/auth/change-password",
        json={"current_password": "not-my-password", "new_password": NEW},
        headers=account,
    )
    assert wrong.status_code == 422
    assert wrong.json()["details"]["reason"] == "wrong_password"

    changed = client.post(
        "/api/v1/auth/change-password",
        json={"current_password": OLD, "new_password": NEW},
        headers=account,
    )
    assert changed.status_code == 200
    fresh = {"Authorization": f"Bearer {changed.json()['access_token']}"}
    assert client.get("/api/v1/auth/me", headers=fresh).status_code == 200
    assert client.get("/api/v1/auth/me", headers=account).status_code == 401
    stale = {"Authorization": f"Bearer {other_device}"}
    assert client.get("/api/v1/auth/me", headers=stale).status_code == 401
    assert login(client, NEW).status_code == 200


def test_admin_set_password_retires_links_and_sessions(client, account, outbox, db_session):
    request_reset(client)
    user = db_session.scalar(select(User).where(User.email == EMAIL))
    set_password(db_session, user, NEW)
    db_session.commit()

    assert login(client, NEW).status_code == 200
    assert client.get("/api/v1/auth/me", headers=account).status_code == 401
    assert confirm(client, outbox.token(), "another-password-42").status_code == 422


def test_tokens_from_before_versions_still_work(client, account, db_session):
    """Tokens issued before this change carry no version: they count as version 0."""
    import jwt

    from app.core.config import get_settings

    user = db_session.scalar(select(User).where(User.email == EMAIL))
    now = utc_now()
    legacy = jwt.encode(
        {"sub": str(user.id), "type": "access", "iat": now, "exp": now + timedelta(minutes=5)},
        get_settings().auth_secret.get_secret_value(),
        algorithm="HS256",
    )
    headers = {"Authorization": f"Bearer {legacy}"}
    assert client.get("/api/v1/auth/me", headers=headers).status_code == 200


def test_smtp_needs_a_host_and_sender():
    from pydantic import ValidationError

    from app.core.config import Settings

    with pytest.raises(ValidationError, match="SMTP_HOST and SMTP_FROM"):
        Settings(auth_secret="s" * 40, email_backend="smtp")


def test_smtp_sender_uses_starttls_and_login(monkeypatch):
    from app.email.sender import SmtpEmailSender

    calls = []

    class FakeSMTP:
        def __init__(self, host, port, timeout):
            calls.append(("connect", host, port))

        def __enter__(self):
            return self

        def __exit__(self, *_):
            return False

        def starttls(self):
            calls.append(("starttls",))

        def login(self, user, password):
            calls.append(("login", user))

        def send_message(self, message):
            calls.append(("send", message["To"], message["Subject"]))

    monkeypatch.setattr("app.email.sender.smtplib.SMTP", FakeSMTP)
    SmtpEmailSender("smtp.example.com", 587, "user", "pw", "LEARNABLE <a@b.c>").send(
        "to@example.com", "Hi", "Body"
    )
    assert calls == [
        ("connect", "smtp.example.com", 587),
        ("starttls",),
        ("login", "user"),
        ("send", "to@example.com", "Hi"),
    ]
