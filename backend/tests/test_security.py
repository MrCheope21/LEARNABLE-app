"""Attempt limits (app/core/rate_limit.py) and security headers (app/api/headers.py)."""

import pytest

from app.api.headers import CONTENT_SECURITY_POLICY
from app.core.config import get_settings

PASSWORD = "correct-horse-battery-staple"


WRONG = "wrong-password-123"


def login(client, email, password=WRONG):
    return client.post("/api/v1/auth/login", json={"email": email, "password": password})


def test_repeated_wrong_passwords_for_one_address_are_slowed_down(client, auth_headers):
    auth_headers("victim@example.com")
    for _ in range(10):
        assert login(client, "victim@example.com").status_code == 401
    blocked = login(client, "victim@example.com", PASSWORD)
    assert blocked.status_code == 429
    assert blocked.json()["error_type"] == "rate_limited"
    assert int(blocked.headers["Retry-After"]) > 0
    # Other accounts are unaffected.
    auth_headers("other@example.com")
    assert login(client, "other@example.com", PASSWORD).status_code == 200


def test_unknown_addresses_are_limited_the_same_way(client):
    for _ in range(10):
        assert login(client, "nobody@example.com").status_code == 401
    assert login(client, "nobody@example.com").status_code == 429


def test_one_ip_cannot_try_endlessly_across_addresses(client):
    statuses = [login(client, f"user{i}@example.com").status_code for i in range(31)]
    assert statuses[:30] == [401] * 30
    assert statuses[30] == 429


def test_sign_ups_from_one_ip_are_limited(client):
    statuses = [
        client.post(
            "/api/v1/auth/register", json={"email": f"new{i}@example.com", "password": PASSWORD}
        ).status_code
        for i in range(11)
    ]
    assert statuses == [201] * 10 + [429]


def test_password_reset_requests_from_one_ip_are_limited(client):
    statuses = [
        client.post(
            "/api/v1/auth/password-reset/request", json={"email": f"x{i}@example.com"}
        ).status_code
        for i in range(11)
    ]
    assert statuses == [202] * 10 + [429]


def test_limits_can_be_switched_off(client, monkeypatch):
    monkeypatch.setattr(get_settings(), "rate_limits_enabled", False)
    assert all(login(client, "off@example.com").status_code == 401 for _ in range(15))


@pytest.mark.parametrize("path", ["/health", "/api/v1/auth/me"])
def test_every_response_carries_the_security_headers(client, path):
    response = client.get(path)
    assert response.headers["X-Content-Type-Options"] == "nosniff"
    assert response.headers["X-Frame-Options"] == "DENY"
    assert response.headers["Referrer-Policy"] == "no-referrer"
    assert "microphone=(self)" in response.headers["Permissions-Policy"]
    assert response.headers["Content-Security-Policy"] == CONTENT_SECURITY_POLICY
    assert "frame-ancestors 'none'" in CONTENT_SECURITY_POLICY
    assert "Strict-Transport-Security" not in response.headers


def test_api_responses_are_not_cached_and_https_gets_hsts(client, auth_headers):
    headers = auth_headers("cache@example.com")
    me = client.get("/api/v1/auth/me", headers=headers)
    assert me.headers["Cache-Control"] == "no-store"
    secure = client.get("https://testserver/health")
    assert secure.headers["Strict-Transport-Security"].startswith("max-age=")


def test_the_docs_page_can_still_load_its_scripts(client):
    assert "Content-Security-Policy" not in client.get("/docs").headers
