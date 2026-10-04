"""Profile and interface language (GET/PATCH /auth/me, POST /auth/register)."""

import pytest

PASSWORD = "a-long-enough-password"


def test_a_new_account_speaks_english_with_no_display_name(client, auth_headers):
    me = client.get("/api/v1/auth/me", headers=auth_headers("plain@example.com")).json()
    assert (me["language"], me["display_name"]) == ("en", None)


def test_registration_keeps_the_language_of_the_sign_up_page(client):
    created = client.post(
        "/api/v1/auth/register",
        json={"email": "giulia@example.com", "password": PASSWORD, "language": "it"},
    )
    assert created.status_code == 201
    login = client.post(
        "/api/v1/auth/login", json={"email": "giulia@example.com", "password": PASSWORD}
    ).json()
    headers = {"Authorization": f"Bearer {login['access_token']}"}
    assert client.get("/api/v1/auth/me", headers=headers).json()["language"] == "it"


@pytest.mark.parametrize("language", ["en", "it", "es", "fr", "de", "zh", "ja", "ar", "hi"])
def test_every_shipped_language_can_be_chosen(client, auth_headers, language):
    headers = auth_headers("polyglot@example.com")
    updated = client.patch("/api/v1/auth/me", json={"language": language}, headers=headers)
    assert updated.status_code == 200
    assert updated.json()["language"] == language


@pytest.mark.parametrize("bad", ["xx", "EN", "it-IT", ""])
def test_unknown_languages_are_refused(client, auth_headers, bad):
    headers = auth_headers("strict@example.com")
    assert (
        client.patch("/api/v1/auth/me", json={"language": bad}, headers=headers).status_code == 422
    )
    assert client.get("/api/v1/auth/me", headers=headers).json()["language"] == "en"


def test_display_name_is_tidied_and_can_be_cleared(client, auth_headers):
    headers = auth_headers("named@example.com")
    named = client.patch(
        "/api/v1/auth/me", json={"display_name": "  Andrea   Rossi "}, headers=headers
    ).json()
    assert named["display_name"] == "Andrea Rossi"
    # Other preferences are left as they were.
    assert named["language"] == "en"
    cleared = client.patch("/api/v1/auth/me", json={"display_name": "   "}, headers=headers).json()
    assert cleared["display_name"] is None
    too_long = client.patch("/api/v1/auth/me", json={"display_name": "x" * 81}, headers=headers)
    assert too_long.status_code == 422
