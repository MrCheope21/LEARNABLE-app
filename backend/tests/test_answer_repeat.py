"""A near miss (green on at least 3 of the 4 scores, graded HARD) is repeated after reviewing the
reference answer. The repeat is evaluated: repeated well, the first answer counts as correct and
the schedule moves forward; not well, it is failed and the item goes back to level 0. A poor
answer (AGAIN) never gets a repeat."""

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
from test_xp_consolidation import studied

from app.ai.mock import MockAIProvider
from app.ai.schemas import EvaluationOutput
from app.models.enums import EvaluationClassification as C

API = "/api/v1"


def scores(correctness, completeness, understanding, precision, classification=C.PARTIALLY_CORRECT):
    return EvaluationOutput(
        classification=classification,
        correctness=correctness,
        completeness=completeness,
        conceptual_understanding=understanding,
        precision=precision,
        confidence=0.9,
        context_sufficient=True,
    )


NEAR_MISS = scores(0.9, 0.6, 0.9, 0.9)  # 3 green, a little incomplete: HARD
POOR = scores(0.9, 0.4, 0.9, 0.9)  # 3 green but too incomplete: AGAIN
GOOD = scores(0.95, 0.95, 0.95, 0.95, C.CORRECT)
STILL_HARD = scores(0.9, 0.6, 0.9, 0.9)
WRONG = scores(0.2, 0.2, 0.2, 0.2, C.WRONG)
UNSURE = scores(0.5, 0.5, 0.5, 0.5, C.UNCERTAIN)


def provider(*evaluations):
    """Answers evaluated in order: the first answer, then its repeat, then what follows."""
    queue = list(evaluations)
    return use_provider(MockAIProvider(evaluation=lambda _request: queue.pop(0)))


@pytest.fixture
def due_item(client, course, db_session):  # noqa: F811
    """An encoded item (level 1) that is due for review."""
    headers, course_id, _, topic_id = course
    created = item(client, headers, concept(client, headers, topic_id)["id"])
    learn(client, headers, course_id)
    make_due(db_session, created["id"], ago=timedelta(days=2))
    return headers, course_id, created


def review(client, headers, course_id, *evaluations):
    provider(*evaluations)
    session = start(client, headers, course_id, "SCHEDULED_REVIEW").json()
    return session, answer(client, headers, session["id"], "Una risposta quasi completa.").json()


def repeat(client, headers, answer_id, text="Consegna di denaro con obbligo di restituzione."):
    return client.post(f"{API}/answers/{answer_id}/repeat", json={"text": text}, headers=headers)


def test_a_near_miss_is_not_graded_yet_but_offered_a_repeat(client, due_item, db_session):
    headers, course_id, created = due_item
    _, result = review(client, headers, course_id, NEAR_MISS)
    assert result["needs_repeat"] is True
    assert (result["final_outcome"], result["resolved_outcome"]) == (None, "HARD")
    assert result["schedule"] is None
    assert memory(db_session, created["id"]).level == 1  # nothing moved yet


def test_repeated_well_it_counts_as_correct_and_moves_forward(client, due_item, db_session):
    headers, course_id, created = due_item
    session, result = review(client, headers, course_id, NEAR_MISS, GOOD)
    done = repeat(client, headers, result["answer_id"])
    assert done.status_code == 200, done.text
    body = done.json()
    assert (body["final_outcome"], body["needs_repeat"], body["needs_self_grade"]) == (
        "GOOD",
        False,
        False,
    )
    # Forward, never back: level 1 -> 2, and the full XP of a correct answer.
    assert (body["schedule"]["previous_level"], body["schedule"]["next_level"]) == (1, 2)
    assert memory(db_session, created["id"]).level == 2
    assert body["xp"]["correct"] is True
    assert body["xp"]["xp"] > 0
    # The first evaluation is kept as written, and the repeat's own evaluation is shown too.
    assert body["resolved_outcome"] == "HARD"
    assert body["evaluation"]["classification"] == "PARTIALLY_CORRECT"
    assert body["repeat"]["classification"] == "CORRECT"
    assert card(client, headers, session["id"])["done"] is True


def test_not_repeated_well_it_fails_and_restarts_from_level_zero(client, due_item, db_session):
    headers, course_id, created = due_item
    session, result = review(client, headers, course_id, NEAR_MISS, WRONG)
    body = repeat(client, headers, result["answer_id"], "Boh.").json()
    assert (body["final_outcome"], body["needs_repeat"]) == ("AGAIN", False)
    assert body["xp"]["correct"] is False
    assert body["schedule"]["next_level"] == 0
    state = memory(db_session, created["id"])
    assert (state.level, state.state.value) == (0, "RELEARNING")
    # A failed item must still be answered well once in this session.
    assert body["session"]["total"] == 2
    assert card(client, headers, session["id"])["done"] is False


def test_a_repeat_that_is_only_hard_is_not_well_either(client, due_item, db_session):
    headers, course_id, created = due_item
    _, result = review(client, headers, course_id, NEAR_MISS, STILL_HARD)
    body = repeat(client, headers, result["answer_id"]).json()
    assert body["final_outcome"] == "AGAIN"
    assert memory(db_session, created["id"]).level == 0


def test_after_a_failed_repeat_one_good_answer_ends_it_and_starts_at_level_one(
    client, due_item, db_session
):
    headers, course_id, created = due_item
    session, result = review(client, headers, course_id, NEAR_MISS, WRONG, GOOD)
    repeat(client, headers, result["answer_id"])
    again = answer(client, headers, session["id"], FULL).json()
    assert again["final_outcome"] == "GOOD"
    assert (again["schedule"]["previous_level"], again["schedule"]["next_level"]) == (0, 1)
    assert card(client, headers, session["id"])["done"] is True
    assert memory(db_session, created["id"]).level == 1


