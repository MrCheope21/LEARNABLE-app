"""Invitations, account administration and the daily limits."""

import uuid
from datetime import timedelta

import pytest
from conftest import DEFAULT_PASSWORD
from sqlalchemy import select

from app.core.config import get_settings
from app.core.errors import QuotaExceededError
from app.db.types import utc_now
from app.models.auth import Invitation
from app.models.user import User
from app.services import quota

API = "/api/v1"


def _user(db, email):
    return db.scalar(select(User).where(User.email == email))


@pytest.fixture
def admin(auth_headers, db_session):
    headers = auth_headers("boss@example.com")
    _user(db_session, "boss@example.com").is_admin = True
    db_session.commit()
    return headers


@pytest.fixture
def invite_only(monkeypatch):
    monkeypatch.setenv("REGISTRATION_OPEN", "false")
    get_settings.cache_clear()
    yield
    monkeypatch.delenv("REGISTRATION_OPEN")
    get_settings.cache_clear()


def _register(client, email, invite=None):
    body = {"email": email, "password": DEFAULT_PASSWORD}
    if invite is not None:
        body["invite"] = invite
    return client.post(f"{API}/auth/register", json=body)


def _invite(client, admin, **body):
    created = client.post(f"{API}/admin/invitations", json=body, headers=admin)
    assert created.status_code == 201, created.text
    return created.json()


def _code(invitation):
    return invitation["link"].split("invite=")[1]


def test_only_administrators_reach_the_admin_api(client, auth_headers, admin):
    plain = auth_headers("plain@example.com")
    for path in ("/admin/users", "/admin/invitations", "/admin/summary"):
        assert client.get(f"{API}{path}", headers=plain).status_code == 403
        assert client.get(f"{API}{path}").status_code == 401
        assert client.get(f"{API}{path}", headers=admin).status_code == 200
    assert client.get(f"{API}/auth/me", headers=admin).json()["is_admin"] is True
    assert client.get(f"{API}/auth/me", headers=plain).json()["is_admin"] is False


def test_with_sign_up_closed_an_invitation_is_needed(client, admin, invite_only):
    refused = _register(client, "stranger@example.com")
    assert (refused.status_code, refused.json()["error_type"]) == (403, "invitation_invalid")
    assert _register(client, "stranger@example.com", "made-up-code").status_code == 403

    invitation = _invite(client, admin, note="Marco")
    assert invitation["status"] == "pending"
    assert _register(client, "marco@example.com", _code(invitation)).status_code == 201

    # One use only, whoever tries again.
    assert _register(client, "other@example.com", _code(invitation)).status_code == 403
    listed = client.get(f"{API}/admin/invitations", headers=admin).json()
    assert (listed[0]["status"], listed[0]["used_by_email"]) == ("used", "marco@example.com")


def test_the_code_is_never_stored_in_clear(client, admin, db_session):
    invitation = _invite(client, admin)
    stored = db_session.scalar(
        select(Invitation).where(Invitation.id == uuid.UUID(invitation["id"]))
    )
    assert _code(invitation) not in stored.token_hash
    assert "link" not in client.get(f"{API}/admin/invitations", headers=admin).json()[0]


def test_an_invitation_can_be_tied_to_an_address(client, admin, invite_only):
    invitation = _invite(client, admin, email="Anna@Example.com")
    assert _register(client, "someone-else@example.com", _code(invitation)).status_code == 403
    assert _register(client, "anna@example.com", _code(invitation)).status_code == 201


def test_revoked_and_expired_invitations_do_not_work(client, admin, invite_only, db_session):
    revoked = _invite(client, admin)
    done = client.delete(f"{API}/admin/invitations/{revoked['id']}", headers=admin)
    assert done.json()["status"] == "revoked"
    assert _register(client, "late@example.com", _code(revoked)).status_code == 403

    expired = _invite(client, admin)
    row = db_session.get(Invitation, uuid.UUID(expired["id"]))
    row.expires_at = utc_now() - timedelta(minutes=1)
    db_session.commit()
    assert _register(client, "late2@example.com", _code(expired)).status_code == 403


