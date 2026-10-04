"""Own review: the student picks questions or a concept to be tested on, outside the plan.

A PRACTICE session: it never moves the review schedule and earns no XP.
"""

from test_review import (  # noqa: F401
    FULL,
    answer,
    card,
    concept,
    course,
    item,
    learn,
    memory,
    start,
)


def test_chosen_questions_are_reviewed_without_touching_the_plan(client, course, db_session):  # noqa: F811
    headers, course_id, _, topic_id = course
    c = concept(client, headers, topic_id)
    chosen = item(client, headers, c["id"], "Scelta")
    other = item(client, headers, c["id"], "Altra")
    learn(client, headers, course_id)
    before = memory(db_session, chosen["id"])
    due_before, level_before = before.due_at, before.level
    other_reviews = memory(db_session, other["id"]).review_count

    session = start(
        client,
        headers,
        course_id,
        "PRACTICE",
        selection_mode="SELECTED",
        learning_item_ids=[chosen["id"]],
    ).json()
    assert session["total"] == 1
    assert session["affects_schedule"] is False
    assert card(client, headers, session["id"])["card"]["learning_item_id"] == chosen["id"]

    result = answer(client, headers, session["id"], FULL).json()
    assert result["final_outcome"] == "GOOD"
    assert result["schedule"] is None
    assert result["xp"] is None or result["xp"]["xp"] == 0
    after = memory(db_session, chosen["id"])
    assert (after.due_at, after.level) == (due_before, level_before)
    assert memory(db_session, other["id"]).review_count == other_reviews


def test_a_whole_concept_can_be_reviewed_on_your_own(client, course):  # noqa: F811
    headers, course_id, _, topic_id = course
    c = concept(client, headers, topic_id)
    for title in ("Uno", "Due"):
        item(client, headers, c["id"], title)
    learn(client, headers, course_id)
    session = start(client, headers, course_id, "PRACTICE", concept_ids=[c["id"]]).json()
    assert (session["total"], session["affects_schedule"]) == (2, False)
