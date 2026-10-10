"""An answer green on at least 3 of the 4 scores, but not a GOOD, is repeated after reviewing the
reference answer, and then counts as a correct first answer: the schedule goes forward."""

from datetime import timedelta

import pytest
from test_review import (
    FULL,
    answer,
    card,
    concept,
    course,  # noqa: F401
    item,
    learn,
    make_due,
    memory,
    start,
    use_provider,
)

from app.ai.mock import MockAIProvider
from app.ai.schemas import EvaluationOutput
from app.models.enums import EvaluationClassification as C

API = "/api/v1"


def scores(
    correctness, completeness, understanding, precision, classification=C.PARTIALLY_CORRECT, **extra
):
    return EvaluationOutput(
        classification=classification,
        correctness=correctness,
        completeness=completeness,
        conceptual_understanding=understanding,
        precision=precision,
        confidence=0.9,
        context_sufficient=True,
        **extra,
    )


@pytest.fixture
def due_item(client, course, db_session):  # noqa: F811
    """An encoded item (level 1) that is due for review."""
    headers, course_id, _, topic_id = course
    created = item(client, headers, concept(client, headers, topic_id)["id"])
    learn(client, headers, course_id)
    make_due(db_session, created["id"], ago=timedelta(days=2))
    return headers, course_id, created


def review(client, headers, course_id, evaluation, text="Una risposta quasi completa."):
    use_provider(MockAIProvider(evaluation=evaluation))
    session = start(client, headers, course_id, "SCHEDULED_REVIEW").json()
    return session, answer(client, headers, session["id"], text).json()


def test_three_green_scores_offer_a_repeat_instead_of_a_grade(client, due_item, db_session):
    headers, course_id, created = due_item
    # Correct, understanding and precise; the answer just leaves a little out (graded HARD).
    _, result = review(client, headers, course_id, scores(0.9, 0.6, 0.9, 0.9))
    assert result["needs_repeat"] is True
    assert result["final_outcome"] is None
    assert result["schedule"] is None
    assert memory(db_session, created["id"]).level == 1  # nothing moved yet


def test_repeating_it_counts_as_correct_and_moves_forward(client, due_item, db_session):
    headers, course_id, created = due_item
    session, result = review(client, headers, course_id, scores(0.9, 0.6, 0.9, 0.9))
    repeated = client.post(
        f"{API}/answers/{result['answer_id']}/repeat",
        json={"text": "Consegna di denaro con obbligo di restituzione."},
        headers=headers,
    )
    assert repeated.status_code == 200, repeated.text
    body = repeated.json()
    assert (body["final_outcome"], body["needs_repeat"], body["needs_self_grade"]) == (
        "GOOD",
        False,
        False,
    )
    # Forward, never back: level 1 -> 2.
    assert (body["schedule"]["previous_level"], body["schedule"]["next_level"]) == (1, 2)
    assert memory(db_session, created["id"]).level == 2
    # The AI's own verdict is kept as written.
    assert body["resolved_outcome"] == "HARD"
    assert body["evaluation"]["classification"] == "PARTIALLY_CORRECT"
    # It earns XP as a correct answer, and the session moves on.
    assert body["xp"]["correct"] is True
    assert body["xp"]["xp"] > 0
    assert card(client, headers, session["id"])["done"] is True


def test_a_poor_answer_is_still_failed_and_never_offered_a_repeat(client, due_item, db_session):
    headers, course_id, created = due_item
    # Three green scores, but so incomplete (0.4) that it would be graded AGAIN: it fails.
    _, result = review(client, headers, course_id, scores(0.9, 0.4, 0.9, 0.9))
    assert result["needs_repeat"] is False
    assert (result["final_outcome"], result["resolved_outcome"]) == ("AGAIN", "AGAIN")
    assert result["schedule"] is not None
    # The failure is applied: never forward (a level-1 item can't fall further than level 1).
    assert result["schedule"]["next_level"] <= result["schedule"]["previous_level"]
    assert memory(db_session, created["id"]).level == result["schedule"]["next_level"]


def test_a_hard_answer_with_three_green_scores_is_repeated_too(client, due_item):
    headers, course_id, _ = due_item
    # CORRECT but a bit incomplete (0.65 < 0.7): graded HARD, which would hold the level.
    _, result = review(
        client, headers, course_id, scores(0.9, 0.65, 0.9, 0.9, classification=C.CORRECT)
    )
    assert result["needs_repeat"] is True
    assert result["resolved_outcome"] == "HARD"