def test_open_sign_up_ignores_invitations(client):
    assert _register(client, "free@example.com").status_code == 201


def test_suspend_reactivate_reset_password_and_delete(client, admin, auth_headers, db_session):
    victim = auth_headers("victim@example.com")
    victim_id = str(_user(db_session, "victim@example.com").id)

    off = client.patch(f"{API}/admin/users/{victim_id}", json={"is_active": False}, headers=admin)
    assert off.json()["is_active"] is False
    assert client.get(f"{API}/auth/me", headers=victim).status_code == 401
    login = client.post(
        f"{API}/auth/login", json={"email": "victim@example.com", "password": DEFAULT_PASSWORD}
    )
    assert login.status_code == 403
    client.patch(f"{API}/admin/users/{victim_id}", json={"is_active": True}, headers=admin)

    temp = client.post(f"{API}/admin/users/{victim_id}/password", headers=admin).json()["password"]
    new_login = client.post(
        f"{API}/auth/login", json={"email": "victim@example.com", "password": temp}
    )
    assert new_login.status_code == 200

    assert client.delete(f"{API}/admin/users/{victim_id}", headers=admin).status_code == 204
    assert _user(db_session, "victim@example.com") is None


def test_an_administrator_cannot_suspend_or_delete_themselves(client, admin, db_session):
    me = str(_user(db_session, "boss@example.com").id)
    assert (
        client.patch(
            f"{API}/admin/users/{me}", json={"is_active": False}, headers=admin
        ).status_code
        == 409
    )
    assert client.delete(f"{API}/admin/users/{me}", headers=admin).status_code == 409


def test_the_user_list_shows_usage_but_never_study_content(client, admin, auth_headers):
    auth_headers("reader@example.com")
    rows = client.get(f"{API}/admin/users", headers=admin).json()
    row = next(r for r in rows if r["email"] == "reader@example.com")
    assert {"course_count", "storage_bytes", "evaluations_today", "evaluations_limit"} <= set(row)
    assert not {"courses", "documents", "answers", "text"} & set(row)


def test_daily_limits_count_per_account_and_admins_have_none(
    client, db_session, auth_headers, admin
):
    auth_headers("limited@example.com")
    user = _user(db_session, "limited@example.com")
    user.limit_evaluations = 2
    db_session.commit()
    quota.charge(db_session, user, quota.EVALUATION)
    quota.charge(db_session, user, quota.EVALUATION)
    with pytest.raises(QuotaExceededError):
        quota.charge(db_session, user, quota.EVALUATION)
    quota.charge(db_session, user, quota.GENERATION)  # its own counter

    boss = _user(db_session, "boss@example.com")
    boss.limit_evaluations = 1
    for _ in range(3):
        quota.charge(db_session, boss, quota.EVALUATION)


def test_the_default_limit_applies_and_the_admin_can_change_one_account(
    client, admin, auth_headers, db_session
):
    auth_headers("normal@example.com")
    uid = str(_user(db_session, "normal@example.com").id)
    row = lambda: next(  # noqa: E731
        r for r in client.get(f"{API}/admin/users", headers=admin).json() if r["id"] == uid
    )
    assert (row()["evaluations_limit"], row()["custom_limits"]) == (100, False)
    client.patch(f"{API}/admin/users/{uid}", json={"limit_evaluations": 5}, headers=admin)
    assert (row()["evaluations_limit"], row()["custom_limits"]) == (5, True)
    client.patch(f"{API}/admin/users/{uid}", json={"limit_evaluations": None}, headers=admin)
    assert (row()["evaluations_limit"], row()["custom_limits"]) == (100, False)


