import uuid
from datetime import UTC, datetime, timedelta

import jwt
import pytest
from conftest import DEFAULT_PASSWORD

from app.auth.security import create_access_token, hash_password, verify_password
from app.core.config import get_settings


def _register(client, email: str, password: str = DEFAULT_PASSWORD):
    return client.post("/api/v1/auth/register", json={"email": email, "password": password})


def _login(client, email: str, password: str = DEFAULT_PASSWORD):
    return client.post("/api/v1/auth/login", json={"email": email, "password": password})


def _bearer(token: str) -> dict[str, str]:
    return {"Authorization": f"Bearer {token}"}


def test_register_then_login_then_me(client):
    register = _register(client, "student@example.com")
    assert register.status_code == 201
    assert register.json()["email"] == "student@example.com"

    login = _login(client, "student@example.com")
    assert login.status_code == 200
    token = login.json()["access_token"]

    me = client.get("/api/v1/auth/me", headers=_bearer(token))
    assert me.status_code == 200
    assert me.json()["email"] == "student@example.com"


def test_duplicate_registration_rejected(client):
    assert _register(client, "dupe@example.com").status_code == 201
    second = _register(client, "dupe@example.com")
    assert second.status_code == 409
    assert second.json()["error_type"] == "conflict"


def test_email_is_case_and_whitespace_insensitive(client):
    assert _register(client, "Mixed.Case@Example.com").status_code == 201
    # Same address, different case: same account, not a second one.
    assert _register(client, "mixed.case@example.com").status_code == 409
    # Login works with any casing and surrounding whitespace.
    assert _login(client, "  MIXED.CASE@EXAMPLE.COM ").status_code == 200


@pytest.mark.parametrize("password", ["", "short", "x" * 11, "x" * 129])
def test_password_policy_enforced_on_register(client, password):
    response = _register(client, "policy@example.com", password)
    assert response.status_code == 422
    assert response.json()["error_type"] == "validation_error"


def test_password_whitespace_is_significant(client):
    assert _register(client, "spaces@example.com", "  padded password  ").status_code == 201
    assert _login(client, "spaces@example.com", "  padded password  ").status_code == 200
    assert _login(client, "spaces@example.com", "padded password").status_code == 401


def test_login_with_wrong_password_rejected(client):
    _register(client, "wrongpw@example.com")
    response = _login(client, "wrongpw@example.com", "not-the-right-password")
    assert response.status_code == 401
    assert response.json()["error_type"] == "authentication_failed"
    assert response.headers["WWW-Authenticate"] == "Bearer"


def test_login_unknown_email_gives_same_error_as_wrong_password(client):
    _register(client, "known@example.com")
    unknown = _login(client, "unknown@example.com")
    wrong_password = _login(client, "known@example.com", "not-the-right-password")
    assert unknown.status_code == wrong_password.status_code == 401
    assert unknown.json() == wrong_password.json()


def test_unknown_fields_rejected(client):
    response = client.post(
        "/api/v1/auth/register",
        json={"email": "extra@example.com", "password": DEFAULT_PASSWORD, "is_admin": True},
    )
    assert response.status_code == 422


def test_me_without_token_rejected(client):
    response = client.get("/api/v1/auth/me")
    assert response.status_code == 401
    assert response.json()["error_type"] == "authentication_failed"


def test_me_with_non_bearer_scheme_rejected(client):
    response = client.get("/api/v1/auth/me", headers={"Authorization": "Basic dXNlcjpwYXNz"})
    assert response.status_code == 401


def _forged_token(**overrides) -> str:
    now = datetime.now(UTC)
    payload = {
        "sub": str(uuid.uuid4()),
        "type": "access",
        "iat": now,
        "exp": now + timedelta(minutes=5),
    }
    payload.update(overrides)
    secret = get_settings().auth_secret.get_secret_value()
    return jwt.encode(payload, secret, algorithm="HS256")


