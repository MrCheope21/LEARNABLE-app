"""AI curriculum generation over the API (docs/PROJECT_SPEC.md §18-21, §36, §72).

Uses MockAIProvider (spec §76): one Chapter per document, one Topic per section, one Concept per
passage, each citing its passage. Tests that need other answers install their own mock.
"""

import logging
import uuid
from datetime import timedelta

import pytest
from samples import make_png
from sqlalchemy import select

from app.ai.factory import get_ai_provider
from app.ai.mock import MockAIProvider
from app.ai.schemas import CurriculumOutput
from app.api.curriculum import get_max_context_chars
from app.core.errors import AIUnavailableError
from app.db.types import utc_now
from app.main import app
from app.models.curriculum import ConceptSource, CurriculumProposal
from app.models.enums import CurriculumProposalStatus

NOTES = (
    b"# Contratti bancari\n\n"
    b"Il deposito bancario e il contratto con cui la banca acquista la proprieta del denaro.\n\n"
    b"# Crediti\n\n"
    b"L'apertura di credito obbliga la banca a tenere una somma a disposizione del cliente.\n"
)


@pytest.fixture
def course(client, auth_headers):
    headers = auth_headers("curriculum-owner@example.com")
    course = client.post(
        "/api/v1/courses", json={"title": "Diritto bancario", "language": "it"}, headers=headers
    ).json()
    return headers, course["id"]


def upload(client, headers, course_id, name="banca.md", data=NOTES):
    response = client.post(
        f"/api/v1/courses/{course_id}/documents",
        files={"file": (name, data, "application/octet-stream")},
        headers=headers,
    )
    assert response.status_code == 202, response.text
    return response.json()["id"]


def generate(client, headers, course_id, body=None):
    """Returns (POST response, the proposal after its background generation)."""
    response = client.post(
        f"/api/v1/courses/{course_id}/curriculum-proposals", json=body, headers=headers
    )
    if response.status_code != 202:
        return response, None
    # TestClient runs background tasks before returning, so generation has finished.
    proposal = client.get(f"/api/v1/curriculum-proposals/{response.json()['id']}", headers=headers)
    return response, proposal.json()


def use_provider(provider: MockAIProvider) -> MockAIProvider:
    app.dependency_overrides[get_ai_provider] = lambda: provider
    return provider


def as_apply_body(proposal: dict) -> dict:
    """The proposal accepted unchanged, in the shape POST .../apply takes."""
    return {
        "chapters": [
            {
                "title": chapter["title"],
                "description": chapter["description"],
                "topics": [
                    {
                        "title": topic["title"],
                        "description": topic["description"],
                        "concepts": [
                            {
                                "title": concept["title"],
                                "description": concept["description"],
                                "source_chunk_ids": [s["chunk_id"] for s in concept["sources"]],
                            }
                            for concept in topic["concepts"]
                        ],
                    }
                    for topic in chapter["topics"]
                ],
            }
            for chapter in proposal["chapters"]
        ]
    }


# --- Generation ---


def test_generation_returns_202_then_a_grounded_proposal(client, course, ai_provider):
    headers, course_id = course
    document_id = upload(client, headers, course_id)

    response, proposal = generate(client, headers, course_id)

    assert response.status_code == 202
    assert response.json()["status"] == "GENERATING"
    assert response.json()["chapters"] is None
    assert proposal["status"] == "READY"
    assert proposal["passages_used"] == proposal["passages_total"] == 2
    assert proposal["dropped_concepts"] == 0
    assert (proposal["ai_provider"], proposal["prompt_version"]) == ("mock", "mock_curriculum_v1")
    [chapter] = proposal["chapters"]
    assert chapter["title"] == "banca"
    assert [t["title"] for t in chapter["topics"]] == ["Contratti bancari", "Crediti"]
    concept = chapter["topics"][0]["concepts"][0]
    [source] = concept["sources"]
    assert source["document_id"] == document_id
    assert source["section"] == "Contratti bancari"

    # The model saw the Course's own material, in its language.
    [sent] = ai_provider.curriculum_requests
    assert sent.language == "it"
    assert sent.course_title == "Diritto bancario"
    assert "deposito bancario" in sent.passages[0].text


def test_proposal_does_not_touch_the_course_until_applied(client, course):
    headers, course_id = course
    upload(client, headers, course_id)
    generate(client, headers, course_id)
    assert client.get(f"/api/v1/courses/{course_id}/outline", headers=headers).json() == []


def test_without_processed_material_nothing_is_generated(client, course, ai_provider):
    headers, course_id = course
    response, _ = generate(client, headers, course_id)
    assert response.status_code == 409
    assert response.json()["details"]["reason"] == "no_source_material"

    upload(client, headers, course_id, "scan.png", make_png())  # stored, but FAILED
    response, _ = generate(client, headers, course_id)
    assert response.status_code == 409
    assert ai_provider.curriculum_requests == []


