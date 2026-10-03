"""Drag-and-drop order of chapters, topics, concepts and learning items (docs/API.md)."""

import pytest

API = "/api/v1"


@pytest.fixture
def owner(auth_headers):
    return auth_headers("orderly@example.com")


def post(client, headers, path, **body):
    response = client.post(f"{API}{path}", json=body, headers=headers)
    assert response.status_code == 201, response.text
    return response.json()["id"]


def put_order(client, headers, path, ids):
    return client.put(f"{API}{path}", json={"ids": ids}, headers=headers)


@pytest.fixture
def course(client, owner):
    """One course: chapters A, B, C; chapter A holds topics T1, T2; T1 holds concepts K1, K2;
    K1 holds items I1, I2, I3."""
    course = post(client, owner, "/courses", title="Course")
    chapters = [
        post(client, owner, f"/courses/{course}/chapters", title=t, order=i)
        for i, t in enumerate("ABC")
    ]
    topics = [
        post(client, owner, f"/chapters/{chapters[0]}/topics", title=t, order=i)
        for i, t in enumerate(["T1", "T2"])
    ]
    concepts = [
        post(client, owner, f"/topics/{topics[0]}/concepts", title=t, order=i)
        for i, t in enumerate(["K1", "K2"])
    ]
    items = [
        post(
            client,
            owner,
            f"/concepts/{concepts[0]}/learning-items",
            title=t,
            questions=[{"question_type": "RECALL", "text": f"{t}?"}],
        )
        for t in ["I1", "I2", "I3"]
    ]
    return {
        "id": course,
        "chapters": chapters,
        "topics": topics,
        "concepts": concepts,
        "items": items,
    }


def outline(client, headers, course_id):
    response = client.get(f"{API}/courses/{course_id}/outline", headers=headers)
    assert response.status_code == 200
    return response.json()


def item_titles(client, headers, concept_id):
    response = client.get(f"{API}/concepts/{concept_id}/learning-items", headers=headers)
    return [item["title"] for item in response.json()]


def test_reorder_every_level(client, owner, course):
    c = course
    assert (
        put_order(
            client, owner, f"/courses/{c['id']}/chapter-order", c["chapters"][::-1]
        ).status_code
        == 204
    )
    assert (
        put_order(
            client, owner, f"/chapters/{c['chapters'][0]}/topic-order", c["topics"][::-1]
        ).status_code
        == 204
    )
    assert (
        put_order(
            client, owner, f"/topics/{c['topics'][0]}/concept-order", c["concepts"][::-1]
        ).status_code
        == 204
    )
    new_items = [c["items"][2], c["items"][0], c["items"][1]]
    assert (
        put_order(
            client, owner, f"/concepts/{c['concepts'][0]}/learning-item-order", new_items
        ).status_code
        == 204
    )

    tree = outline(client, owner, c["id"])
    assert [ch["title"] for ch in tree] == ["C", "B", "A"]
    chapter_a = tree[2]
    assert [t["title"] for t in chapter_a["topics"]] == ["T2", "T1"]
    assert [k["title"] for k in chapter_a["topics"][1]["concepts"]] == ["K2", "K1"]
    assert item_titles(client, owner, c["concepts"][0]) == ["I3", "I1", "I2"]
    # The course-wide question manager follows the same order.
    listed = client.get(f"{API}/courses/{c['id']}/learning-items", headers=owner).json()
    assert [i["title"] for i in listed] == ["I3", "I1", "I2"]


@pytest.mark.parametrize(
    "ids",
    [
        pytest.param(lambda c: c["chapters"][:2], id="missing"),
        pytest.param(lambda c: [*c["chapters"], c["chapters"][0]], id="duplicate"),
        pytest.param(lambda c: [*c["chapters"][:2], c["topics"][0]], id="foreign"),
    ],
)
def test_stale_or_foreign_lists_are_rejected_and_change_nothing(client, owner, course, ids):
    response = put_order(client, owner, f"/courses/{course['id']}/chapter-order", ids(course))
    assert response.status_code == 422
    assert response.json()["details"]["reason"] == "order_mismatch"
    assert [ch["title"] for ch in outline(client, owner, course["id"])] == ["A", "B", "C"]


def test_an_item_of_another_concept_is_rejected(client, owner, course):
    other = post(
        client,
        owner,
        f"/concepts/{course['concepts'][1]}/learning-items",
        title="Elsewhere",
        questions=[{"question_type": "RECALL", "text": "Elsewhere?"}],
    )
    ids = [*course["items"][:2], other]
    response = put_order(
        client, owner, f"/concepts/{course['concepts'][0]}/learning-item-order", ids
    )
    assert response.status_code == 422
    assert item_titles(client, owner, course["concepts"][0]) == ["I1", "I2", "I3"]


def test_empty_list_is_a_validation_error(client, owner, course):
    assert put_order(client, owner, f"/courses/{course['id']}/chapter-order", []).status_code == 422
