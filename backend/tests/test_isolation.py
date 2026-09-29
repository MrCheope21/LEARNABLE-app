"""Course isolation across every Course-scoped endpoint (docs/PROJECT_SPEC.md §10, §81).

An intruder with a valid account tries each endpoint against another user's resources. Every
attempt must 404 (never 403 — that would confirm the id exists), and the owner's data must be
unchanged afterwards. New Course-scoped endpoints must be added to ENDPOINTS.
"""

import pytest

_TITLE = {"json": {"title": "hijacked"}}
_PLANT = {"json": {"title": "planted"}}
_FILE = {"files": {"file": ("planted.txt", b"Planted by an intruder.", "text/plain")}}
_CURRICULUM = {"json": {"chapters": [{"title": "planted", "topics": [{"title": "planted"}]}]}}

# (method, path template, request kwargs)
ENDPOINTS = [
    ("GET", "/api/v1/courses/{course}", {}),
    ("PATCH", "/api/v1/courses/{course}", _TITLE),
    ("DELETE", "/api/v1/courses/{course}", {}),
    ("POST", "/api/v1/courses/{course}/pause", {}),
    ("POST", "/api/v1/courses/{course}/resume", {}),
    ("POST", "/api/v1/courses/{course}/chapters", _PLANT),
    ("PATCH", "/api/v1/chapters/{chapter}", _TITLE),
    ("DELETE", "/api/v1/chapters/{chapter}", {}),
    ("POST", "/api/v1/chapters/{chapter}/pause", {}),
    ("POST", "/api/v1/chapters/{chapter}/resume", {}),
    ("POST", "/api/v1/chapters/{chapter}/topics", _PLANT),
    ("PATCH", "/api/v1/topics/{topic}", _TITLE),
    ("DELETE", "/api/v1/topics/{topic}", {}),
    ("POST", "/api/v1/topics/{topic}/pause", {}),
    ("POST", "/api/v1/topics/{topic}/resume", {}),
    ("POST", "/api/v1/topics/{topic}/concepts", _PLANT),
    ("PATCH", "/api/v1/concepts/{concept}", _TITLE),
    ("DELETE", "/api/v1/concepts/{concept}", {}),
    ("POST", "/api/v1/concepts/{concept}/mark-studied", {}),
    ("POST", "/api/v1/concepts/{concept}/activate", {}),
    ("POST", "/api/v1/concepts/{concept}/pause", {}),
    ("POST", "/api/v1/concepts/{concept}/resume", {}),
    ("POST", "/api/v1/concepts/{concept}/deactivate", {}),
    ("POST", "/api/v1/concepts/{concept}/complete", {}),
    ("POST", "/api/v1/courses/{course}/documents", _FILE),
    ("POST", "/api/v1/courses/{course}/documents", {**_FILE, "data": {"purpose": "QUESTION_BANK"}}),
    ("GET", "/api/v1/courses/{course}/documents", {}),
    ("GET", "/api/v1/documents/{document}", {}),
    ("DELETE", "/api/v1/documents/{document}", {}),
    ("GET", "/api/v1/documents/{document}/chunks", {}),
    ("GET", "/api/v1/documents/{document}/chunks/{chunk}", {}),
    ("POST", "/api/v1/courses/{course}/curriculum-proposals", {"json": {}}),
    (
        "POST",
        "/api/v1/courses/{course}/curriculum-proposals",
        {"json": {"document_ids": ["{document}"]}},
    ),
    ("GET", "/api/v1/courses/{course}/curriculum-proposals", {}),
    ("GET", "/api/v1/curriculum-proposals/{proposal}", {}),
    ("DELETE", "/api/v1/curriculum-proposals/{proposal}", {}),
    ("POST", "/api/v1/curriculum-proposals/{proposal}/apply", _CURRICULUM),
    ("GET", "/api/v1/courses/{course}/outline", {}),
    ("PATCH", "/api/v1/documents/{document}", {"json": {"chapter_id": None}}),
    ("GET", "/api/v1/courses/{course}/documents?chapter_id={chapter}", {}),
    (
        "POST",
        "/api/v1/courses/{course}/curriculum-proposals",
        {"json": {"chapter_id": "{chapter}"}},
    ),
    ("GET", "/api/v1/concepts/{concept}", {}),
    ("GET", "/api/v1/concepts/{concept}/sources", {}),
    ("GET", "/api/v1/concepts/{concept}/learning-items", {}),
    ("POST", "/api/v1/concepts/{concept}/learning-items", {"json": {"title": "planted"}}),
    ("POST", "/api/v1/concepts/{concept}/learning-items/generate", {}),
    ("GET", "/api/v1/learning-items/{item}", {}),
    ("PATCH", "/api/v1/learning-items/{item}", _TITLE),
    ("DELETE", "/api/v1/learning-items/{item}", {}),
    ("POST", "/api/v1/learning-items/{item}/train", {}),
    ("POST", "/api/v1/learning-items/{item}/untrain", {}),
    ("POST", "/api/v1/learning-items/{item}/pause", {}),
    ("POST", "/api/v1/learning-items/{item}/resume", {}),
    (
        "POST",
        "/api/v1/learning-items/{item}/questions",
        {"json": {"question_type": "RECALL", "text": "planted"}},
    ),
    ("POST", "/api/v1/learning-items/{item}/questions/generate", {"json": {"count": 1}}),
    ("GET", "/api/v1/learning-items/{item}/sources", {}),
    ("GET", "/api/v1/learning-items/{item}/reviews", {}),
    ("GET", "/api/v1/courses/{course}/progress", {}),
    ("GET", "/api/v1/courses/{course}/review-load", {}),
    ("POST", "/api/v1/courses/{course}/review-sessions", {"json": {"intent": "LEARN"}}),
    ("GET", "/api/v1/review-sessions/{session}", {}),
    ("GET", "/api/v1/review-sessions/{session}/next", {}),
    (
        "POST",
        "/api/v1/review-sessions/{session}/answers",
        {"json": {"question_formulation_id": "{question}", "text": "planted"}},
    ),
    ("POST", "/api/v1/review-sessions/{session}/skip", {}),
    ("POST", "/api/v1/review-sessions/{session}/end", {}),
    ("GET", "/api/v1/answers/{answer}", {}),
    ("POST", "/api/v1/answers/{answer}/evaluate", {}),
    ("POST", "/api/v1/answers/{answer}/override", {"json": {"outcome": "EASY"}}),
    ("GET", "/api/v1/concepts/{concept}/consolidation", {}),
    ("POST", "/api/v1/concepts/{concept}/consolidation", {}),
    ("POST", "/api/v1/review-sessions/{session}/hint", {}),
    ("GET", "/api/v1/documents/{document}/file", {}),
    ("GET", "/api/v1/courses/{course}/summary", {}),
    ("GET", "/api/v1/courses/{course}/learning-items", {}),
    (
        "POST",
        "/api/v1/courses/{course}/learning-items/bulk",
        {"json": {"item_ids": ["{item}"], "action": "delete"}},
    ),
    ("PATCH", "/api/v1/questions/{question}", {"json": {"text": "hijacked"}}),
    ("DELETE", "/api/v1/questions/{question}", {}),
]