def test_ai_not_configured_is_503(client, course):
    headers, course_id = course
    upload(client, headers, course_id)
    app.dependency_overrides[get_ai_provider] = lambda: None
    response, _ = generate(client, headers, course_id)
    assert response.status_code == 503
    assert response.json()["error_type"] == "ai_not_configured"


def test_generation_can_be_limited_to_chosen_documents(client, course, ai_provider):
    headers, course_id = course
    upload(client, headers, course_id)
    other = upload(client, headers, course_id, "altro.txt", b"Il mutuo e un prestito di denaro.")

    _, proposal = generate(client, headers, course_id, {"document_ids": [other]})

    assert proposal["passages_total"] == 1
    [sent] = ai_provider.curriculum_requests
    assert [p.document_name for p in sent.passages] == ["altro.txt"]


def test_chosen_documents_must_be_this_courses_and_ready(client, course, auth_headers):
    headers, course_id = course
    upload(client, headers, course_id)
    failed = upload(client, headers, course_id, "scan.png", make_png())
    stranger = auth_headers("stranger@example.com")
    their_course = client.post("/api/v1/courses", json={"title": "X"}, headers=stranger).json()
    theirs = upload(client, stranger, their_course["id"], "theirs.txt", b"Their private notes.")

    response, _ = generate(client, headers, course_id, {"document_ids": [theirs]})
    assert response.status_code == 404
    response, _ = generate(client, headers, course_id, {"document_ids": [failed]})
    assert response.status_code == 409
    assert response.json()["details"]["document_ids"] == [failed]


def test_material_over_the_context_budget_is_cut_and_reported(client, course, ai_provider):
    headers, course_id = course
    paragraphs = [f"Paragrafo {i}. " + "Il credito bancario e regolato. " * 35 for i in range(6)]
    upload(client, headers, course_id, "lungo.txt", "\n\n".join(paragraphs).encode())
    app.dependency_overrides[get_max_context_chars] = lambda: 2_000

    _, proposal = generate(client, headers, course_id)

    assert proposal["status"] == "READY"
    assert proposal["passages_total"] > proposal["passages_used"] >= 1
    sent = ai_provider.curriculum_requests[0].passages
    assert sum(len(p.text) for p in sent) <= 2_000 or len(sent) == 1


def test_only_one_generation_at_a_time_and_interrupted_ones_expire(client, course, db_session):
    headers, course_id = course
    upload(client, headers, course_id)
    running = CurriculumProposal(
        course_id=uuid.UUID(course_id), status=CurriculumProposalStatus.GENERATING
    )
    db_session.add(running)
    db_session.commit()

    response, _ = generate(client, headers, course_id)
    assert response.status_code == 409
    assert response.json()["details"]["proposal_id"] == str(running.id)

    # Still GENERATING long after any AI call could last: the server restarted mid-generation.
    running.updated_at = utc_now() - timedelta(hours=1)
    db_session.commit()
    response, proposal = generate(client, headers, course_id)
    assert response.status_code == 202
    assert proposal["status"] == "READY"
    expired = client.get(f"/api/v1/curriculum-proposals/{running.id}", headers=headers).json()
    assert expired["status"] == "FAILED"
    assert "interrupted" in expired["error_message"]


# --- Grounding and failures (spec §19, §36) ---


def _output(*concepts: dict) -> CurriculumOutput:
    return CurriculumOutput.model_validate(
        {
            "context_sufficient": True,
            "chapters": [{"title": "Ch", "topics": [{"title": "T", "concepts": list(concepts)}]}],
        }
    )


def test_concepts_citing_passages_that_were_not_sent_are_dropped(client, course):
    headers, course_id = course
    upload(client, headers, course_id)
    use_provider(
        MockAIProvider(
            curriculum=_output(
                {"title": "Grounded", "source_refs": ["S1", "S1", "S404"]},
                {"title": "Invented", "source_refs": ["S404"]},
                {"title": "Uncited", "source_refs": []},
            )
        )
    )

    _, proposal = generate(client, headers, course_id)

    assert proposal["status"] == "READY"
    assert proposal["dropped_concepts"] == 2
    [concept] = proposal["chapters"][0]["topics"][0]["concepts"]
    assert concept["title"] == "Grounded"
    assert len(concept["sources"]) == 1


def test_nothing_grounded_is_insufficient_context_not_a_fake_curriculum(client, course):
    headers, course_id = course
    upload(client, headers, course_id)
    use_provider(MockAIProvider(curriculum=_output({"title": "Invented", "source_refs": ["S9"]})))

    _, proposal = generate(client, headers, course_id)

    assert proposal["status"] == "INSUFFICIENT_CONTEXT"
    assert proposal["chapters"] is None
    assert proposal["dropped_concepts"] == 1
    assert "tie to your study material" in proposal["error_message"]


