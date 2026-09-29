"""Chapter-by-chapter material and incremental analysis (docs/PROJECT_SPEC.md §16, §19-21).

The user creates the Chapters, files material under each, and the AI proposes Topics → Concepts
for one Chapter at a time. Adding, revising or deleting material later is analyzed against what
the Chapter already contains. MockAIProvider matches existing Topics/Concepts by exact title.
"""

import pytest
from sqlalchemy import select

from app.models.curriculum import ConceptSource

BANKING = (
    b"# Contratti bancari\n\n"
    b"Il deposito bancario e un contratto reale. La banca acquista la proprieta del denaro.\n"
)
MORE_BANKING = (
    b"# Contratti bancari\n\n"
    b"L'apertura di credito obbliga la banca a tenere una somma a disposizione del cliente.\n"
)
# The same Concept as BANKING (same first sentence), reworded after it: a revised edition.
REVISED_BANKING = (
    b"# Contratti bancari\n\n"
    b"Il deposito bancario e un contratto reale. Il depositante puo chiedere la restituzione.\n"
)


@pytest.fixture
def chapter(client, auth_headers):
    headers = auth_headers("chapters-owner@example.com")
    course = client.post(
        "/api/v1/courses",
        json={"title": "Dottore Commercialista", "language": "it"},
        headers=headers,
    ).json()
    chapter = client.post(
        f"/api/v1/courses/{course['id']}/chapters",
        json={"title": "Diritto bancario"},
        headers=headers,
    ).json()
    return headers, course["id"], chapter["id"]


def upload(client, headers, course_id, data, name="banca.md", chapter_id=None):
    response = client.post(
        f"/api/v1/courses/{course_id}/documents",
        files={"file": (name, data, "application/octet-stream")},
        data={"chapter_id": chapter_id} if chapter_id else None,
        headers=headers,
    )
    assert response.status_code == 202, response.text
    return response.json()


def generate(client, headers, course_id, **body):
    response = client.post(
        f"/api/v1/courses/{course_id}/curriculum-proposals", json=body, headers=headers
    )
    if response.status_code != 202:
        return response, None
    proposal = client.get(f"/api/v1/curriculum-proposals/{response.json()['id']}", headers=headers)
    return response, proposal.json()


def apply_topics(client, headers, proposal):
    """Accepts a Chapter proposal unchanged."""
    body = {
        "topics": [
            {
                "title": t["title"],
                "existing_topic_id": t["existing_topic_id"],
                "concepts": [
                    {
                        "title": c["title"],
                        "existing_concept_id": c["existing_concept_id"],
                        "source_chunk_ids": [s["chunk_id"] for s in c["sources"]],
                    }
                    for c in t["concepts"]
                ],
            }
            for t in proposal["topics"]
        ]
    }
    return client.post(
        f"/api/v1/curriculum-proposals/{proposal['id']}/apply", json=body, headers=headers
    )


def chapter_tree(client, headers, course_id, chapter_id):
    outline = client.get(f"/api/v1/courses/{course_id}/outline", headers=headers).json()
    [found] = [c for c in outline if c["id"] == chapter_id]
    return found["topics"]


def document(client, headers, document_id):
    return client.get(f"/api/v1/documents/{document_id}", headers=headers).json()


# --- Filing material under Chapters ---


def test_material_is_filed_under_a_chapter_and_listed_by_it(client, chapter):
    headers, course_id, chapter_id = chapter
    filed = upload(client, headers, course_id, BANKING, chapter_id=chapter_id)
    loose = upload(client, headers, course_id, MORE_BANKING, name="altro.md")

    assert filed["chapter_id"] == chapter_id
    assert filed["analyzed_at"] is None
    assert loose["chapter_id"] is None
    listed = client.get(
        f"/api/v1/courses/{course_id}/documents",
        params={"chapter_id": chapter_id},
        headers=headers,
    ).json()
    assert [d["id"] for d in listed] == [filed["id"]]


def test_material_cannot_be_filed_under_another_courses_chapter(client, chapter, auth_headers):
    _headers, _course_id, chapter_id = chapter
    stranger = auth_headers("stranger@example.com")
    theirs = client.post("/api/v1/courses", json={"title": "X"}, headers=stranger).json()

    response = client.post(
        f"/api/v1/courses/{theirs['id']}/documents",
        files={"file": ("n.txt", b"Notes.", "text/plain")},
        data={"chapter_id": chapter_id},
        headers=stranger,
    )
    assert response.status_code == 404
    assert client.get(f"/api/v1/courses/{theirs['id']}/documents", headers=stranger).json() == []

    their_doc = upload(client, stranger, theirs["id"], b"Notes.", name="n.txt")
    moved = client.patch(
        f"/api/v1/documents/{their_doc['id']}", json={"chapter_id": chapter_id}, headers=stranger
    )
    assert moved.status_code == 404


