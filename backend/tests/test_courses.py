import re

import pytest

TIMESTAMP_FORMAT = re.compile(r"^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}\.\d{3}Z$")


def _create_hierarchy(client, headers) -> dict[str, str]:
    course_id = client.post(
        "/api/v1/courses", json={"title": "Macroeconomia"}, headers=headers
    ).json()["id"]
    chapter_id = client.post(
        f"/api/v1/courses/{course_id}/chapters", json={"title": "Ch"}, headers=headers
    ).json()["id"]
    topic_id = client.post(
        f"/api/v1/chapters/{chapter_id}/topics", json={"title": "T"}, headers=headers
    ).json()["id"]
    concept_id = client.post(
        f"/api/v1/topics/{topic_id}/concepts", json={"title": "Opportunity cost"}, headers=headers
    ).json()["id"]
    return {"course": course_id, "chapter": chapter_id, "topic": topic_id, "concept": concept_id}


def test_create_list_and_get_course(client, auth_headers):
    headers = auth_headers("owner@example.com")

    created = client.post(
        "/api/v1/courses",
        json={"title": "Dottore Commercialista", "language": "it"},
        headers=headers,
    )
    assert created.status_code == 201
    course_id = created.json()["id"]

    titles = [c["title"] for c in client.get("/api/v1/courses", headers=headers).json()]
    assert titles == ["Dottore Commercialista"]

    fetched = client.get(f"/api/v1/courses/{course_id}", headers=headers)
    assert fetched.status_code == 200
    assert fetched.json()["language"] == "it"


def test_timestamps_follow_api_contract(client, auth_headers):
    headers = auth_headers("timestamps@example.com")
    body = client.post("/api/v1/courses", json={"title": "Timestamps"}, headers=headers).json()
    # UTC, millisecond precision, Z suffix (docs/API.md) — the format the iOS decoder expects.
    assert TIMESTAMP_FORMAT.match(body["created_at"]), body["created_at"]
    assert TIMESTAMP_FORMAT.match(body["updated_at"]), body["updated_at"]


def test_unauthenticated_requests_rejected(client):
    assert client.get("/api/v1/courses").status_code == 401
    assert client.post("/api/v1/courses", json={"title": "x"}).status_code == 401


@pytest.mark.parametrize(
    "body",
    [
        {},
        {"title": ""},
        {"title": "   "},
        {"title": "x" * 201},
        {"title": "ok", "description": "x" * 2001},
        {"title": "ok", "language": "italian"},
        {"title": "ok", "user_id": "00000000-0000-0000-0000-000000000000"},
    ],
    ids=[
        "missing_title",
        "empty_title",
        "blank_title",
        "title_too_long",
        "description_too_long",
        "bad_language",
        "unknown_field",
    ],
)
def test_invalid_course_create_rejected(client, auth_headers, body):
    headers = auth_headers("validation@example.com")
    response = client.post("/api/v1/courses", json=body, headers=headers)
    assert response.status_code == 422
    assert response.json()["error_type"] == "validation_error"


def test_whitespace_is_trimmed(client, auth_headers):
    headers = auth_headers("trim@example.com")
    body = client.post("/api/v1/courses", json={"title": "  Banking  "}, headers=headers).json()
    assert body["title"] == "Banking"


def test_patch_semantics(client, auth_headers):
    headers = auth_headers("patch@example.com")
    ids = _create_hierarchy(client, headers)
    course_url = f"/api/v1/courses/{ids['course']}"

    # Omitted fields are untouched.
    patched = client.patch(course_url, json={"description": "New"}, headers=headers)
    assert patched.status_code == 200
    assert patched.json()["title"] == "Macroeconomia"
    assert patched.json()["description"] == "New"

    # Explicit null is a validation error, not a 500 from a NOT NULL violation.
    for url, field in [
        (course_url, "title"),
        (f"/api/v1/chapters/{ids['chapter']}", "order"),
        (f"/api/v1/topics/{ids['topic']}", "title"),
        (f"/api/v1/concepts/{ids['concept']}", "description"),
    ]:
        response = client.patch(url, json={field: None}, headers=headers)
        assert response.status_code == 422, f"{url} accepted null {field}"

    assert (
        client.patch(
            f"/api/v1/chapters/{ids['chapter']}", json={"order": -1}, headers=headers
        ).status_code
        == 422
    )


def test_full_hierarchy_creation(client, auth_headers):
    headers = auth_headers("hierarchy@example.com")
    course_id = client.post(
        "/api/v1/courses", json={"title": "Bilancio Bancario"}, headers=headers
    ).json()["id"]

    chapter = client.post(
        f"/api/v1/courses/{course_id}/chapters",
        json={"title": "Bilancio bancario"},
        headers=headers,
    ).json()
    assert chapter["course_id"] == course_id

    topic = client.post(
        f"/api/v1/chapters/{chapter['id']}/topics",
        json={"title": "Stato patrimoniale attivo"},
        headers=headers,
    ).json()
    assert topic["chapter_id"] == chapter["id"]
    assert topic["course_id"] == course_id

    concept = client.post(
        f"/api/v1/topics/{topic['id']}/concepts", json={"title": "Cassa"}, headers=headers
    ).json()
    assert concept["topic_id"] == topic["id"]
    assert concept["chapter_id"] == chapter["id"]
    assert concept["course_id"] == course_id
    assert concept["study_state"] == "NOT_STUDIED"


def test_course_deletion_cascades_to_hierarchy(client, auth_headers):
    headers = auth_headers("cascade@example.com")
    ids = _create_hierarchy(client, headers)

    assert client.delete(f"/api/v1/courses/{ids['course']}", headers=headers).status_code == 204

    assert client.get(f"/api/v1/courses/{ids['course']}", headers=headers).status_code == 404
    for kind in ("chapter", "topic", "concept"):
        response = client.patch(
            f"/api/v1/{kind}s/{ids[kind]}", json={"title": "x"}, headers=headers
        )
        assert response.status_code == 404, f"{kind} survived course deletion"


def test_chapter_deletion_cascades_but_leaves_course(client, auth_headers):
    headers = auth_headers("chapter-cascade@example.com")
    ids = _create_hierarchy(client, headers)

    assert client.delete(f"/api/v1/chapters/{ids['chapter']}", headers=headers).status_code == 204

    assert client.get(f"/api/v1/courses/{ids['course']}", headers=headers).status_code == 200
    for kind in ("topic", "concept"):
        response = client.patch(
            f"/api/v1/{kind}s/{ids[kind]}", json={"title": "x"}, headers=headers
        )
        assert response.status_code == 404, f"{kind} survived chapter deletion"