def test_model_reporting_insufficient_context(client, course):
    headers, course_id = course
    upload(client, headers, course_id)
    use_provider(MockAIProvider(curriculum=CurriculumOutput(context_sufficient=False, chapters=[])))
    _, proposal = generate(client, headers, course_id)
    assert proposal["status"] == "INSUFFICIENT_CONTEXT"
    assert proposal["ai_provider"] == "mock"


def test_provider_error_marks_the_proposal_failed_with_its_reason(client, course):
    headers, course_id = course
    upload(client, headers, course_id)
    use_provider(MockAIProvider(error=AIUnavailableError("The AI provider took too long.")))
    _, proposal = generate(client, headers, course_id)
    assert proposal["status"] == "FAILED"
    assert proposal["error_message"] == "The AI provider took too long."


def test_unexpected_error_fails_safely_without_logging_content(client, course, caplog):
    headers, course_id = course
    upload(client, headers, course_id)
    use_provider(MockAIProvider(error=RuntimeError("boom")))
    caplog.set_level(logging.INFO)

    _, proposal = generate(client, headers, course_id)

    assert proposal["status"] == "FAILED"
    assert proposal["error_message"] == "The curriculum couldn't be generated."
    assert "deposito" not in caplog.text.lower()


# --- Review: apply, reject ---


def test_apply_creates_the_edited_curriculum_unactivated(client, course):
    headers, course_id = course
    upload(client, headers, course_id)
    _, proposal = generate(client, headers, course_id)
    body = as_apply_body(proposal)
    # The user renames a Concept, drops the second Topic and adds a Concept of their own.
    topic = body["chapters"][0]["topics"][0]
    topic["concepts"][0]["title"] = "Deposito bancario"
    topic["concepts"].append({"title": "Conto corrente"})
    del body["chapters"][0]["topics"][1]

    response = client.post(
        f"/api/v1/curriculum-proposals/{proposal['id']}/apply", json=body, headers=headers
    )

    assert response.status_code == 201, response.text
    [chapter] = response.json()
    [created_topic] = chapter["topics"]
    assert [c["title"] for c in created_topic["concepts"]] == [
        "Deposito bancario",
        "Conto corrente",
    ]
    assert [c["order"] for c in created_topic["concepts"]] == [0, 1]
    for concept in created_topic["concepts"]:
        # Spec §20/§21: never activated automatically.
        assert concept["study_state"] == "NOT_STUDIED"
        assert concept["is_reviewable"] is False

    first, own = created_topic["concepts"]
    sources = client.get(f"/api/v1/concepts/{first['id']}/sources", headers=headers).json()
    assert len(sources) == 1
    assert "deposito bancario" in sources[0]["text"]
    assert client.get(f"/api/v1/concepts/{own['id']}/sources", headers=headers).json() == []

    applied = client.get(f"/api/v1/curriculum-proposals/{proposal['id']}", headers=headers).json()
    assert applied["status"] == "APPLIED"
    assert applied["applied_at"] is not None

    # The user activates what they studied, through the normal lifecycle.
    activated = client.post(f"/api/v1/concepts/{first['id']}/activate", headers=headers)
    assert activated.json()["study_state"] == "ACTIVE"


def test_apply_goes_after_existing_chapters_and_only_once(client, course):
    headers, course_id = course
    client.post(
        f"/api/v1/courses/{course_id}/chapters",
        json={"title": "Manual", "order": 4},
        headers=headers,
    )
    upload(client, headers, course_id)
    _, proposal = generate(client, headers, course_id)
    url = f"/api/v1/curriculum-proposals/{proposal['id']}/apply"

    outline = client.post(url, json=as_apply_body(proposal), headers=headers).json()
    assert [(c["title"], c["order"]) for c in outline] == [("Manual", 4), ("banca", 5)]

    again = client.post(url, json=as_apply_body(proposal), headers=headers)
    assert again.status_code == 409
    assert again.json()["details"]["status"] == "APPLIED"


def test_apply_never_links_another_courses_passage(client, course, auth_headers, db_session):
    headers, course_id = course
    upload(client, headers, course_id)
    _, proposal = generate(client, headers, course_id)
    stranger = auth_headers("stranger@example.com")
    theirs = client.post("/api/v1/courses", json={"title": "X"}, headers=stranger).json()
    their_doc = upload(client, stranger, theirs["id"], "theirs.txt", b"Their private notes.")
    [their_chunk] = client.get(f"/api/v1/documents/{their_doc}/chunks", headers=stranger).json()

    body = {"chapters": [{"title": "C", "topics": [{"title": "T", "concepts": [
        {"title": "Stolen", "source_chunk_ids": [their_chunk["id"]]}
    ]}]}]}  # fmt: skip
    outline = client.post(
        f"/api/v1/curriculum-proposals/{proposal['id']}/apply", json=body, headers=headers
    ).json()

    concept_id = outline[0]["topics"][0]["concepts"][0]["id"]
    assert client.get(f"/api/v1/concepts/{concept_id}/sources", headers=headers).json() == []
    # Checked in the database too: the read endpoint's own Course filter would hide a bad link.
    assert db_session.scalars(select(ConceptSource)).all() == []