def test_moving_material_to_another_chapter_marks_it_for_analysis_again(client, chapter):
    headers, course_id, chapter_id = chapter
    doc = upload(client, headers, course_id, BANKING, chapter_id=chapter_id)
    _, proposal = generate(client, headers, course_id, chapter_id=chapter_id)
    apply_topics(client, headers, proposal)
    assert document(client, headers, doc["id"])["analyzed_at"] is not None

    other = client.post(
        f"/api/v1/courses/{course_id}/chapters", json={"title": "Bilancio"}, headers=headers
    ).json()
    moved = client.patch(
        f"/api/v1/documents/{doc['id']}", json={"chapter_id": other["id"]}, headers=headers
    ).json()
    assert moved["chapter_id"] == other["id"]
    assert moved["analyzed_at"] is None

    unassigned = client.patch(
        f"/api/v1/documents/{doc['id']}", json={"chapter_id": None}, headers=headers
    ).json()
    assert unassigned["chapter_id"] is None


def test_deleting_a_chapter_keeps_its_material_unassigned_and_unanalyzed(client, chapter):
    headers, course_id, chapter_id = chapter
    doc = upload(client, headers, course_id, BANKING, chapter_id=chapter_id)
    _, proposal = generate(client, headers, course_id, chapter_id=chapter_id)
    apply_topics(client, headers, proposal)

    client.delete(f"/api/v1/chapters/{chapter_id}", headers=headers)

    kept = document(client, headers, doc["id"])
    assert (kept["chapter_id"], kept["analyzed_at"]) == (None, None)


# --- Chapter proposals ---


def test_chapter_proposal_uses_only_that_chapters_material(client, chapter, ai_provider):
    headers, course_id, chapter_id = chapter
    upload(client, headers, course_id, BANKING, chapter_id=chapter_id)
    other = client.post(
        f"/api/v1/courses/{course_id}/chapters", json={"title": "Bilancio"}, headers=headers
    ).json()
    upload(client, headers, course_id, b"Lo stato patrimoniale.", "bilancio.txt", other["id"])
    upload(client, headers, course_id, b"Materiale non assegnato.", "sciolto.txt")

    response, proposal = generate(client, headers, course_id, chapter_id=chapter_id)

    assert response.status_code == 202
    assert proposal["status"] == "READY"
    assert proposal["chapter_id"] == chapter_id
    assert proposal["chapters"] is None
    assert [t["title"] for t in proposal["topics"]] == ["Contratti bancari"]
    assert proposal["prompt_version"] == "mock_chapter_curriculum_v1"
    [sent] = ai_provider.chapter_requests
    assert sent.chapter_title == "Diritto bancario"
    assert {p.document_name for p in sent.passages} == {"banca.md"}
    assert sent.existing_topics == []


def test_applying_a_chapter_proposal_fills_that_chapter_and_marks_material_analyzed(
    client, chapter
):
    headers, course_id, chapter_id = chapter
    doc = upload(client, headers, course_id, BANKING, chapter_id=chapter_id)
    _, proposal = generate(client, headers, course_id, chapter_id=chapter_id)
    assert proposal["document_ids"] == [doc["id"]]

    response = apply_topics(client, headers, proposal)

    assert response.status_code == 201, response.text
    [topic] = chapter_tree(client, headers, course_id, chapter_id)
    assert topic["title"] == "Contratti bancari"
    [concept] = topic["concepts"]
    assert concept["study_state"] == "NOT_STUDIED"
    assert document(client, headers, doc["id"])["analyzed_at"] is not None

    again, _ = generate(client, headers, course_id, chapter_id=chapter_id)
    assert again.status_code == 409
    assert again.json()["details"]["reason"] == "no_new_material"


def test_new_material_is_merged_into_the_existing_chapter(client, chapter, ai_provider):
    headers, course_id, chapter_id = chapter
    upload(client, headers, course_id, BANKING, chapter_id=chapter_id)
    _, first = generate(client, headers, course_id, chapter_id=chapter_id)
    apply_topics(client, headers, first)
    [existing_topic] = chapter_tree(client, headers, course_id, chapter_id)

    upload(client, headers, course_id, MORE_BANKING, "credito.md", chapter_id)
    _, second = generate(client, headers, course_id, chapter_id=chapter_id)

    # Only the new document was sent, alongside the structure the Chapter already has.
    request = ai_provider.chapter_requests[-1]
    assert {p.document_name for p in request.passages} == {"credito.md"}
    assert [t.title for t in request.existing_topics] == ["Contratti bancari"]
    [proposed] = second["topics"]
    assert proposed["existing_topic_id"] == existing_topic["id"]

    apply_topics(client, headers, second)

    [topic] = chapter_tree(client, headers, course_id, chapter_id)
    assert topic["id"] == existing_topic["id"]
    assert [c["order"] for c in topic["concepts"]] == [0, 1]
    assert "apertura di credito" in topic["concepts"][1]["title"].lower()


