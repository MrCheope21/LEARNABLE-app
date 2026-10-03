"""Second opinions (POST /answers/{id}/dispute) and the weak-spots page.

A second opinion asks the evaluator again with the student's objection. It is stored beside the
first evaluation and never changes the outcome, the schedule or XP.
"""

import uuid

import pytest
from sqlalchemy import select
from test_review import answer as submit
from test_review import concept, course, item, scripted, start  # noqa: F401

from app.ai.mock import MockAIProvider
from app.ai.schemas import EvaluationOutput, EvaluationRequest
from app.core.errors import AIUnavailableError
from app.db.types import utc_now
from app.models.enums import EvaluationClassification, EvaluationStatus
from app.models.review import Evaluation

ANSWER = "Il mutuo e un prestito."


def _graded(request: EvaluationRequest) -> EvaluationOutput:
    """First opinion: wrong, with a misconception. Second opinion (an objection is present): ok."""
    if request.user_argument:
        return scripted(
            EvaluationClassification.CORRECT,
            0.95,
            correct_points=["reconsidered"],
            misconceptions=["Solo nel secondo parere"],
        )
    return scripted(
        EvaluationClassification.WRONG, 0.1, misconceptions=["Confonde mutuo e comodato"]
    )


@pytest.fixture
def ai_provider() -> MockAIProvider:
    return MockAIProvider(evaluation=_graded)


@pytest.fixture
def answered(client, course):  # noqa: F811
    headers, course_id, _, topic_id = course
    created = concept(client, headers, topic_id)
    item(client, headers, created["id"])
    session = start(client, headers, course_id).json()
    result = submit(client, headers, session["id"], ANSWER).json()
    return headers, course_id, created["id"], result


def dispute(client, headers, answer_id, argument="Il mutuo prevede anche la restituzione."):
    return client.post(
        f"/api/v1/answers/{answer_id}/dispute", json={"argument": argument}, headers=headers
    )


def test_a_second_opinion_is_kept_beside_the_first_and_changes_no_grade(client, answered):
    headers, _, _, result = answered
    assert result["evaluation"]["classification"] == "WRONG"
    assert result["second_opinion"] is None

    response = dispute(client, headers, result["answer_id"])
    assert response.status_code == 200
    body = response.json()
    assert body["evaluation"]["classification"] == "WRONG"
    assert body["evaluation"]["user_argument"] is None
    assert body["second_opinion"]["classification"] == "CORRECT"
    assert body["second_opinion"]["user_argument"] == "Il mutuo prevede anche la restituzione."
    assert body["final_outcome"] == result["final_outcome"]
    assert body["xp"] == result["xp"]


def test_the_evaluator_sees_the_objection_only_on_the_second_call(client, answered, ai_provider):
    headers, _, _, result = answered
    dispute(client, headers, result["answer_id"], "Penso che la mia risposta basti.")
    first, second = ai_provider.evaluation_requests
    assert first.user_argument is None
    assert second.user_argument == "Penso che la mia risposta basti."


def test_second_opinions_do_not_stand_in_for_the_first_evaluation(client, answered, db_session):
    headers, _, _, result = answered
    dispute(client, headers, result["answer_id"])
    stored = db_session.scalars(select(Evaluation).order_by(Evaluation.created_at)).all()
    assert [e.user_argument is None for e in stored] == [True, False]
    reread = client.get(f"/api/v1/answers/{result['answer_id']}", headers=headers).json()
    assert reread["evaluation"]["user_argument"] is None
    assert len(reread["evaluations"]) == 2


def test_the_number_of_second_opinions_is_limited(client, answered):
    headers, _, _, result = answered
    for _ in range(3):
        assert dispute(client, headers, result["answer_id"]).status_code == 200
    blocked = dispute(client, headers, result["answer_id"])
    assert blocked.status_code == 409
    assert blocked.json()["details"]["reason"] == "dispute_limit"


def test_a_failed_second_opinion_is_shown_as_such(client, answered, ai_provider):
    headers, _, _, result = answered
    ai_provider._error = AIUnavailableError("down")
    body = dispute(client, headers, result["answer_id"]).json()
    assert body["second_opinion"]["status"] == "FAILED"
    assert body["evaluation"]["classification"] == "WRONG"


def test_an_objection_needs_a_few_words(client, answered):
    headers, _, _, result = answered
    assert dispute(client, headers, result["answer_id"], "x").status_code == 422


def test_weak_spots_lists_recent_misconceptions_by_concept(client, answered):
    headers, course_id, concept_id, _ = answered
    spots = client.get(f"/api/v1/courses/{course_id}/weak-spots", headers=headers).json()
    [concept] = spots["concepts"]
    assert concept["concept_id"] == concept_id
    assert (concept["concept_title"], concept["topic_title"], concept["chapter_title"]) == (
        "Mutuo",
        "Prestiti",
        "Contratti",
    )
    assert [(m["text"], m["count"]) for m in concept["misconceptions"]] == [
        ("Confonde mutuo e comodato", 1)
    ]


def test_weak_spots_ignore_second_opinions_and_empty_courses(client, answered, auth_headers):
    headers, course_id, _, result = answered
    dispute(client, headers, result["answer_id"])
    [concept] = client.get(f"/api/v1/courses/{course_id}/weak-spots", headers=headers).json()[
        "concepts"
    ]
    assert concept["total"] == 1

    other = auth_headers("other@example.com")
    empty = client.post("/api/v1/courses", json={"title": "Vuoto"}, headers=other).json()
    assert client.get(f"/api/v1/courses/{empty['id']}/weak-spots", headers=other).json() == {
        "concepts": []
    }


def test_second_opinions_never_reach_the_weak_spots_or_the_mastery_view(client, answered):
    headers, course_id, _, result = answered
    dispute(client, headers, result["answer_id"])
    spots = client.get(f"/api/v1/courses/{course_id}/weak-spots", headers=headers).text
    progress = client.get(f"/api/v1/courses/{course_id}/progress", headers=headers).text
    assert "Confonde mutuo e comodato" in spots
    assert "Confonde mutuo e comodato" in progress
    assert "Solo nel secondo parere" not in spots
    assert "Solo nel secondo parere" not in progress


def test_a_mistake_disappears_once_the_latest_evaluations_no_longer_show_it(
    client, answered, db_session
):
    headers, course_id, _, result = answered
    for _ in range(3):
        db_session.add(
            Evaluation(
                answer_id=uuid.UUID(result["answer_id"]),
                course_id=uuid.UUID(course_id),
                status=EvaluationStatus.COMPLETED,
                misconceptions=[],
                created_at=utc_now(),
            )
        )
    db_session.commit()
    spots = client.get(f"/api/v1/courses/{course_id}/weak-spots", headers=headers).json()
    assert spots == {"concepts": []}