def test_rejected_tokens(client, auth_headers):
    headers = auth_headers("token-owner@example.com")
    user_id = client.get("/api/v1/auth/me", headers=headers).json()["id"]
    valid = headers["Authorization"].removeprefix("Bearer ")

    now = datetime.now(UTC)
    bad_tokens = {
        "garbage": "not-a-jwt",
        "tampered_signature": valid[:-4] + ("AAAA" if not valid.endswith("AAAA") else "BBBB"),
        "wrong_secret": jwt.encode(
            {"sub": user_id, "type": "access", "iat": now, "exp": now + timedelta(minutes=5)},
            "a-completely-different-secret-that-is-long-enough",
            algorithm="HS256",
        ),
        "alg_none": jwt.encode(
            {"sub": user_id, "type": "access", "iat": now, "exp": now + timedelta(minutes=5)},
            None,
            algorithm="none",
        ),
        "expired": _forged_token(
            sub=user_id, iat=now - timedelta(hours=2), exp=now - timedelta(hours=1)
        ),
        "wrong_type": _forged_token(sub=user_id, type="refresh"),
        "missing_exp": jwt.encode(
            {"sub": user_id, "type": "access", "iat": now},
            get_settings().auth_secret.get_secret_value(),
            algorithm="HS256",
        ),
        "nonexistent_user": _forged_token(),
        "non_uuid_subject": _forged_token(sub="not-a-uuid"),
    }
    for name, token in bad_tokens.items():
        response = client.get("/api/v1/auth/me", headers=_bearer(token))
        assert response.status_code == 401, f"{name} was accepted"


def test_access_token_round_trip():
    user_id = uuid.uuid4()
    token = create_access_token(user_id)
    payload = jwt.decode(token, get_settings().auth_secret.get_secret_value(), algorithms=["HS256"])
    assert payload["sub"] == str(user_id)
    assert payload["type"] == "access"


def test_password_hashing_handles_long_passwords():
    # bcrypt silently truncated at 72 bytes; Argon2 must distinguish passwords that differ only
    # after byte 72.
    base = "a" * 80
    hashed = hash_password(base + "1")
    assert verify_password(base + "1", hashed)
    assert not verify_password(base + "2", hashed)


def _with_username(client, email: str, username: str):
    return client.post(
        "/api/v1/auth/register",
        json={"email": email, "password": DEFAULT_PASSWORD, "username": username},
    )


def test_login_with_the_username_or_the_email(client):
    assert _with_username(client, "ada@example.com", "Ada.L").json()["username"] == "ada.l"
    for who in ("ada.l", "ADA.L", " ada.l ", "ada@example.com"):
        assert _login(client, who).status_code == 200, who
    assert _login(client, "ada.l", "not-the-right-password").status_code == 401
    unknown = _login(client, "nobody.here")
    assert unknown.status_code == 401
    assert unknown.json() == _login(client, "ada.l", "not-the-right-password").json()


def test_usernames_are_unique_and_checked(client):
    assert _with_username(client, "one@example.com", "sharedname").status_code == 201
    taken = _with_username(client, "two@example.com", "SharedName")
    assert taken.status_code == 409
    assert _with_username(client, "three@example.com", "has space").status_code == 422
    assert _with_username(client, "four@example.com", "a@b.c").status_code == 422
    assert _with_username(client, "five@example.com", "ab").status_code == 422


def test_a_username_can_be_set_changed_and_cleared_in_the_profile(client):
    _register(client, "later@example.com")
    _with_username(client, "taken@example.com", "taken")
    token = _login(client, "later@example.com").json()["access_token"]
    patch = lambda name: client.patch(  # noqa: E731
        "/api/v1/auth/me", json={"username": name}, headers=_bearer(token)
    )
    assert patch("Later_1").json()["username"] == "later_1"
    assert _login(client, "later_1").status_code == 200
    assert patch("taken").status_code == 409
    assert patch("x").status_code in (400, 422)
    assert patch("later_1").status_code == 200  # your own name isn't "taken"
    assert patch("").json()["username"] is None
    assert _login(client, "later_1").status_code == 401


def test_registration_can_be_closed_without_locking_out_existing_accounts(client, monkeypatch):
    from app.core.config import get_settings

    _register(client, "member@example.com")
    monkeypatch.setenv("REGISTRATION_OPEN", "false")
    get_settings.cache_clear()
    try:
        closed = _register(client, "newcomer@example.com")
        assert (closed.status_code, closed.json()["error_type"]) == (403, "registration_closed")
        assert _login(client, "member@example.com").status_code == 200
    finally:
        monkeypatch.delenv("REGISTRATION_OPEN")
        get_settings.cache_clear()