def test_a_poor_answer_is_failed_without_a_repeat(client, due_item, db_session):
    headers, course_id, created = due_item
    # Three green scores, but so incomplete (0.4) that it would be graded AGAIN: it fails.
    session, result = review(client, headers, course_id, POOR)
    assert result["needs_repeat"] is False
    assert (result["final_outcome"], result["resolved_outcome"]) == ("AGAIN", "AGAIN")
    assert result["schedule"]["next_level"] == 0
    state = memory(db_session, created["id"])
    assert (state.level, state.state.value) == (0, "RELEARNING")
    assert result["session"]["total"] == 2
    assert card(client, headers, session["id"])["done"] is False


def test_a_hard_answer_with_three_green_scores_is_offered_the_repeat_too(client, due_item):
    headers, course_id, _ = due_item
    _, result = review(client, headers, course_id, scores(0.9, 0.65, 0.9, 0.9, C.CORRECT))
    assert result["needs_repeat"] is True
    assert result["resolved_outcome"] == "HARD"


@pytest.mark.parametrize(
    ("evaluation", "outcome"),
    [
        (scores(0.9, 0.6, 0.6, 0.6), "HARD"),  # only one green: graded as before
        (scores(0.9, 0.9, 0.9, 0.9, C.CORRECT), "GOOD"),  # nothing to repeat
    ],
)
def test_other_answers_are_graded_as_before(client, due_item, evaluation, outcome):
    headers, course_id, _ = due_item
    _, result = review(client, headers, course_id, evaluation)
    assert result["needs_repeat"] is False
    assert result["final_outcome"] == outcome


def test_an_unsure_evaluation_is_left_to_the_student(client, due_item):
    headers, course_id, _ = due_item
    unsure = NEAR_MISS.model_copy(update={"confidence": 0.3})
    _, result = review(client, headers, course_id, unsure)
    assert (result["needs_repeat"], result["needs_self_grade"]) == (False, True)


def test_practice_sessions_never_offer_a_repeat(client, due_item):
    headers, course_id, created = due_item
    provider(NEAR_MISS)
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


def test_a_repeat_nobody_can_judge_is_left_to_the_student(client, due_item, db_session):
    headers, course_id, created = due_item
    _, result = review(client, headers, course_id, NEAR_MISS, UNSURE)
    body = repeat(client, headers, result["answer_id"]).json()
    assert (body["final_outcome"], body["needs_repeat"], body["needs_self_grade"]) == (
        None,
        False,
        True,
    )
    assert memory(db_session, created["id"]).level == 1  # still nothing moved
    graded = client.post(
        f"{API}/answers/{result['answer_id']}/override", json={"outcome": "GOOD"}, headers=headers
    ).json()
    assert graded["final_outcome"] == "GOOD"


def test_a_repeat_is_refused_when_not_offered_or_already_used(client, due_item):
    headers, course_id, _ = due_item
    _, plain = review(client, headers, course_id, GOOD)
    refused = repeat(client, headers, plain["answer_id"], "x")
    assert (refused.status_code, refused.json()["details"]["reason"]) == (
        409,
        "repeat_not_offered",
    )


def test_a_repeat_can_only_be_made_once(client, due_item):
    headers, course_id, _ = due_item
    _, result = review(client, headers, course_id, NEAR_MISS, GOOD)
    assert repeat(client, headers, result["answer_id"], "Ancora").status_code == 200
    again = repeat(client, headers, result["answer_id"], "Ancora")
    assert (again.status_code, again.json()["details"]["reason"]) == (409, "already_graded")


def test_a_repeat_needs_text_and_only_its_owner_can_make_it(client, due_item, auth_headers):
    headers, course_id, _ = due_item
    _, result = review(client, headers, course_id, NEAR_MISS)
    url = f"{API}/answers/{result['answer_id']}/repeat"
    assert client.post(url, json={"text": ""}, headers=headers).status_code == 422
    other = auth_headers("nosy2@example.com")
    assert client.post(url, json={"text": "x"}, headers=other).status_code == 404


def test_the_student_can_still_grade_a_repeatable_answer_themselves(client, due_item):
    headers, course_id, _ = due_item
    _, result = review(client, headers, course_id, NEAR_MISS)
    graded = client.post(
        f"{API}/answers/{result['answer_id']}/override", json={"outcome": "HARD"}, headers=headers
    )
    assert graded.status_code == 200
    assert (graded.json()["final_outcome"], graded.json()["needs_repeat"]) == ("HARD", False)


def test_the_repeat_is_not_a_pending_answer_of_its_own(client, due_item):
    headers, course_id, _ = due_item
    session, result = review(client, headers, course_id, NEAR_MISS, UNSURE)
    repeat(client, headers, result["answer_id"])
    # Only the first answer waits (for the student's grade): no second pending card.
    pending = card(client, headers, session["id"])["card"]["pending_answer_id"]
    assert pending == result["answer_id"]


def test_in_the_first_study_a_repeated_near_miss_counts_as_one_good_answer(
    client,
    course,  # noqa: F811
    db_session,
):
    headers, _, _, topic_id = course
    made = concept(client, headers, topic_id)
    it = item(client, headers, made["id"])
    provider(NEAR_MISS, GOOD)
    session = studied(client, headers, made["id"]).json()
    first = answer(client, headers, session["id"], "Quasi").json()
    assert first["needs_repeat"] is True
    body = repeat(client, headers, first["answer_id"]).json()
    assert body["final_outcome"] == "GOOD"
    # One good answer of the three needed; the item isn't learned yet.
    assert card(client, headers, session["id"])["card"]["round"] == 2
    assert memory(db_session, it["id"]).state.value == "NEW"
