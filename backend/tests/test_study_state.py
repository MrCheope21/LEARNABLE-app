"""Concept study-state lifecycle and section pausing (docs/PROJECT_SPEC.md §21, §22, §56, §60).

The expected matrix is written out by hand from the spec's intent, deliberately NOT derived from
service.CONCEPT_TRANSITIONS — a test generated from the code under test can't catch it being wrong.
"""

import pytest

NS, S, A, P, C = "NOT_STUDIED", "STUDIED", "ACTIVE", "PAUSED", "COMPLETED"
REJECTED = None

# action -> {starting state -> resulting state, or REJECTED (409)}
EXPECTED = {
    # Marking as studied is the step before activation; it never demotes a Concept in training.
    "mark-studied": {NS: S, S: S, A: REJECTED, P: REJECTED, C: REJECTED},
    # Activation; completed material can be brought back, a paused Concept must be resumed.
    "activate": {NS: A, S: A, A: A, P: REJECTED, C: A},
    "pause": {NS: REJECTED, S: REJECTED, A: P, P: REJECTED, C: REJECTED},
    "resume": {NS: REJECTED, S: REJECTED, A: REJECTED, P: A, C: REJECTED},
    # Leave active learning, keeping the fact it was studied.
    "deactivate": {NS: REJECTED, S: REJECTED, A: S, P: S, C: REJECTED},
    "complete": {NS: C, S: C, A: C, P: C, C: C},
}

# How to reach each starting state from a fresh (NOT_STUDIED) Concept.
SETUP = {NS: [], S: ["mark-studied"], A: ["activate"], P: ["activate", "pause"], C: ["complete"]}

CASES = [
    (action, start, result) for action, row in EXPECTED.items() for start, result in row.items()
]


def _hierarchy(client, headers) -> dict[str, str]:
    course = client.post("/api/v1/courses", json={"title": "Macroeconomia"}, headers=headers)
    course_id = course.json()["id"]
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


@pytest.mark.parametrize(
    ("action", "start", "result"), CASES, ids=[f"{a}-from-{s}" for a, s, _ in CASES]
)
def test_transition_matrix(client, auth_headers, action, start, result):
    headers = auth_headers("matrix@example.com")
    concept_url = f"/api/v1/concepts/{_hierarchy(client, headers)['concept']}"
    for step in SETUP[start]:
        assert client.post(f"{concept_url}/{step}", headers=headers).status_code == 200

    response = client.post(f"{concept_url}/{action}", headers=headers)

    if result is REJECTED:
        assert response.status_code == 409, response.text
        body = response.json()
        assert body["error_type"] == "invalid_state_transition"
        assert body["details"]["current_state"] == start
    else:
        assert response.status_code == 200, response.text
        assert response.json()["study_state"] == result


def test_only_active_concepts_are_reviewable(client, auth_headers):
    headers = auth_headers("reviewable@example.com")
    concept_url = f"/api/v1/concepts/{_hierarchy(client, headers)['concept']}"

    def reviewable_after(action: str) -> bool:
        return client.post(f"{concept_url}/{action}", headers=headers).json()["is_reviewable"]

    assert reviewable_after("mark-studied") is False
    assert reviewable_after("activate") is True
    assert reviewable_after("pause") is False
    assert reviewable_after("resume") is True
    assert reviewable_after("complete") is False


@pytest.mark.parametrize("section", ["course", "chapter", "topic"])
def test_pausing_a_section_excludes_its_concepts_without_changing_them(
    client, auth_headers, section
):
    headers = auth_headers(f"section-{section}@example.com")
    ids = _hierarchy(client, headers)
    concept_url = f"/api/v1/concepts/{ids['concept']}"
    section_url = f"/api/v1/{section}s/{ids[section]}"
    client.post(f"{concept_url}/activate", headers=headers)

    paused = client.post(f"{section_url}/pause", headers=headers)
    assert paused.status_code == 200
    assert paused.json()["paused"] is True

    concept = client.patch(concept_url, json={}, headers=headers).json()
    assert concept["study_state"] == A  # the Concept itself is untouched...
    assert concept["is_reviewable"] is False  # ...but it's out of review while the section is

    resumed = client.post(f"{section_url}/resume", headers=headers)
    assert resumed.json()["paused"] is False
    assert client.patch(concept_url, json={}, headers=headers).json()["is_reviewable"] is True


def test_resuming_a_section_restores_individually_paused_concepts_as_paused(client, auth_headers):
    # §56: "Unpause restores their previous state" — a section resume must not un-pause a
    # Concept the user had paused on its own.
    headers = auth_headers("restore@example.com")
    ids = _hierarchy(client, headers)
    concept_url = f"/api/v1/concepts/{ids['concept']}"
    client.post(f"{concept_url}/activate", headers=headers)
    client.post(f"{concept_url}/pause", headers=headers)

    client.post(f"/api/v1/topics/{ids['topic']}/pause", headers=headers)
    client.post(f"/api/v1/topics/{ids['topic']}/resume", headers=headers)

    concept = client.patch(concept_url, json={}, headers=headers).json()
    assert concept["study_state"] == P
    assert concept["is_reviewable"] is False


def test_section_pause_is_idempotent(client, auth_headers):
    headers = auth_headers("idempotent@example.com")
    topic_url = f"/api/v1/topics/{_hierarchy(client, headers)['topic']}"
    for _ in range(2):
        assert client.post(f"{topic_url}/pause", headers=headers).json()["paused"] is True
    for _ in range(2):
        assert client.post(f"{topic_url}/resume", headers=headers).json()["paused"] is False
