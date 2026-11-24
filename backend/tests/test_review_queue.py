"""Choosing what to review: the due list, a review of chosen questions, and picking the next
question while reviewing."""

from datetime import timedelta

import pytest
from test_review import (
    answer,
    card,
    concept,
    course,  # noqa: F401
    item,
    learn,
    make_due,
    start,
)

API = "/api/v1"


@pytest.fixture
def due_items(client, course, db_session):  # noqa: F811
    """Three encoded questions in two concepts, all due; made due in the opposite order to their
    place in the course, to show the list follows the course, not the due dates."""
    headers, course_id, _, topic_id = course
    first = concept(client, headers, topic_id, "Mutuo")
    second = concept(client, headers, topic_id, "Deposito")
    ids = [
        item(client, headers, first["id"], "Mutuo A")["id"],
        item(client, headers, first["id"], "Mutuo B")["id"],
        item(client, headers, second["id"], "Deposito C")["id"],
    ]
    learn(client, headers, course_id)
    for index, item_id in enumerate(ids):  # the last in the course is the most overdue
        make_due(db_session, item_id, ago=timedelta(days=1 + index))
    return headers, course_id, ids


def queue(client, headers, course_id):
    return client.get(f"{API}/courses/{course_id}/review-queue", headers=headers)


def test_the_queue_lists_what_is_due_in_course_order(client, due_items):
    headers, course_id, ids = due_items
    body = queue(client, headers, course_id).json()
    assert body["total"] == 3
    assert [row["learning_item_id"] for row in body["items"]] == ids  # course order
    assert [row["overdue_days"] for row in body["items"]] == [1, 2, 3]
    first = body["items"][0]
    assert (first["chapter_title"], first["topic_title"], first["concept_title"]) == (
        "Contratti",
        "Prestiti",
        "Mutuo",
    )
    assert first["question"].startswith("Che cos'e") or first["question"].startswith("Spiega")


def test_the_queue_leaves_out_what_is_not_due_and_other_people_s_questions(
    client, due_items, auth_headers, db_session
):
    headers, course_id, ids = due_items
    make_due(db_session, ids[0], ago=-timedelta(days=5))  # pushed into the future
    assert queue(client, headers, course_id).json()["total"] == 2
    stranger = auth_headers("nosy3@example.com")
    assert queue(client, stranger, course_id).status_code == 404


def test_a_review_of_chosen_questions_asks_only_those_in_course_order(client, due_items):
    headers, course_id, ids = due_items
    session = start(
        client,
        headers,
        course_id,
        "SCHEDULED_REVIEW",
        selection_mode="SELECTED",
        learning_item_ids=[ids[2], ids[0]],  # ticked in the opposite order
    ).json()
    assert (session["total"], session["affects_schedule"]) == (2, True)
    assert card(client, headers, session["id"])["card"]["learning_item_id"] == ids[0]


def test_a_chosen_review_ignores_what_is_not_due(client, due_items, db_session):
    headers, course_id, ids = due_items
    make_due(db_session, ids[1], ago=-timedelta(days=5))
    session = start(
        client,
        headers,
        course_id,
        "SCHEDULED_REVIEW",
        selection_mode="SELECTED",
        learning_item_ids=[ids[0], ids[1]],
    ).json()
    assert session["total"] == 1


def test_the_session_queue_lists_what_is_left_and_marks_the_current(client, due_items):
    headers, course_id, _ids = due_items
    session = start(client, headers, course_id, "SCHEDULED_REVIEW").json()
    body = client.get(f"{API}/review-sessions/{session['id']}/queue", headers=headers).json()
    assert body["total"] == 3
    assert sum(row["current"] for row in body["items"]) == 1
    assert body["items"][0]["current"] is True


def test_picking_makes_a_later_question_the_next_one_and_drops_nothing(client, due_items):
    headers, course_id, _ids = due_items
    session = start(client, headers, course_id, "SCHEDULED_REVIEW").json()
    order = [
        row["learning_item_id"]
        for row in client.get(
            f"{API}/review-sessions/{session['id']}/queue", headers=headers
        ).json()["items"]
    ]
    wanted = order[2]
    picked = client.post(
        f"{API}/review-sessions/{session['id']}/pick",
        json={"learning_item_id": wanted},
        headers=headers,
    )
    assert picked.status_code == 200
    assert picked.json()["card"]["learning_item_id"] == wanted
    after = client.get(f"{API}/review-sessions/{session['id']}/queue", headers=headers).json()
    assert [row["learning_item_id"] for row in after["items"]] == [wanted, order[0], order[1]]


def test_picking_between_answers_chooses_the_following_question(client, due_items):
    headers, course_id, _ids = due_items
    session = start(client, headers, course_id, "SCHEDULED_REVIEW").json()
    answer(client, headers, session["id"], "Consegna di denaro con obbligo di restituzione.")
    remaining = client.get(f"{API}/review-sessions/{session['id']}/queue", headers=headers).json()
    assert remaining["total"] == 2
    last = remaining["items"][1]["learning_item_id"]
    picked = client.post(
        f"{API}/review-sessions/{session['id']}/pick",
        json={"learning_item_id": last},
        headers=headers,
    ).json()
    assert picked["card"]["learning_item_id"] == last


def test_a_question_already_answered_or_unknown_cannot_be_picked(client, due_items):
    headers, course_id, _ids = due_items
    session = start(client, headers, course_id, "SCHEDULED_REVIEW").json()
    first = card(client, headers, session["id"])["card"]["learning_item_id"]
    answer(client, headers, session["id"], "Consegna di denaro con obbligo di restituzione.")
    gone = client.post(
        f"{API}/review-sessions/{session['id']}/pick",
        json={"learning_item_id": first},
        headers=headers,
    )
    assert gone.status_code == 404


def test_only_the_owner_can_use_a_session_queue(client, due_items, auth_headers):
    headers, course_id, ids = due_items
    session = start(client, headers, course_id, "SCHEDULED_REVIEW").json()
    stranger = auth_headers("nosy4@example.com")
    assert (
        client.get(f"{API}/review-sessions/{session['id']}/queue", headers=stranger).status_code
        == 404
    )
    assert (
        client.post(
            f"{API}/review-sessions/{session['id']}/pick",
            json={"learning_item_id": ids[0]},
            headers=stranger,
        ).status_code
        == 404
    )