@pytest.fixture
def owner_and_intruder(client, auth_headers):
    owner = auth_headers("owner@example.com")
    intruder = auth_headers("intruder@example.com")

    course = client.post("/api/v1/courses", json={"title": "Private"}, headers=owner).json()
    chapter = client.post(
        f"/api/v1/courses/{course['id']}/chapters", json={"title": "Ch"}, headers=owner
    ).json()
    topic = client.post(
        f"/api/v1/chapters/{chapter['id']}/topics", json={"title": "T"}, headers=owner
    ).json()
    concept = client.post(
        f"/api/v1/topics/{topic['id']}/concepts", json={"title": "C"}, headers=owner
    ).json()
    # Active, so pause is a valid transition for the owner — an intruder's pause must still 404
    # rather than succeeding or leaking a 409.
    client.post(f"/api/v1/concepts/{concept['id']}/activate", headers=owner)
    document = client.post(
        f"/api/v1/courses/{course['id']}/documents",
        files={"file": ("notes.txt", b"Private study notes.", "text/plain")},
        data={"chapter_id": chapter["id"]},
        headers=owner,
    ).json()
    [chunk] = client.get(f"/api/v1/documents/{document['id']}/chunks", headers=owner).json()
    item = client.post(
        f"/api/v1/concepts/{concept['id']}/learning-items",
        json={
            "title": "Private item",
            "questions": [{"question_type": "RECALL", "text": "Private question?"}],
        },
        headers=owner,
    ).json()
    # A LEARN session with an answer that has no outcome yet (the item has no reference to grade
    # against): an intruder's evaluate/override/skip would visibly change it.
    session = client.post(
        f"/api/v1/courses/{course['id']}/review-sessions", json={"intent": "LEARN"}, headers=owner
    ).json()
    pending = client.post(
        f"/api/v1/review-sessions/{session['id']}/answers",
        json={"question_formulation_id": item["questions"][0]["id"], "text": "My answer"},
        headers=owner,
    ).json()
    assert pending["needs_self_grade"] is True
    proposal = client.post(
        f"/api/v1/courses/{course['id']}/curriculum-proposals",
        json={"chapter_id": chapter["id"]},
        headers=owner,
    ).json()

    ids = {
        "course": course["id"],
        "chapter": chapter["id"],
        "topic": topic["id"],
        "concept": concept["id"],
        "document": document["id"],
        "chunk": chunk["id"],
        "proposal": proposal["id"],
        "item": item["id"],
        "question": item["questions"][0]["id"],
        "session": session["id"],
        "answer": pending["answer_id"],
    }
    return owner, intruder, ids


