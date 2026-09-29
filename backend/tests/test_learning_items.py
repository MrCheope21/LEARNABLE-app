"""Learning Items and question formulations (docs/PROJECT_SPEC.md §21, §24-29, §56).

MockAIProvider's default: one CORE_TRAINABLE item per source passage (up to 3), each with two
formulations, citing that passage.
"""

import uuid
from datetime import timedelta

import pytest
from sqlalchemy import func, select

from app.ai.factory import get_ai_provider
from app.ai.mock import MockAIProvider
from app.ai.schemas import LearningItemsOutput
from app.core.errors import AIUnavailableError
from app.db.types import utc_now
from app.main import app
from app.models.course import Concept
from app.models.enums import ItemGenerationStatus
from app.models.learning import QuestionFormulation, ReviewState

NOTES = (
    b"# Contratti bancari\n\n"
    b"Il deposito bancario e il contratto con cui la banca acquista la proprieta del denaro. "
    b"Il depositante ha diritto alla restituzione.\n"
)


@pytest.fixture
def course(client, auth_headers):
    headers = auth_headers("items-owner@example.com")
    course = client.post(
        "/api/v1/courses", json={"title": "Diritto bancario", "language": "it"}, headers=headers
    ).json()
    return headers, course["id"]


def sourced_concept(client, headers, course_id):
    """A Concept built from uploaded material, so it has source passages."""
    chapter = client.post(
        f"/api/v1/courses/{course_id}/chapters", json={"title": "Banca"}, headers=headers
    ).json()
    client.post(
        f"/api/v1/courses/{course_id}/documents",
        files={"file": ("banca.md", NOTES, "text/markdown")},
        data={"chapter_id": chapter["id"]},
        headers=headers,
    )
    proposal = client.post(
        f"/api/v1/courses/{course_id}/curriculum-proposals",
        json={"chapter_id": chapter["id"]},
        headers=headers,
    ).json()
    proposal = client.get(f"/api/v1/curriculum-proposals/{proposal['id']}", headers=headers).json()
    body = {
        "topics": [
            {
                "title": t["title"],
                "concepts": [
                    {
                        "title": c["title"],
                        "source_chunk_ids": [s["chunk_id"] for s in c["sources"]],
                    }
                    for c in t["concepts"]
                ],
            }
            for t in proposal["topics"]
        ]
    }
    outline = client.post(
        f"/api/v1/curriculum-proposals/{proposal['id']}/apply", json=body, headers=headers
    ).json()
    return outline[0]["topics"][0]["concepts"][0]


def manual_concept(client, headers, course_id):
    chapter = client.post(
        f"/api/v1/courses/{course_id}/chapters", json={"title": "Manuale"}, headers=headers
    ).json()
    topic = client.post(
        f"/api/v1/chapters/{chapter['id']}/topics", json={"title": "T"}, headers=headers
    ).json()
    return client.post(
        f"/api/v1/topics/{topic['id']}/concepts", json={"title": "Mutuo"}, headers=headers
    ).json()


def items_of(client, headers, concept_id):
    return client.get(f"/api/v1/concepts/{concept_id}/learning-items", headers=headers).json()


def concept_state(db_session, concept_id):
    db_session.expire_all()
    return db_session.get(Concept, uuid.UUID(concept_id))


def use_provider(provider):
    app.dependency_overrides[get_ai_provider] = lambda: provider
    return provider


# --- Generation on activation (spec §21, §5.2 of the task) ---