@pytest.mark.parametrize(
    ("evaluation", "outcome"),
    [
        (scores(0.9, 0.4, 0.6, 0.6), "AGAIN"),  # only one green
        (scores(0.9, 0.9, 0.5, 0.5), "HARD"),  # two green: graded as before
        (scores(0.9, 0.9, 0.9, 0.9, classification=C.CORRECT), "GOOD"),  # nothing to repeat
    ],
)
def test_other_answers_are_graded_as_before(client, due_item, db_session, evaluation, outcome):
    headers, course_id, created = due_item
    _, result = review(client, headers, course_id, evaluation)
    assert result["needs_repeat"] is False
    assert result["final_outcome"] == outcome
    assert result["resolved_outcome"] == outcome
    if outcome == "AGAIN":
        assert memory(db_session, created["id"]).level == 1  # the policy's own lapse handling


def test_an_unsure_evaluation_is_left_to_the_student(client, due_item):
    headers, course_id, _ = due_item
    unsure = scores(0.9, 0.6, 0.9, 0.9)
    unsure = unsure.model_copy(update={"confidence": 0.3})
    _, result = review(client, headers, course_id, unsure)
    assert (result["needs_repeat"], result["needs_self_grade"]) == (False, True)


def test_practice_sessions_never_offer_a_repeat(client, due_item):
    headers, course_id, created = due_item
    use_provider(MockAIProvider(evaluation=scores(0.9, 0.6, 0.9, 0.9)))
    session = start(
        client,
        headers,
        course_id,
        "PRACTICE",
        selection_mode="SELECTED",
        learning_item_ids=[created["id"]],
    ).json()
    result = answer(client, headers, session["id"], "Quasi").json()
    assert result["needs_repeat"] is False


def test_a_repeat_is_refused_when_not_offered_or_already_used(client, due_item):
    headers, course_id, _ = due_item
    _, plain = review(
        client, headers, course_id, scores(0.9, 0.9, 0.9, 0.9, classification=C.CORRECT)
    )
    refused = client.post(
        f"{API}/answers/{plain['answer_id']}/repeat", json={"text": "x"}, headers=headers
    )
    assert (refused.status_code, refused.json()["details"]["reason"]) == (409, "repeat_not_offered")


def test_a_repeat_can_only_be_made_once(client, due_item):
    headers, course_id, _ = due_item
    _, result = review(client, headers, course_id, scores(0.9, 0.6, 0.9, 0.9))
    url = f"{API}/answers/{result['answer_id']}/repeat"
    assert client.post(url, json={"text": "Ancora"}, headers=headers).status_code == 200
    again = client.post(url, json={"text": "Ancora"}, headers=headers)
    assert (again.status_code, again.json()["details"]["reason"]) == (409, "already_graded")


def test_a_repeat_needs_text_and_only_its_owner_can_make_it(client, due_item, auth_headers):
    headers, course_id, _ = due_item
    _, result = review(client, headers, course_id, scores(0.9, 0.6, 0.9, 0.9))
    url = f"{API}/answers/{result['answer_id']}/repeat"
    assert client.post(url, json={"text": ""}, headers=headers).status_code == 422
    other = auth_headers("nosy2@example.com")
    assert client.post(url, json={"text": "x"}, headers=other).status_code == 404


def test_the_student_can_still_grade_a_repeatable_answer_themselves(client, due_item):
    headers, course_id, _ = due_item
    _, result = review(client, headers, course_id, scores(0.9, 0.6, 0.9, 0.9))
    graded = client.post(
        f"{API}/answers/{result['answer_id']}/override", json={"outcome": "HARD"}, headers=headers
    )
    assert graded.status_code == 200
    assert (graded.json()["final_outcome"], graded.json()["needs_repeat"]) == ("HARD", False)


def test_a_first_answer_to_a_new_item_repeated_starts_its_schedule(client, course, db_session):  # noqa: F811
    headers, course_id, _, topic_id = course
    created = item(client, headers, concept(client, headers, topic_id)["id"])
    use_provider(MockAIProvider(evaluation=scores(0.9, 0.6, 0.9, 0.9)))
    session = start(client, headers, course_id).json()
    result = answer(client, headers, session["id"], FULL).json()
    assert result["needs_repeat"] is True
    done = client.post(
        f"{API}/answers/{result['answer_id']}/repeat", json={"text": FULL}, headers=headers
    ).json()
    assert done["final_outcome"] == "GOOD"
    assert memory(db_session, created["id"]).level == 1