def test_generation_only_ever_sends_this_courses_material(
    client, course, auth_headers, ai_provider
):
    headers, course_id = course
    stranger = auth_headers("stranger@example.com")
    theirs = client.post("/api/v1/courses", json={"title": "X"}, headers=stranger).json()
    upload(client, stranger, theirs["id"], "theirs.txt", b"Their private notes.")
    upload(client, headers, course_id)

    _, proposal = generate(client, headers, course_id)

    assert proposal["passages_total"] == 2
    [sent] = ai_provider.curriculum_requests
    assert {p.document_name for p in sent.passages} == {"banca.md"}


def test_only_ready_proposals_can_be_applied(client, course):
    headers, course_id = course
    upload(client, headers, course_id)
    use_provider(MockAIProvider(error=AIUnavailableError("down")))
    _, failed = generate(client, headers, course_id)
    response = client.post(
        f"/api/v1/curriculum-proposals/{failed['id']}/apply",
        json={"chapters": [{"title": "C"}]},
        headers=headers,
    )
    assert response.status_code == 409


@pytest.mark.parametrize(
    "body",
    [
        {"chapters": []},
        {"chapters": [{"title": ""}]},
        {"chapters": [{"title": "C", "extra": 1}]},
        {
            "chapters": [
                {"title": "C", "topics": [{"title": "T", "concepts": [{"title": "x" * 201}]}]}
            ]
        },
    ],
)
def test_apply_validates_the_tree(client, course, body):
    headers, course_id = course
    upload(client, headers, course_id)
    _, proposal = generate(client, headers, course_id)
    response = client.post(
        f"/api/v1/curriculum-proposals/{proposal['id']}/apply", json=body, headers=headers
    )
    assert response.status_code == 422


def test_rejecting_a_proposal_deletes_it(client, course):
    headers, course_id = course
    upload(client, headers, course_id)
    _, proposal = generate(client, headers, course_id)
    url = f"/api/v1/curriculum-proposals/{proposal['id']}"

    assert client.delete(url, headers=headers).status_code == 204
    assert client.get(url, headers=headers).status_code == 404
    assert (
        client.get(f"/api/v1/courses/{course_id}/curriculum-proposals", headers=headers).json()
        == []
    )


def test_proposals_are_listed_newest_first(client, course):
    headers, course_id = course
    upload(client, headers, course_id)
    _, first = generate(client, headers, course_id)
    _, second = generate(client, headers, course_id)
    listed = client.get(f"/api/v1/courses/{course_id}/curriculum-proposals", headers=headers).json()
    assert [p["id"] for p in listed] == [second["id"], first["id"]]


def test_deleting_the_document_removes_sources_but_keeps_concepts(client, course):
    headers, course_id = course
    document_id = upload(client, headers, course_id)
    _, proposal = generate(client, headers, course_id)
    outline = client.post(
        f"/api/v1/curriculum-proposals/{proposal['id']}/apply",
        json=as_apply_body(proposal),
        headers=headers,
    ).json()
    concept_id = outline[0]["topics"][0]["concepts"][0]["id"]

    client.delete(f"/api/v1/documents/{document_id}", headers=headers)

    assert client.get(f"/api/v1/concepts/{concept_id}/sources", headers=headers).json() == []
    assert len(client.get(f"/api/v1/courses/{course_id}/outline", headers=headers).json()) == 1
    stale = client.get(f"/api/v1/curriculum-proposals/{proposal['id']}", headers=headers).json()
    assert stale["chapters"][0]["topics"][0]["concepts"][0]["sources"] == []


# --- Outline ---


def test_outline_nests_and_orders_the_whole_course(client, course):
    headers, course_id = course
    chapter = client.post(
        f"/api/v1/courses/{course_id}/chapters", json={"title": "Ch"}, headers=headers
    ).json()
    topic = client.post(
        f"/api/v1/chapters/{chapter['id']}/topics", json={"title": "T"}, headers=headers
    ).json()
    for title, order in [("Second", 1), ("First", 0)]:
        client.post(
            f"/api/v1/topics/{topic['id']}/concepts",
            json={"title": title, "order": order},
            headers=headers,
        )

    [outlined] = client.get(f"/api/v1/courses/{course_id}/outline", headers=headers).json()
    assert [c["title"] for c in outlined["topics"][0]["concepts"]] == ["First", "Second"]