def test_activating_a_sourced_concept_generates_its_learning_items(client, course, ai_provider):
    headers, course_id = course
    concept = sourced_concept(client, headers, course_id)

    activated = client.post(f"/api/v1/concepts/{concept['id']}/activate", headers=headers).json()

    assert activated["study_state"] == "ACTIVE"
    assert activated["item_generation_status"] == "GENERATING"
    [item] = items_of(client, headers, concept["id"])
    assert item["role"] == "CORE_TRAINABLE"
    assert item["in_training"] is True
    assert item["concept_id"] == concept["id"]
    assert item["course_id"] == course_id
    assert "deposito bancario" in item["expected_knowledge"]
    assert len(item["questions"]) == 2
    assert item["prompt_version"] == "mock_learning_items_v1"
    # Not encoded yet: it waits for a LEARN session, it is not scheduled.
    assert item["review_state"]["state"] == "NEW"
    assert item["review_state"]["level"] == 0
    assert item["review_state"]["due_at"] is None
    [source] = client.get(f"/api/v1/learning-items/{item['id']}/sources", headers=headers).json()
    assert "deposito bancario" in source["text"]
    # The Concept can be read on its own (e.g. to follow generation).
    one = client.get(f"/api/v1/concepts/{concept['id']}", headers=headers).json()
    assert (one["id"], one["item_generation_status"]) == (concept["id"], "READY")
    # The model saw only this Concept's passages.
    [request] = ai_provider.learning_item_requests
    assert request.concept_title == concept["title"]
    assert request.language == "it"


def test_generation_status_ends_ready(client, course, db_session):
    headers, course_id = course
    concept = sourced_concept(client, headers, course_id)
    client.post(f"/api/v1/concepts/{concept['id']}/activate", headers=headers)
    assert concept_state(db_session, concept["id"]).item_generation_status is (
        ItemGenerationStatus.READY
    )


def test_activation_without_sources_or_ai_generates_nothing(client, course, ai_provider):
    headers, course_id = course
    manual = manual_concept(client, headers, course_id)
    activated = client.post(f"/api/v1/concepts/{manual['id']}/activate", headers=headers).json()
    assert activated["item_generation_status"] == "NONE"

    sourced = sourced_concept(client, headers, course_id)
    app.dependency_overrides[get_ai_provider] = lambda: None
    activated = client.post(f"/api/v1/concepts/{sourced['id']}/activate", headers=headers)
    assert activated.status_code == 200
    assert activated.json()["item_generation_status"] == "NONE"
    assert ai_provider.learning_item_requests == []


def test_reactivation_does_not_generate_twice(client, course, ai_provider):
    headers, course_id = course
    concept = sourced_concept(client, headers, course_id)
    client.post(f"/api/v1/concepts/{concept['id']}/activate", headers=headers)
    client.post(f"/api/v1/concepts/{concept['id']}/deactivate", headers=headers)
    client.post(f"/api/v1/concepts/{concept['id']}/activate", headers=headers)
    assert len(ai_provider.learning_item_requests) == 1
    assert len(items_of(client, headers, concept["id"])) == 1


# --- Explicit generation ---


def test_explicit_generation_and_its_refusals(client, course):
    headers, course_id = course
    concept = sourced_concept(client, headers, course_id)
    url = f"/api/v1/concepts/{concept['id']}/learning-items/generate"

    response = client.post(url, headers=headers)
    assert response.status_code == 202
    assert len(items_of(client, headers, concept["id"])) == 1

    again = client.post(url, headers=headers)
    assert again.status_code == 409
    assert again.json()["details"]["reason"] == "items_exist"

    manual = manual_concept(client, headers, course_id)
    unsourced = client.post(
        f"/api/v1/concepts/{manual['id']}/learning-items/generate", headers=headers
    )
    assert unsourced.status_code == 409
    assert unsourced.json()["details"]["reason"] == "no_source_material"


def test_generation_without_ai_is_503(client, course):
    headers, course_id = course
    concept = sourced_concept(client, headers, course_id)
    app.dependency_overrides[get_ai_provider] = lambda: None
    response = client.post(
        f"/api/v1/concepts/{concept['id']}/learning-items/generate", headers=headers
    )
    assert response.status_code == 503


