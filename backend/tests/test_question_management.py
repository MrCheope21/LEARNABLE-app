"""Managing a Course's questions: edit/delete one wording, bulk delete/pause/resume/move."""

import uuid

import pytest
from sqlalchemy import select
from test_review import FULL, answer, card, concept, item, make_due, memory, start

from app.models.course import Concept
from app.models.curriculum import ConceptSource
from app.models.learning import LearningItemSource


@pytest.fixture
def course(client, auth_headers):
    headers = auth_headers("organizer@example.com")
    course = client.post(
        "/api/v1/courses", json={"title": "Diritto", "language": "it"}, headers=headers
    ).json()
    chapter = client.post(
        f"/api/v1/courses/{course['id']}/chapters", json={"title": "Contratti"}, headers=headers
    ).json()
    topic_a = client.post(
        f"/api/v1/chapters/{chapter['id']}/topics", json={"title": "Prestiti"}, headers=headers
    ).json()
    topic_b = client.post(
        f"/api/v1/chapters/{chapter['id']}/topics", json={"title": "Garanzie"}, headers=headers
    ).json()
    return headers, course["id"], topic_a["id"], topic_b["id"]


def bulk(client, headers, course_id, **body):
    return client.post(
        f"/api/v1/courses/{course_id}/learning-items/bulk", json=body, headers=headers
    )


def items_of(client, headers, concept_id):
    return client.get(f"/api/v1/concepts/{concept_id}/learning-items", headers=headers).json()


def test_lists_every_item_of_the_course_in_order(client, course):
    headers, course_id, topic_a, topic_b = course
    first = concept(client, headers, topic_a, title="Mutuo")
    second = concept(client, headers, topic_b, title="Fideiussione")
    item(client, headers, first["id"], title="Uno")
    item(client, headers, second["id"], title="Due")
    listed = client.get(f"/api/v1/courses/{course_id}/learning-items", headers=headers).json()
    assert [i["title"] for i in listed] == ["Uno", "Due"]
    assert all(i["questions"] for i in listed)


def test_reword_and_delete_one_question(client, course, db_session):
    headers, _, topic_a, _ = course
    c = concept(client, headers, topic_a)
    it = item(client, headers, c["id"])
    first, second = it["questions"]

    reworded = client.patch(
        f"/api/v1/questions/{first['id']}", json={"text": "Definisci il mutuo."}, headers=headers
    )
    assert reworded.status_code == 200
    assert reworded.json()["text"] == "Definisci il mutuo."

    assert client.delete(f"/api/v1/questions/{second['id']}", headers=headers).status_code == 204
    last = client.delete(f"/api/v1/questions/{first['id']}", headers=headers)
    assert last.status_code == 409
    assert last.json()["details"]["reason"] == "last_question"
    [remaining] = items_of(client, headers, c["id"])[0]["questions"]
    assert remaining["text"] == "Definisci il mutuo."


def test_bulk_delete_removes_items_and_emptied_concepts(client, course, db_session):
    headers, course_id, topic_a, _ = course
    lonely = concept(client, headers, topic_a, title="Solo")
    shared = concept(client, headers, topic_a, title="Insieme")
    a = item(client, headers, lonely["id"], title="A")
    b = item(client, headers, shared["id"], title="B")
    item(client, headers, shared["id"], title="C")

    result = bulk(client, headers, course_id, item_ids=[a["id"], b["id"]], action="delete")
    assert result.json() == {"affected": 2, "created_concepts": 0, "deleted_concepts": 1}
    assert client.get(f"/api/v1/concepts/{lonely['id']}", headers=headers).status_code == 404
    assert [i["title"] for i in items_of(client, headers, shared["id"])] == ["C"]


def test_bulk_delete_can_keep_empty_concepts(client, course):
    headers, course_id, topic_a, _ = course
    c = concept(client, headers, topic_a)
    it = item(client, headers, c["id"])
    bulk(
        client,
        headers,
        course_id,
        item_ids=[it["id"]],
        action="delete",
        delete_emptied_concepts=False,
    )
    assert client.get(f"/api/v1/concepts/{c['id']}", headers=headers).status_code == 200


def test_bulk_pause_and_resume_keep_the_schedule(client, course, db_session):
    headers, course_id, topic_a, _ = course
    c = concept(client, headers, topic_a)
    it = item(client, headers, c["id"])
    session = start(client, headers, course_id).json()
    while not card(client, headers, session["id"])["done"]:
        answer(client, headers, session["id"], FULL)
    make_due(db_session, it["id"])

    bulk(client, headers, course_id, item_ids=[it["id"]], action="pause")
    assert memory(db_session, it["id"]).paused_at is not None
    assert start(client, headers, course_id, intent="SCHEDULED_REVIEW").status_code == 409
    bulk(client, headers, course_id, item_ids=[it["id"]], action="resume")
    assert memory(db_session, it["id"]).paused_at is None
    assert start(client, headers, course_id, intent="SCHEDULED_REVIEW").status_code == 201


