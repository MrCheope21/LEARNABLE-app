"""Every error response uses the envelope documented in docs/API.md."""

from fastapi.testclient import TestClient

from app.db.session import get_db
from app.main import app


def _assert_envelope(response, status_code: int, error_type: str) -> dict:
    assert response.status_code == status_code
    body = response.json()
    assert set(body) == {"error_type", "message", "details"}
    assert body["error_type"] == error_type
    assert isinstance(body["message"], str)
    assert body["message"]
    return body


def test_unknown_route(client):
    _assert_envelope(client.get("/api/v1/does-not-exist"), 404, "not_found")


def test_method_not_allowed(client):
    _assert_envelope(client.put("/health"), 405, "method_not_allowed")


def test_validation_error_does_not_echo_input(client):
    secret_password = "tiny"
    response = client.post(
        "/api/v1/auth/register", json={"email": "not-an-email", "password": secret_password}
    )
    body = _assert_envelope(response, 422, "validation_error")
    locations = {tuple(err["loc"]) for err in body["details"]["errors"]}
    assert ("body", "email") in locations
    assert ("body", "password") in locations
    # The rejected password must not be reflected back (it would end up in client logs).
    assert secret_password not in response.text


def test_unhandled_exception_is_generic_500():
    def _broken_db():
        raise RuntimeError("database credentials: hunter2")
        yield  # pragma: no cover

    app.dependency_overrides[get_db] = _broken_db
    try:
        with TestClient(app, raise_server_exceptions=False) as client:
            response = client.post(
                "/api/v1/auth/login", json={"email": "a@example.com", "password": "whatever"}
            )
    finally:
        app.dependency_overrides.clear()

    _assert_envelope(response, 500, "internal_error")
    assert "hunter2" not in response.text