def test_uncited_items_are_dropped_and_nothing_left_is_insufficient(client, course, db_session):
    headers, course_id = course
    concept = sourced_concept(client, headers, course_id)
    use_provider(
        MockAIProvider(
            learning_items=LearningItemsOutput.model_validate(
                {
                    "context_sufficient": True,
                    "items": [
                        {
                            "title": "Invented",
                            "expected_knowledge": "Not in the material.",
                            "role": "CORE_TRAINABLE",
                            "source_refs": ["S99"],
                            "questions": [{"question_type": "RECALL", "text": "?"}],
                        }
                    ],
                }
            )
        )
    )
    client.post(f"/api/v1/concepts/{concept['id']}/learning-items/generate", headers=headers)

    assert items_of(client, headers, concept["id"]) == []
    state = concept_state(db_session, concept["id"])
    assert state.item_generation_status is ItemGenerationStatus.INSUFFICIENT_CONTEXT


def test_provider_failure_is_recorded_and_can_be_retried(client, course, db_session):
    headers, course_id = course
    concept = sourced_concept(client, headers, course_id)
    url = f"/api/v1/concepts/{concept['id']}/learning-items/generate"
    use_provider(MockAIProvider(error=AIUnavailableError("The AI provider is down.")))
    client.post(url, headers=headers)
    state = concept_state(db_session, concept["id"])
    assert state.item_generation_status is ItemGenerationStatus.FAILED
    assert state.item_generation_error == "The AI provider is down."

    use_provider(MockAIProvider())
    assert client.post(url, headers=headers).status_code == 202
    assert len(items_of(client, headers, concept["id"])) == 1


def test_a_running_generation_blocks_until_it_goes_stale(client, course, db_session):
    headers, course_id = course
    concept = sourced_concept(client, headers, course_id)
    row = concept_state(db_session, concept["id"])
    row.item_generation_status = ItemGenerationStatus.GENERATING
    row.item_generation_started_at = utc_now()
    db_session.commit()
    url = f"/api/v1/concepts/{concept['id']}/learning-items/generate"

    assert client.post(url, headers=headers).status_code == 409
    row.item_generation_started_at = utc_now() - timedelta(hours=1)
    db_session.commit()
    assert client.post(url, headers=headers).status_code == 202


# --- Training roles (spec §24) ---


def _item(role="CORE_TRAINABLE", questions=True, **extra):
    return {
        "title": "Mutuo: definizione",
        "expected_knowledge": "Il mutuo e il contratto con cui una parte consegna denaro.",
        "essential_points": ["consegna di denaro", "obbligo di restituzione"],
        "role": role,
        "questions": [{"question_type": "DEFINITION", "text": "Che cos'e il mutuo?"}]
        if questions
        else [],
        **extra,
    }


def test_trainable_items_with_questions_start_in_training(client, course):
    headers, course_id = course
    concept = manual_concept(client, headers, course_id)
    url = f"/api/v1/concepts/{concept['id']}/learning-items"

    trained = client.post(url, json=_item(), headers=headers).json()
    info = client.post(url, json=_item(role="INFORMATIONAL"), headers=headers).json()
    no_questions = client.post(url, json=_item(questions=False), headers=headers).json()

    assert trained["in_training"] is True
    assert info["in_training"] is False
    assert no_questions["in_training"] is False
    assert [i["order"] for i in items_of(client, headers, concept["id"])] == [0, 1, 2]


def test_informational_content_can_be_promoted_and_removed_without_losing_anything(client, course):
    headers, course_id = course
    concept = manual_concept(client, headers, course_id)
    item = client.post(
        f"/api/v1/concepts/{concept['id']}/learning-items",
        json=_item(role="INFORMATIONAL"),
        headers=headers,
    ).json()

    promoted = client.post(f"/api/v1/learning-items/{item['id']}/train", headers=headers).json()
    assert promoted["in_training"] is True
    assert promoted["role"] == "INFORMATIONAL"  # the role describes content; training is a choice

    removed = client.post(f"/api/v1/learning-items/{item['id']}/untrain", headers=headers).json()
    assert removed["in_training"] is False
    assert removed["questions"] == promoted["questions"]
    assert removed["review_state"] == promoted["review_state"]


