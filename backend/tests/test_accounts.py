"""Suspending and deleting accounts."""

import uuid

from conftest import DEFAULT_PASSWORD
from sqlalchemy import func, select

from app.models.course import Course
from app.models.user import User
from app.services import accounts


def _user(db_session, email):
    return db_session.scalar(select(User).where(User.email == email))


def test_a_suspended_account_cannot_sign_in_and_its_sessions_end(client, auth_headers, db_session):
    headers = auth_headers("suspend-me@example.com")
    assert client.get("/api/v1/auth/me", headers=headers).status_code == 200
    user = _user(db_session, "suspend-me@example.com")

    accounts.set_active(db_session, user.id, False)

    # The session it had is over at once.
    assert client.get("/api/v1/auth/me", headers=headers).status_code == 401
    login = client.post(
        "/api/v1/auth/login",
        json={"email": "suspend-me@example.com", "password": DEFAULT_PASSWORD},
    )
    assert (login.status_code, login.json()["error_type"]) == (403, "account_suspended")

    accounts.set_active(db_session, user.id, True)
    again = client.post(
        "/api/v1/auth/login",
        json={"email": "suspend-me@example.com", "password": DEFAULT_PASSWORD},
    )
    assert again.status_code == 200
    # The old token stays dead: reactivating does not bring back earlier sessions.
    assert client.get("/api/v1/auth/me", headers=headers).status_code == 401


def test_a_wrong_password_on_a_suspended_account_is_still_just_wrong(
    client, auth_headers, db_session
):
    auth_headers("quiet@example.com")
    accounts.set_active(db_session, _user(db_session, "quiet@example.com").id, False)
    wrong = client.post(
        "/api/v1/auth/login", json={"email": "quiet@example.com", "password": "not-the-password"}
    )
    assert wrong.status_code == 401


def test_deleting_an_account_removes_its_data_and_nobody_else_s(
    client, auth_headers, db_session, storage
):
    gone = auth_headers("gone@example.com")
    kept = auth_headers("kept@example.com")
    for headers in (gone, kept):
        client.post("/api/v1/courses", json={"title": "Corso", "language": "it"}, headers=headers)
    gone_id = _user(db_session, "gone@example.com").id

    accounts.delete_account(db_session, storage, gone_id)

    assert _user(db_session, "gone@example.com") is None
    assert (
        db_session.scalar(select(func.count()).select_from(Course).where(Course.user_id == gone_id))
        == 0
    )
    assert _user(db_session, "kept@example.com") is not None
    assert len(client.get("/api/v1/courses", headers=kept).json()) == 1
    assert client.get("/api/v1/auth/me", headers=gone).status_code == 401


def test_deleting_an_unknown_account_is_a_clear_error(db_session, storage):
    import pytest

    from app.core.errors import NotFoundError

    with pytest.raises(NotFoundError):
        accounts.delete_account(db_session, storage, uuid.uuid4())