def test_revised_material_relinks_existing_concepts_instead_of_duplicating(client, chapter):
    headers, course_id, chapter_id = chapter
    old = upload(client, headers, course_id, BANKING, chapter_id=chapter_id)
    _, first = generate(client, headers, course_id, chapter_id=chapter_id)
    apply_topics(client, headers, first)
    [[concept]] = [t["concepts"] for t in chapter_tree(client, headers, course_id, chapter_id)]

    # The user replaces the document with a revised edition: delete, then upload the new one.
    client.delete(f"/api/v1/documents/{old['id']}", headers=headers)
    [[orphan]] = [t["concepts"] for t in chapter_tree(client, headers, course_id, chapter_id)]
    assert orphan["needs_source_review"] is True
    assert client.get(f"/api/v1/concepts/{concept['id']}/sources", headers=headers).json() == []

    upload(client, headers, course_id, REVISED_BANKING, "banca-v2.md", chapter_id)
    _, second = generate(client, headers, course_id, chapter_id=chapter_id)
    [proposed] = second["topics"][0]["concepts"]
    assert proposed["existing_concept_id"] == concept["id"]
    apply_topics(client, headers, second)

    [[relinked]] = [t["concepts"] for t in chapter_tree(client, headers, course_id, chapter_id)]
    assert relinked["id"] == concept["id"]
    assert relinked["needs_source_review"] is False
    [source] = client.get(f"/api/v1/concepts/{concept['id']}/sources", headers=headers).json()
    assert "restituzione" in source["text"]


def test_concept_keeps_its_flag_off_while_another_source_remains(client, chapter):
    headers, course_id, chapter_id = chapter
    first = upload(client, headers, course_id, BANKING, chapter_id=chapter_id)
    upload(client, headers, course_id, REVISED_BANKING, "banca-v2.md", chapter_id)
    _, proposal = generate(client, headers, course_id, chapter_id=chapter_id)
    # Both documents teach the same Concept: link both passages to one Concept.
    chunk_ids = [
        s["chunk_id"] for t in proposal["topics"] for c in t["concepts"] for s in c["sources"]
    ]
    body = {
        "topics": [
            {"title": "T", "concepts": [{"title": "Deposito", "source_chunk_ids": chunk_ids}]}
        ]
    }
    client.post(f"/api/v1/curriculum-proposals/{proposal['id']}/apply", json=body, headers=headers)

    client.delete(f"/api/v1/documents/{first['id']}", headers=headers)

    [[concept]] = [t["concepts"] for t in chapter_tree(client, headers, course_id, chapter_id)]
    assert concept["needs_source_review"] is False


def test_user_can_dismiss_the_source_review_flag(client, chapter):
    headers, course_id, chapter_id = chapter
    doc = upload(client, headers, course_id, BANKING, chapter_id=chapter_id)
    _, proposal = generate(client, headers, course_id, chapter_id=chapter_id)
    apply_topics(client, headers, proposal)
    client.delete(f"/api/v1/documents/{doc['id']}", headers=headers)
    [[concept]] = [t["concepts"] for t in chapter_tree(client, headers, course_id, chapter_id)]

    kept = client.patch(
        f"/api/v1/concepts/{concept['id']}", json={"needs_source_review": False}, headers=headers
    )
    assert kept.json()["needs_source_review"] is False


# --- Scope and validation ---


def test_explicit_documents_must_be_in_the_chapter(client, chapter):
    headers, course_id, chapter_id = chapter
    upload(client, headers, course_id, BANKING, chapter_id=chapter_id)
    loose = upload(client, headers, course_id, MORE_BANKING, name="altro.md")
    response, _ = generate(
        client, headers, course_id, chapter_id=chapter_id, document_ids=[loose["id"]]
    )
    assert response.status_code == 409
    assert response.json()["details"] == {
        "reason": "documents_not_in_chapter",
        "document_ids": [loose["id"]],
    }