def test_an_item_without_questions_cannot_be_trained(client, course):
    headers, course_id = course
    concept = manual_concept(client, headers, course_id)
    item = client.post(
        f"/api/v1/concepts/{concept['id']}/learning-items",
        json=_item(questions=False),
        headers=headers,
    ).json()
    response = client.post(f"/api/v1/learning-items/{item['id']}/train", headers=headers)
    assert response.status_code == 409
    assert response.json()["details"]["reason"] == "no_questions"

    client.post(
        f"/api/v1/learning-items/{item['id']}/questions",
        json={"question_type": "RECALL", "text": "Il mutuo?"},
        headers=headers,
    )
    trained = client.post(f"/api/v1/learning-items/{item['id']}/train", headers=headers)
    assert trained.json()["in_training"] is True


# --- Formulations share one memory state (spec §27) ---


def test_every_formulation_shares_the_items_single_memory_state(client, course, db_session):
    headers, course_id = course
    concept = manual_concept(client, headers, course_id)
    item = client.post(
        f"/api/v1/concepts/{concept['id']}/learning-items", json=_item(), headers=headers
    ).json()
    client.post(
        f"/api/v1/learning-items/{item['id']}/questions",
        json={"question_type": "SCENARIO", "text": "Tizio presta denaro a Caio: che contratto e?"},
        headers=headers,
    )

    item_id = uuid.UUID(item["id"])
    questions = db_session.scalar(
        select(func.count()).where(QuestionFormulation.learning_item_id == item_id)
    )
    states = db_session.scalar(select(func.count()).where(ReviewState.learning_item_id == item_id))
    assert (questions, states) == (2, 1)


# --- Editing and pausing ---


def test_editing_content_never_touches_memory_state(client, course):
    headers, course_id = course
    concept = manual_concept(client, headers, course_id)
    item = client.post(
        f"/api/v1/concepts/{concept['id']}/learning-items", json=_item(), headers=headers
    ).json()
    edited = client.patch(
        f"/api/v1/learning-items/{item['id']}",
        json={"title": "Il mutuo", "essential_points": ["consegna"], "difficulty": 4},
        headers=headers,
    ).json()
    assert (edited["title"], edited["difficulty"]) == ("Il mutuo", 4)
    assert edited["review_state"] == item["review_state"]

    rejected = client.patch(
        f"/api/v1/learning-items/{item['id']}", json={"review_state": {"level": 8}}, headers=headers
    )
    assert rejected.status_code == 422


def test_item_pause_and_resume(client, course):
    headers, course_id = course
    concept = manual_concept(client, headers, course_id)
    item = client.post(
        f"/api/v1/concepts/{concept['id']}/learning-items", json=_item(), headers=headers
    ).json()
    paused = client.post(f"/api/v1/learning-items/{item['id']}/pause", headers=headers).json()
    assert paused["paused"] is True
    resumed = client.post(f"/api/v1/learning-items/{item['id']}/resume", headers=headers).json()
    assert resumed["paused"] is False


def test_deleting_the_concept_deletes_its_items(client, course):
    headers, course_id = course
    concept = manual_concept(client, headers, course_id)
    item = client.post(
        f"/api/v1/concepts/{concept['id']}/learning-items", json=_item(), headers=headers
    ).json()
    client.delete(f"/api/v1/concepts/{concept['id']}", headers=headers)
    assert client.get(f"/api/v1/learning-items/{item['id']}", headers=headers).status_code == 404


def test_items_of_another_course_are_404(client, course, auth_headers):
    headers, course_id = course
    concept = manual_concept(client, headers, course_id)
    item = client.post(
        f"/api/v1/concepts/{concept['id']}/learning-items", json=_item(), headers=headers
    ).json()
    stranger = auth_headers("stranger@example.com")
    for method, url in [
        ("GET", f"/api/v1/learning-items/{item['id']}"),
        ("GET", f"/api/v1/concepts/{concept['id']}/learning-items"),
        ("POST", f"/api/v1/learning-items/{item['id']}/untrain"),
    ]:
        assert client.request(method, url, headers=stranger).status_code == 404