@pytest.mark.parametrize(
    ("method", "path", "kwargs"), ENDPOINTS, ids=[f"{m} {p}" for m, p, _ in ENDPOINTS]
)
def test_intruder_gets_404_and_changes_nothing(
    client, owner_and_intruder, ai_provider, method, path, kwargs
):
    owner, intruder, ids = owner_and_intruder
    url = path.format(**ids)
    if "json" in kwargs:
        kwargs = {"json": _fill(kwargs["json"], ids)}
    ai_calls_before = _ai_calls(ai_provider)

    response = client.request(method, url, headers=intruder, **kwargs)
    assert response.status_code == 404, response.text
    assert response.json()["error_type"] == "not_found"

    course = client.get(f"/api/v1/courses/{ids['course']}", headers=owner)
    assert course.status_code == 200
    assert course.json()["title"] == "Private"
    assert course.json()["paused"] is False
    concept = client.patch(f"/api/v1/concepts/{ids['concept']}", json={}, headers=owner)
    assert concept.status_code == 200
    assert concept.json()["title"] == "C"
    assert concept.json()["study_state"] == "ACTIVE"
    # Also catches an intruder pausing the owner's Topic or Chapter.
    assert concept.json()["is_reviewable"] is True
    documents = client.get(f"/api/v1/courses/{ids['course']}/documents", headers=owner).json()
    # Nothing deleted, nothing planted, nothing moved.
    assert [(d["id"], d["chapter_id"]) for d in documents] == [(ids["document"], ids["chapter"])]
    proposals = client.get(
        f"/api/v1/courses/{ids['course']}/curriculum-proposals", headers=owner
    ).json()
    assert [(p["id"], p["status"]) for p in proposals] == [(ids["proposal"], "READY")]
    outline = client.get(f"/api/v1/courses/{ids['course']}/outline", headers=owner).json()
    assert [c["title"] for c in outline] == ["Ch"]
    items = client.get(f"/api/v1/concepts/{ids['concept']}/learning-items", headers=owner).json()
    assert [
        (i["id"], i["title"], i["in_training"], i["paused"], len(i["questions"])) for i in items
    ] == [(ids["item"], "Private item", True, False, 1)]
    owned_session = client.get(f"/api/v1/review-sessions/{ids['session']}", headers=owner).json()
    assert (owned_session["position"], owned_session["ended_at"]) == (0, None)
    owned_answer = client.get(f"/api/v1/answers/{ids['answer']}", headers=owner).json()
    assert (owned_answer["final_outcome"], len(owned_answer["evaluations"])) == (None, 1)
    assert items[0]["review_state"]["state"] == "NEW"
    # The owner's material was never sent to the AI on the intruder's behalf.
    assert _ai_calls(ai_provider) == ai_calls_before


def _ai_calls(provider):
    return (
        len(provider.curriculum_requests)
        + len(provider.chapter_requests)
        + len(provider.learning_item_requests)
        + len(provider.evaluation_requests)
    )


def _fill(body, ids):
    """Replaces "{placeholder}" strings in a JSON body with the owner's ids."""
    if isinstance(body, dict):
        return {k: _fill(v, ids) for k, v in body.items()}
    if isinstance(body, list):
        return [_fill(v, ids) for v in body]
    if isinstance(body, str) and body.startswith("{") and body.endswith("}"):
        return ids[body[1:-1]]
    return body


def test_intruder_list_excludes_other_users_courses(client, owner_and_intruder):
    _owner, intruder, ids = owner_and_intruder
    listed = client.get("/api/v1/courses", headers=intruder).json()
    assert all(c["id"] != ids["course"] for c in listed)


def test_nonexistent_and_foreign_ids_are_indistinguishable(client, owner_and_intruder):
    _owner, intruder, ids = owner_and_intruder
    foreign = client.get(f"/api/v1/courses/{ids['course']}", headers=intruder)
    missing = client.get("/api/v1/courses/00000000-0000-0000-0000-000000000000", headers=intruder)
    assert foreign.status_code == missing.status_code == 404
    assert foreign.json() == missing.json()


def test_duplicate_detection_never_reveals_another_users_files(client, owner_and_intruder):
    # The intruder uploads the exact file the owner has: it must be accepted as new in their own
    # Course, not flagged as a duplicate (which would leak what the owner's repository contains).
    _owner, intruder, _ids = owner_and_intruder
    course = client.post("/api/v1/courses", json={"title": "Mine"}, headers=intruder).json()
    response = client.post(
        f"/api/v1/courses/{course['id']}/documents",
        files={"file": ("notes.txt", b"Private study notes.", "text/plain")},
        headers=intruder,
    )
    assert response.status_code == 202