def test_explicit_documents_can_be_reanalyzed(client, chapter):
    headers, course_id, chapter_id = chapter
    doc = upload(client, headers, course_id, BANKING, chapter_id=chapter_id)
    _, proposal = generate(client, headers, course_id, chapter_id=chapter_id)
    apply_topics(client, headers, proposal)
    response, again = generate(
        client, headers, course_id, chapter_id=chapter_id, document_ids=[doc["id"]]
    )
    assert response.status_code == 202
    assert again["status"] == "READY"


def test_chapter_with_no_material_is_409(client, chapter):
    headers, course_id, chapter_id = chapter
    response, _ = generate(client, headers, course_id, chapter_id=chapter_id)
    assert response.status_code == 409
    assert response.json()["details"]["reason"] == "no_source_material"


def test_another_courses_chapter_is_404(client, chapter, auth_headers):
    _headers, _course_id, chapter_id = chapter
    stranger = auth_headers("stranger@example.com")
    theirs = client.post("/api/v1/courses", json={"title": "X"}, headers=stranger).json()
    upload(client, stranger, theirs["id"], b"Their notes.", name="n.txt")
    response, _ = generate(client, stranger, theirs["id"], chapter_id=chapter_id)
    assert response.status_code == 404


def test_course_proposal_ignores_material_filed_under_chapters(client, chapter, ai_provider):
    headers, course_id, chapter_id = chapter
    upload(client, headers, course_id, BANKING, chapter_id=chapter_id)
    upload(client, headers, course_id, MORE_BANKING, name="sciolto.md")

    _, proposal = generate(client, headers, course_id)

    assert proposal["chapter_id"] is None
    assert proposal["topics"] is None
    [sent] = ai_provider.curriculum_requests
    assert {p.document_name for p in sent.passages} == {"sciolto.md"}


@pytest.mark.parametrize(
    ("scope", "body"),
    [
        ("chapter", {"chapters": [{"title": "C"}]}),
        ("course", {"topics": [{"title": "T"}]}),
        (
            "course",
            {
                "chapters": [
                    {
                        "title": "C",
                        "topics": [
                            {
                                "title": "T",
                                "existing_topic_id": "00000000-0000-0000-0000-000000000000",
                            }
                        ],
                    }
                ]
            },
        ),
        ("chapter", {"topics": [{"title": "T"}], "chapters": [{"title": "C"}]}),
    ],
)
def test_apply_body_must_match_the_proposal(client, chapter, scope, body):
    headers, course_id, chapter_id = chapter
    upload(client, headers, course_id, BANKING, chapter_id=chapter_id)
    upload(client, headers, course_id, MORE_BANKING, name="sciolto.md")
    kwargs = {"chapter_id": chapter_id} if scope == "chapter" else {}
    _, proposal = generate(client, headers, course_id, **kwargs)

    response = client.post(
        f"/api/v1/curriculum-proposals/{proposal['id']}/apply", json=body, headers=headers
    )
    assert response.status_code == 422
    after = client.get(f"/api/v1/curriculum-proposals/{proposal['id']}", headers=headers).json()
    assert after["status"] == "READY"


def test_existing_ids_must_belong_to_the_proposals_chapter(client, chapter, db_session):
    headers, course_id, chapter_id = chapter
    other = client.post(
        f"/api/v1/courses/{course_id}/chapters", json={"title": "Bilancio"}, headers=headers
    ).json()
    other_topic = client.post(
        f"/api/v1/chapters/{other['id']}/topics", json={"title": "Attivo"}, headers=headers
    ).json()
    other_concept = client.post(
        f"/api/v1/topics/{other_topic['id']}/concepts", json={"title": "Cassa"}, headers=headers
    ).json()
    upload(client, headers, course_id, BANKING, chapter_id=chapter_id)
    _, proposal = generate(client, headers, course_id, chapter_id=chapter_id)
    chunk = proposal["topics"][0]["concepts"][0]["sources"][0]["chunk_id"]
    url = f"/api/v1/curriculum-proposals/{proposal['id']}/apply"

    wrong_topic = {"topics": [{"title": "T", "existing_topic_id": other_topic["id"]}]}
    assert client.post(url, json=wrong_topic, headers=headers).status_code == 404
    wrong_concept = {"topics": [{"title": "T", "concepts": [
        {"title": "C", "existing_concept_id": other_concept["id"], "source_chunk_ids": [chunk]}
    ]}]}  # fmt: skip
    assert client.post(url, json=wrong_concept, headers=headers).status_code == 404

    # Nothing was linked to the other Chapter's Concept, and the proposal is still open.
    assert db_session.scalars(select(ConceptSource)).all() == []
    assert client.get(url.removesuffix("/apply"), headers=headers).json()["status"] == "READY"
