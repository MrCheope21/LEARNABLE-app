"""The MVP acceptance flow (docs/PROJECT_SPEC.md §102), end to end through the API.

One user, one real PDF, MockAIProvider standing in for the runtime model (spec §76). Each step
is labelled with its number in docs/PROJECT_STATUS.md §3.
"""

import uuid
from datetime import timedelta

from samples import make_pdf
from sqlalchemy import select

from app.db.types import utc_now
from app.models.learning import ReviewState

PAGES = [
    (
        "Il deposito bancario",
        "Il deposito bancario e il contratto con cui la banca acquista la proprieta del denaro "
        "depositato. Il depositante ha diritto alla restituzione della somma.",
    ),
    (
        "Il mutuo",
        "Il mutuo e il contratto con cui una parte consegna all'altra una quantita di denaro. "
        "Chi riceve si obbliga a restituire altrettanto.",
    ),
]


def test_mvp_acceptance_flow(client, auth_headers, db_session, ai_provider):
    owner = auth_headers("student@example.com")
    api = "/api/v1"

    # 1. Create Course
    course = client.post(
        f"{api}/courses", json={"title": "Dottore Commercialista", "language": "it"}, headers=owner
    ).json()
    course_id = course["id"]

    # 2. Create Chapters
    chapter = client.post(
        f"{api}/courses/{course_id}/chapters", json={"title": "Diritto bancario"}, headers=owner
    ).json()

    # 4-6. Import a PDF into the Chapter → text extracted → page/section-bounded chunks
    document = client.post(
        f"{api}/courses/{course_id}/documents",
        files={"file": ("banca.pdf", make_pdf(PAGES), "application/pdf")},
        data={"chapter_id": chapter["id"]},
        headers=owner,
    ).json()
    document = client.get(f"{api}/documents/{document['id']}", headers=owner).json()
    assert (document["status"], document["page_count"], document["chunk_count"]) == ("READY", 2, 2)

    # 7. Generate a curriculum proposal (3. Topics come from it)
    proposal = client.post(
        f"{api}/courses/{course_id}/curriculum-proposals",
        json={"chapter_id": chapter["id"]},
        headers=owner,
    ).json()
    proposal = client.get(f"{api}/curriculum-proposals/{proposal['id']}", headers=owner).json()
    assert proposal["status"] == "READY"
    assert [t["title"] for t in proposal["topics"]] == ["Il deposito bancario", "Il mutuo"]

    # 8. The user edits (renames a Topic) and accepts
    body = {
        "topics": [
            {
                "title": "Deposito" if t["title"] == "Il deposito bancario" else t["title"],
                "concepts": [
                    {"title": c["title"], "source_chunk_ids": [s["chunk_id"] for s in c["sources"]]}
                    for c in t["concepts"]
                ],
            }
            for t in proposal["topics"]
        ]
    }
    outline = client.post(
        f"{api}/curriculum-proposals/{proposal['id']}/apply", json=body, headers=owner
    ).json()

    # 9. Concepts exist, not activated
    topics = outline[0]["topics"]
    assert [t["title"] for t in topics] == ["Deposito", "Il mutuo"]
    concepts = [c for t in topics for c in t["concepts"]]
    assert all(c["study_state"] == "NOT_STUDIED" for c in concepts)

    # 10. The user activates one Concept → 11-12. its Learning Items and questions are generated
    deposit = concepts[0]
    client.post(f"{api}/concepts/{deposit['id']}/activate", headers=owner)
    [item] = client.get(f"{api}/concepts/{deposit['id']}/learning-items", headers=owner).json()
    assert item["in_training"] is True
    assert len(item["questions"]) == 2
    [source] = client.get(f"{api}/learning-items/{item['id']}/sources", headers=owner).json()
    assert source["page_number"] == 1  # traceable to the page

    # 13-14. The user starts a LEARN session and answers by text
    session = client.post(
        f"{api}/courses/{course_id}/review-sessions", json={"intent": "LEARN"}, headers=owner
    ).json()
    card = client.get(f"{api}/review-sessions/{session['id']}/next", headers=owner).json()["card"]
    assert card["learning_item_id"] == item["id"]
    assert card["introduction"]["sources"][0]["page_number"] == 1
    result = client.post(
        f"{api}/review-sessions/{session['id']}/answers",
        json={
            "question_formulation_id": card["question"]["id"],
            "text": " ".join(item["essential_points"]),
        },
        headers=owner,
    ).json()

    # 15-16. AI evaluates; feedback and the reference answer are shown
    assert result["evaluation"]["status"] == "COMPLETED"
    assert result["evaluation"]["feedback"]
    assert result["reference"]["sources"][0]["document_id"] == document["id"]
    assert result["reference"]["sources"][0]["document_name"] == "banca.pdf"

    # 17-18. The resolver and the SchedulingPolicy process it; the next review is stored
    assert result["final_outcome"] == "GOOD"
    assert (result["schedule"]["next_state"], result["schedule"]["next_level"]) == ("LEARNING", 1)
    state = db_session.scalar(
        select(ReviewState).where(ReviewState.learning_item_id == uuid.UUID(item["id"]))
    )
    assert state.due_at > utc_now() + timedelta(hours=3)

    # 19. Review history is stored
    [history] = client.get(f"{api}/learning-items/{item['id']}/reviews", headers=owner).json()
    assert (history["intent"], history["outcome"]) == ("LEARN", "GOOD")

    # 20-23. Mastery and progress update at Concept, Topic, Chapter and Course level
    progress = client.get(f"{api}/courses/{course_id}/progress", headers=owner).json()
    topic_progress = progress["chapters"][0]["topics"][0]
    concept_progress = topic_progress["concepts"][0]
    assert concept_progress["memory"]["mastery"] == 0.125
    assert topic_progress["memory"]["learning"] == 1
    assert progress["chapters"][0]["memory"]["items_trained"] == 1
    assert progress["curriculum"]["active"] == 1
    assert progress["memory"]["mastery"] == 0.125

    # 24. A second Course stays completely isolated
    other = auth_headers("other@example.com")
    theirs = client.post(f"{api}/courses", json={"title": "Altro"}, headers=other).json()
    assert client.get(f"{api}/courses/{course_id}/progress", headers=other).status_code == 404
    assert client.get(f"{api}/learning-items/{item['id']}", headers=other).status_code == 404
    empty = client.post(
        f"{api}/courses/{theirs['id']}/review-sessions",
        json={
            "intent": "PRACTICE",
            "selection_mode": "SELECTED",
            "learning_item_ids": [item["id"]],
        },
        headers=other,
    )
    assert empty.status_code == 409
    # Every AI request carried only this Course's material.
    sent = [p.text for r in ai_provider.chapter_requests for p in r.passages]
    sent += [p.text for r in ai_provider.learning_item_requests for p in r.passages]
    assert sent
    assert all("deposit" in text or "mutuo" in text for text in sent)
