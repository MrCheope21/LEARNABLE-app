"""Deleting whole groups and single questions together (curriculum/bulk-delete)."""

import pytest


@pytest.fixture
def tree(client, auth_headers):
    headers = auth_headers("owner@example.com")
    course = client.post("/api/v1/courses", json={"title": "Course"}, headers=headers).json()

    def post(path, **body):
        return client.post(f"/api/v1{path}", json=body, headers=headers).json()

    chapters = [post(f"/courses/{course['id']}/chapters", title=t) for t in ("A", "B")]
    topics = {
        "A1": post(f"/chapters/{chapters[0]['id']}/topics", title="A1"),
        "A2": post(f"/chapters/{chapters[0]['id']}/topics", title="A2"),
        "B1": post(f"/chapters/{chapters[1]['id']}/topics", title="B1"),
    }
    concepts = {
        name: post(f"/topics/{topic['id']}/concepts", title=name)
        for name, topic in zip(("A1c", "A2c", "B1c"), topics.values(), strict=True)
    }
    items = {
        name: post(f"/concepts/{concept['id']}/learning-items", title=name)
        for name, concept in zip(("A1i", "A2i", "B1i"), concepts.values(), strict=True)
    }
    return headers, course["id"], chapters, topics, concepts, items


def delete(client, headers, course_id, **body):
    return client.post(
        f"/api/v1/courses/{course_id}/curriculum/bulk-delete", json=body, headers=headers
    )


def outline_titles(client, headers, course_id):
    outline = client.get(f"/api/v1/courses/{course_id}/outline", headers=headers).json()
    return {
        c["title"]: {t["title"]: [k["title"] for k in t["concepts"]] for t in c["topics"]}
        for c in outline
    }


def test_a_chapter_goes_with_everything_inside_it(client, tree):
    headers, course_id, chapters, _, _, items = tree
    response = delete(client, headers, course_id, chapter_ids=[chapters[0]["id"]])
    assert response.status_code == 200
    assert response.json() == {"chapters": 1, "topics": 0, "concepts": 0, "items": 0}
    assert outline_titles(client, headers, course_id) == {"B": {"B1": ["B1c"]}}
    assert (
        client.get(f"/api/v1/learning-items/{items['A1i']['id']}", headers=headers).status_code
        == 404
    )
    assert (
        client.get(f"/api/v1/learning-items/{items['B1i']['id']}", headers=headers).status_code
        == 200
    )


def test_every_stage_can_be_selected_at_once(client, tree):
    headers, course_id, chapters, topics, concepts, items = tree
    response = delete(
        client,
        headers,
        course_id,
        chapter_ids=[chapters[1]["id"]],
        topic_ids=[topics["A1"]["id"], topics["B1"]["id"]],
        concept_ids=[concepts["A1c"]["id"], concepts["A2c"]["id"]],
        item_ids=[items["A2i"]["id"], items["B1i"]["id"]],
    )
    assert response.status_code == 200
    assert response.json() == {"chapters": 1, "topics": 2, "concepts": 2, "items": 2}
    assert outline_titles(client, headers, course_id) == {"A": {"A2": []}}


def test_a_single_group_leaves_its_siblings(client, tree):
    headers, course_id, _, topics, _, _ = tree
    delete(client, headers, course_id, topic_ids=[topics["A1"]["id"]])
    assert outline_titles(client, headers, course_id) == {
        "A": {"A2": ["A2c"]},
        "B": {"B1": ["B1c"]},
    }


def test_nothing_changes_if_any_id_is_not_in_this_course(client, tree, auth_headers):
    headers, course_id, chapters, _, _, _ = tree
    other = auth_headers("other@example.com")
    foreign = client.post("/api/v1/courses", json={"title": "Other"}, headers=other).json()
    stranger = client.post(
        f"/api/v1/courses/{foreign['id']}/chapters", json={"title": "X"}, headers=other
    ).json()
    response = delete(client, headers, course_id, chapter_ids=[chapters[0]["id"], stranger["id"]])
    assert response.status_code == 404
    assert set(outline_titles(client, headers, course_id)) == {"A", "B"}


def test_an_empty_selection_deletes_nothing(client, tree):
    headers, course_id, *_ = tree
    assert delete(client, headers, course_id).json() == {
        "chapters": 0,
        "topics": 0,
        "concepts": 0,
        "items": 0,
    }
    assert set(outline_titles(client, headers, course_id)) == {"A", "B"}
