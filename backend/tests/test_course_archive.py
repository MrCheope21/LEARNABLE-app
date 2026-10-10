"""Archiving a course puts it away without deleting anything; restoring brings it back."""

from test_review import concept, course, item  # noqa: F401

API = "/api/v1"


def cards(client, headers):
    return {c["id"]: c for c in client.get(f"{API}/dashboard", headers=headers).json()["courses"]}


def test_archiving_hides_and_pauses_a_course_and_restoring_resumes_it(client, course):  # noqa: F811
    headers, course_id, _, topic_id = course
    created = item(client, headers, concept(client, headers, topic_id)["id"])

    archived = client.post(f"{API}/courses/{course_id}/archive", headers=headers).json()
    assert archived["paused"] is True
    assert archived["archived_at"] is not None
    card = cards(client, headers)[course_id]
    assert (card["archived_at"] is not None, card["paused"], card["due_now"]) == (True, True, 0)
    # Everything is still there.
    assert client.get(f"{API}/learning-items/{created['id']}", headers=headers).status_code == 200

    restored = client.post(f"{API}/courses/{course_id}/unarchive", headers=headers).json()
    assert (restored["paused"], restored["archived_at"]) == (False, None)
    assert cards(client, headers)[course_id]["archived_at"] is None


def test_an_archived_course_is_not_the_next_step(client, course):  # noqa: F811
    headers, course_id, _, topic_id = course
    item(client, headers, concept(client, headers, topic_id)["id"])
    step = client.get(f"{API}/dashboard", headers=headers).json()["next_step"]
    assert step["course_id"] == course_id
    client.post(f"{API}/courses/{course_id}/archive", headers=headers)
    step = client.get(f"{API}/dashboard", headers=headers).json()["next_step"]
    assert step["course_id"] != course_id
    assert step["kind"] in ("all_caught_up", "create_course")


def test_only_the_owner_can_archive(client, course, auth_headers):  # noqa: F811
    _, course_id, _, _ = course
    other = auth_headers("other@example.com")
    assert client.post(f"{API}/courses/{course_id}/archive", headers=other).status_code == 404


def test_an_archived_course_can_be_deleted(client, course):  # noqa: F811
    headers, course_id, _, _ = course
    client.post(f"{API}/courses/{course_id}/archive", headers=headers)
    assert client.delete(f"{API}/courses/{course_id}", headers=headers).status_code == 204
    assert course_id not in cards(client, headers)
