"""AI question generation for a Learning Item (docs/PROJECT_SPEC.md §27-29, FREE_AI_ROUTING.md).

Runs on the item, not on documents: the request carries the item's objective, reference answer,
essential points, its own passages and existing formulations. New formulations share the item's
memory state and record which provider and model wrote them.
"""

import uuid

import pytest
from sqlalchemy import select

from app.ai.factory import get_ai_provider
from app.ai.mock import MockAIProvider
from app.ai.schemas import QuestionsOutput
from app.core.errors import AIUnavailableError
from app.main import app
from app.models.enums import QuestionType
from app.models.learning import QuestionFormulation, ReviewState
from tests.test_learning_items import items_of, manual_concept, sourced_concept


@pytest.fixture
def course(client, auth_headers):
    headers = auth_headers("questions-owner@example.com")
    course = client.post(
        "/api/v1/courses", json={"title": "Diritto bancario", "language": "it"}, headers=headers
    ).json()
    return headers, course["id"]


def generated_item(client, headers, course_id):
    concept = sourced_concept(client, headers, course_id)
    client.post(f"/api/v1/concepts/{concept['id']}/activate", headers=headers)
    return items_of(client, headers, concept["id"])[0]


def test_generates_grounded_formulations_for_the_item(client, course, ai_provider, db_session):
    headers, course_id = course
    item = generated_item(client, headers, course_id)
    before_state = db_session.scalar(
        select(ReviewState).where(ReviewState.learning_item_id == uuid.UUID(item["id"]))
    )
    before_id, before_level = before_state.id, before_state.level

    response = client.post(
        f"/api/v1/learning-items/{item['id']}/questions/generate",
        json={"count": 2, "question_types": ["APPLICATION", "SCENARIO"]},
        headers=headers,
    )

    assert response.status_code == 201, response.text
    new = response.json()
    assert [q["question_type"] for q in new] == ["APPLICATION", "SCENARIO"]
    [request] = ai_provider.question_requests
    assert request.item_title == item["title"]
    assert request.expected_knowledge == item["expected_knowledge"]
    assert request.essential_points == item["essential_points"]
    assert request.existing_questions == [q["text"] for q in item["questions"]]
    assert request.language == "it"
    assert request.passages
    assert all(p.text for p in request.passages)
    # Stored with provenance, on the same item and its single memory state.
    stored = db_session.get(QuestionFormulation, uuid.UUID(new[0]["id"]))
    assert (stored.ai_provider, stored.prompt_version) == ("mock", "mock_questions_v1")
    db_session.expire_all()
    after = db_session.scalar(
        select(ReviewState).where(ReviewState.learning_item_id == uuid.UUID(item["id"]))
    )
    assert after.id == before_id
    assert after.level == before_level


def test_duplicates_of_existing_wording_are_skipped(client, course):
    headers, course_id = course
    item = generated_item(client, headers, course_id)
    first = client.post(
        f"/api/v1/learning-items/{item['id']}/questions/generate",
        json={"count": 1, "question_types": ["SCENARIO"]},
        headers=headers,
    ).json()
    again = client.post(
        f"/api/v1/learning-items/{item['id']}/questions/generate",
        json={"count": 1, "question_types": ["SCENARIO"]},
        headers=headers,
    )
    assert len(first) == 1
    assert again.status_code == 201
    assert again.json() == []


def test_an_item_without_sources_is_refused(client, course):
    headers, course_id = course
    concept = manual_concept(client, headers, course_id)
    item = client.post(
        f"/api/v1/concepts/{concept['id']}/learning-items",
        json={"title": "Manuale", "expected_knowledge": "x"},
        headers=headers,
    ).json()
    response = client.post(
        f"/api/v1/learning-items/{item['id']}/questions/generate", json={}, headers=headers
    )
    assert response.status_code == 409
    assert response.json()["details"]["reason"] == "no_sources"


def test_insufficient_context_is_a_conflict_not_a_guess(client, course):
    headers, course_id = course
    item = generated_item(client, headers, course_id)

    class Refusing(MockAIProvider):
        def generate_questions(self, request):
            result = super().generate_questions(request)
            return type(result)(output=QuestionsOutput(context_sufficient=False), info=result.info)

    app.dependency_overrides[get_ai_provider] = lambda: Refusing()
    response = client.post(
        f"/api/v1/learning-items/{item['id']}/questions/generate", json={}, headers=headers
    )
    assert response.status_code == 409
    assert response.json()["details"]["reason"] == "insufficient_context"


@pytest.mark.parametrize("body", [{"count": 0}, {"count": 6}, {"question_types": []}])
def test_request_limits(client, course, body):
    headers, course_id = course
    item = generated_item(client, headers, course_id)
    response = client.post(
        f"/api/v1/learning-items/{item['id']}/questions/generate", json=body, headers=headers
    )
    assert response.status_code == 422


def test_ai_failure_changes_nothing(client, course, db_session):
    headers, course_id = course
    item = generated_item(client, headers, course_id)
    app.dependency_overrides[get_ai_provider] = lambda: MockAIProvider(
        error=AIUnavailableError("down")
    )
    response = client.post(
        f"/api/v1/learning-items/{item['id']}/questions/generate", json={}, headers=headers
    )
    assert response.status_code == 503
    count = len(db_session.scalars(select(QuestionFormulation)).all())
    assert count == len(item["questions"])


def test_without_ai_it_is_503(client, course):
    headers, course_id = course
    item = generated_item(client, headers, course_id)
    app.dependency_overrides[get_ai_provider] = lambda: None
    response = client.post(
        f"/api/v1/learning-items/{item['id']}/questions/generate", json={}, headers=headers
    )
    assert response.status_code == 503


def test_default_types_when_none_requested(client, course, ai_provider):
    headers, course_id = course
    item = generated_item(client, headers, course_id)
    client.post(f"/api/v1/learning-items/{item['id']}/questions/generate", json={}, headers=headers)
    assert ai_provider.question_requests[0].question_types == [
        QuestionType.EXPLANATION,
        QuestionType.APPLICATION,
        QuestionType.SCENARIO,
    ]


def test_exhausted_free_capacity_reaches_the_client_as_a_clean_503(client, course):
    from app.ai.catalog import RouteOperation, capability
    from app.ai.failures import FailureKind
    from app.ai.routing import Candidate, RoutedAIProvider

    headers, course_id = course
    item = generated_item(client, headers, course_id)
    quota = MockAIProvider(
        error=AIUnavailableError("quota", details={"failure": FailureKind.QUOTA_EXHAUSTED})
    )
    routed = RoutedAIProvider(
        {RouteOperation.QUESTION_GENERATION: [Candidate(capability("mock", "mock"), quota)]},
        cost_policy="FREE_ONLY",
    )
    app.dependency_overrides[get_ai_provider] = lambda: routed

    response = client.post(
        f"/api/v1/learning-items/{item['id']}/questions/generate", json={}, headers=headers
    )

    assert response.status_code == 503
    body = response.json()
    assert body["error_type"] == "free_capacity_exhausted"
    assert body["details"]["attempts"] == [
        {"provider": "mock", "model": "mock", "failure": "QUOTA_EXHAUSTED"}
    ]