def test_the_shared_guard_stops_everyone_but_administrators(
    client, auth_headers, admin, db_session, monkeypatch
):
    monkeypatch.setenv("AI_SHARED_DAILY_CAP", "10")
    monkeypatch.setenv("AI_ADMIN_RESERVE_PERCENT", "20")
    get_settings.cache_clear()
    try:
        auth_headers("guest@example.com")
        guest = _user(db_session, "guest@example.com")
        for _ in range(8):
            quota.charge(db_session, guest, quota.EVALUATION)
        with pytest.raises(QuotaExceededError) as stopped:
            quota.charge(db_session, guest, quota.EVALUATION)
        assert stopped.value.details["reason"] == "shared_limit"
        quota.charge(db_session, _user(db_session, "boss@example.com"), quota.EVALUATION)
    finally:
        monkeypatch.delenv("AI_SHARED_DAILY_CAP")
        monkeypatch.delenv("AI_ADMIN_RESERVE_PERCENT")
        get_settings.cache_clear()


def test_the_storage_limit_refuses_an_upload_that_does_not_fit(client, auth_headers, db_session):
    headers = auth_headers("uploader@example.com")
    course = client.post(
        f"{API}/courses", json={"title": "Corso", "language": "it"}, headers=headers
    ).json()
    user = _user(db_session, "uploader@example.com")
    user.limit_storage_mb = 1
    db_session.commit()
    big = b"Una frase di prova sul contratto di mutuo. " * 30_000  # ~1.3 MB
    refused = client.post(
        f"{API}/courses/{course['id']}/documents",
        files={"file": ("grande.txt", big, "text/plain")},
        headers=headers,
    )
    assert (refused.status_code, refused.json()["error_type"]) == (413, "storage_quota_exceeded")
    small = client.post(
        f"{API}/courses/{course['id']}/documents",
        files={"file": ("piccolo.txt", b"Il mutuo e un contratto di prestito.", "text/plain")},
        headers=headers,
    )
    assert small.status_code in (201, 202)


class _Outbox:
    def __init__(self):
        self.sent = []

    def send(self, to, subject, body):
        self.sent.append((to, subject, body))


@pytest.fixture
def outbox():
    from app.email.sender import get_email_sender
    from app.main import app

    box = _Outbox()
    app.dependency_overrides[get_email_sender] = lambda: box
    yield box
    app.dependency_overrides.pop(get_email_sender, None)


def test_an_invitation_with_an_address_is_emailed_when_the_server_can_send(
    client, admin, outbox, monkeypatch
):
    monkeypatch.setenv("EMAIL_BACKEND", "smtp")
    monkeypatch.setenv("SMTP_HOST", "smtp.example.com")
    monkeypatch.setenv("SMTP_FROM", "Recallable <no-reply@example.com>")
    get_settings.cache_clear()
    try:
        summary = client.get(f"{API}/admin/summary", headers=admin).json()
        assert summary["email_enabled"] is True
        created = _invite(client, admin, email="Anna@Example.com", note="Anna")
        assert created["emailed"] is True
        (to, subject, body) = outbox.sent[0]
        assert to == "anna@example.com"
        assert "Recallable" in subject
        assert created["link"] in body  # the same link the administrator sees
        # An invitation without an address, or with send_email off, is not emailed.
        assert _invite(client, admin)["emailed"] is False
        assert _invite(client, admin, email="b@example.com", send_email=False)["emailed"] is False
        assert len(outbox.sent) == 1
    finally:
        for name in ("EMAIL_BACKEND", "SMTP_HOST", "SMTP_FROM"):
            monkeypatch.delenv(name)
        get_settings.cache_clear()


def test_nothing_is_emailed_when_the_server_cannot_send(client, admin, outbox):
    summary = client.get(f"{API}/admin/summary", headers=admin).json()
    assert summary["email_enabled"] is False
    assert _invite(client, admin, email="c@example.com")["emailed"] is False
    assert outbox.sent == []