def test_move_into_a_concept_keeps_memory_and_sources(client, course, db_session):
    headers, course_id, topic_a, topic_b = course
    source = concept(client, headers, topic_a, title="Da")
    target = concept(client, headers, topic_b, title="A")
    moving = item(client, headers, source["id"], title="Sposta")
    item(client, headers, target["id"], title="Già qui")
    state_before = memory(db_session, moving["id"])
    level_before = state_before.level
    chunk = _add_item_source(db_session, moving["id"])

    result = bulk(
        client,
        headers,
        course_id,
        item_ids=[moving["id"]],
        action="move",
        target_concept_id=target["id"],
    ).json()
    assert result == {"affected": 1, "created_concepts": 0, "deleted_concepts": 1}
    moved = next(i for i in items_of(client, headers, target["id"]) if i["title"] == "Sposta")
    assert (moved["topic_id"], moved["concept_id"], moved["order"]) == (topic_b, target["id"], 1)
    assert memory(db_session, moving["id"]).level == level_before
    db_session.expire_all()
    linked = db_session.scalars(
        select(ConceptSource.chunk_id).where(ConceptSource.concept_id == uuid.UUID(target["id"]))
    ).all()
    assert chunk in linked


def test_move_to_a_topic_moves_whole_concepts_and_splits_partial_ones(client, course, db_session):
    headers, course_id, topic_a, topic_b = course
    whole = concept(client, headers, topic_a, title="Domanda intera")
    partial = concept(client, headers, topic_a, title="Due domande")
    w = item(client, headers, whole["id"], title="W")
    p1 = item(client, headers, partial["id"], title="P1")
    item(client, headers, partial["id"], title="P2")

    result = bulk(
        client,
        headers,
        course_id,
        item_ids=[w["id"], p1["id"]],
        action="move",
        target_topic_id=topic_b,
    ).json()
    assert result == {"affected": 2, "created_concepts": 1, "deleted_concepts": 0}

    moved_whole = client.get(f"/api/v1/concepts/{whole['id']}", headers=headers).json()
    assert moved_whole["topic_id"] == topic_b
    db_session.expire_all()
    split = db_session.scalar(
        select(Concept).where(
            Concept.topic_id == uuid.UUID(topic_b), Concept.title == "Due domande"
        )
    )
    assert split is not None
    assert split.study_state.value == "ACTIVE"
    assert [i["title"] for i in items_of(client, headers, str(split.id))] == ["P1"]
    assert [i["title"] for i in items_of(client, headers, partial["id"])] == ["P2"]


def test_bulk_is_all_or_nothing_and_course_scoped(client, course, auth_headers):
    headers, course_id, topic_a, _ = course
    mine = item(client, headers, concept(client, headers, topic_a)["id"])

    other = auth_headers("someone-else@example.com")
    their_course = client.post("/api/v1/courses", json={"title": "X"}, headers=other).json()
    chapter = client.post(
        f"/api/v1/courses/{their_course['id']}/chapters", json={"title": "C"}, headers=other
    ).json()
    topic = client.post(
        f"/api/v1/chapters/{chapter['id']}/topics", json={"title": "T"}, headers=other
    ).json()
    theirs = item(client, other, concept(client, other, topic["id"])["id"])

    # Their item in my request: 404, and my item isn't deleted either.
    mixed = bulk(client, headers, course_id, item_ids=[mine["id"], theirs["id"]], action="delete")
    assert mixed.status_code == 404
    assert client.get(f"/api/v1/learning-items/{mine['id']}", headers=headers).status_code == 200
    # A destination in their course: 404.
    elsewhere = bulk(
        client,
        headers,
        course_id,
        item_ids=[mine["id"]],
        action="move",
        target_topic_id=topic["id"],
    )
    assert elsewhere.status_code == 404
    # My course's endpoint used by them: 404; their questions can't be edited by me.
    assert bulk(client, other, course_id, item_ids=[mine["id"]], action="pause").status_code == 404
    question = theirs["questions"][0]["id"]
    assert (
        client.patch(f"/api/v1/questions/{question}", json={"text": "x"}, headers=headers)
    ).status_code == 404
    assert client.delete(f"/api/v1/questions/{question}", headers=headers).status_code == 404


def test_move_needs_exactly_one_destination(client, course):
    headers, course_id, topic_a, topic_b = course
    c = concept(client, headers, topic_a)
    it = item(client, headers, c["id"])
    neither = bulk(client, headers, course_id, item_ids=[it["id"]], action="move")
    assert neither.status_code == 422
    assert neither.json()["details"]["reason"] == "move_target"
    both = bulk(
        client,
        headers,
        course_id,
        item_ids=[it["id"]],
        action="move",
        target_topic_id=topic_b,
        target_concept_id=c["id"],
    )
    assert both.status_code == 422


def _add_item_source(db_session, item_id):
    """A passage for the item (tests create items by hand, without material)."""
    from app.models.document import Document, DocumentChunk
    from app.models.enums import DocumentKind, DocumentStatus
    from app.models.learning import LearningItem

    it = db_session.get(LearningItem, uuid.UUID(item_id))
    document = Document(
        course_id=it.course_id,
        filename="a.md",
        mime_type="text/markdown",
        kind=DocumentKind.MARKDOWN,
        size_bytes=1,
        sha256=uuid.uuid4().hex * 2,
        storage_key=f"k/{uuid.uuid4()}",
        status=DocumentStatus.READY,
    )
    db_session.add(document)
    db_session.flush()
    chunk = DocumentChunk(
        document_id=document.id,
        course_id=it.course_id,
        position=0,
        paragraph_start=0,
        paragraph_end=0,
        text="Il mutuo.",
    )
    db_session.add(chunk)
    db_session.flush()
    db_session.add(
        LearningItemSource(learning_item_id=it.id, chunk_id=chunk.id, course_id=it.course_id)
    )
    db_session.commit()
    return chunk.id
