"""The marketplace: a sales page, publishing, access (not a copy), read-only content kept in sync
with the author, and the buyer's own study and priorities."""

import pytest
from test_drawings import REFERENCE, upload
from test_question_banks import _outline
from test_review import concept, item

API = "/api/v1"
INFO = {
    "title": "Diritto commerciale: l'imprenditore",
    "subtitle": "Tutte le domande dell'orale, con risposte modello",
    "description": "Domande e risposte sull'imprenditore (artt. 2082 ss. c.c.).",
    "outcomes": ["Definire l'imprenditore", "Distinguere piccolo imprenditore e agricolo"],
    "audience": "Candidati all'esame di abilitazione da commercialista",
    "level": "intermediate",
    "category": "law",
    "tags": ["diritto", "esame"],
}
PUBLISH = {**INFO, "rights_confirmed": True}


@pytest.fixture
def author(client, auth_headers):
    """An author's course: one chapter, one topic, two concepts with one question each."""
    headers = auth_headers("author@example.com")
    client.patch(f"{API}/auth/me", json={"display_name": "Prof. Rossi"}, headers=headers)
    course = client.post(
        f"{API}/courses", json={"title": "Commerciale", "language": "it"}, headers=headers
    ).json()
    chapter = client.post(
        f"{API}/courses/{course['id']}/chapters", json={"title": "L'imprenditore"}, headers=headers
    ).json()
    topic = client.post(
        f"{API}/chapters/{chapter['id']}/topics", json={"title": "Nozione"}, headers=headers
    ).json()
    first = concept(client, headers, topic["id"], title="Imprenditore", active=False)
    second = concept(client, headers, topic["id"], title="Piccolo imprenditore", active=False)
    items = [
        item(client, headers, first["id"], title="Chi è imprenditore", priority=1),
        item(client, headers, second["id"], title="Piccolo imprenditore", priority=3),
    ]
    return {"headers": headers, "course": course, "topic": topic, "items": items}


def publish(client, author, body=PUBLISH):
    return client.post(
        f"{API}/courses/{author['course']['id']}/marketplace/publish",
        json=body,
        headers=author["headers"],
    )


def acquire(client, headers, listing_id):
    return client.post(f"{API}/marketplace/listings/{listing_id}/acquire", headers=headers)


def items_of(client, headers, course_id):
    out = []
    for chapter in _outline(client, headers, course_id):
        for topic in chapter["topics"]:
            for c in topic["concepts"]:
                out += client.get(
                    f"{API}/concepts/{c['id']}/learning-items", headers=headers
                ).json()
    return out


@pytest.fixture
def bought(client, auth_headers, author):
    listing = publish(client, author).json()
    buyer = auth_headers("buyer@example.com")
    course_id = acquire(client, buyer, listing["id"]).json()["course_id"]
    return {"listing": listing, "buyer": buyer, "course_id": course_id}


# --- Sales page and browsing ---


def test_a_sales_page_is_a_private_draft_until_published(client, auth_headers, author):
    saved = client.put(
        f"{API}/courses/{author['course']['id']}/marketplace/info",
        json=INFO,
        headers=author["headers"],
    )
    assert saved.status_code == 200, saved.text
    draft = saved.json()
    assert (draft["status"], draft["version"], draft["published_at"]) == ("DRAFT", 0, None)
    assert draft["outcomes"] == INFO["outcomes"]

    stranger = auth_headers("stranger@example.com")
    assert client.get(f"{API}/marketplace/listings", headers=stranger).json() == []
    assert (
        client.get(f"{API}/marketplace/listings/{draft['id']}", headers=stranger).status_code == 404
    )
    assert acquire(client, stranger, draft["id"]).status_code == 404

    published = publish(client, author).json()
    assert (published["id"], published["status"], published["version"]) == (
        draft["id"],
        "PUBLISHED",
        1,
    )


def test_publishing_needs_the_rights_confirmation_a_description_and_a_category(client, author):
    for missing in ("rights_confirmed", "description", "category"):
        body = {k: v for k, v in PUBLISH.items() if k != missing}
        assert publish(client, author, body).status_code == 422
    assert publish(client, author, {**PUBLISH, "category": "astrology"}).status_code == 422


def test_before_access_a_listing_shows_its_sales_page_and_size_only(client, auth_headers, author):
    listing = publish(client, author).json()
    visitor = auth_headers("visitor@example.com")
    response = client.get(f"{API}/marketplace/listings/{listing['id']}", headers=visitor)
    detail = response.json()
    assert detail["author"] == "Prof. Rossi"
    assert (detail["subtitle"], detail["audience"], detail["level"]) == (
        INFO["subtitle"],
        INFO["audience"],
        "intermediate",
    )
    assert detail["chapters"] == [{"title": "L'imprenditore", "questions": 2}]
    assert (detail["item_count"], detail["chapter_count"]) == (2, 1)
    assert (detail["has_access"], detail["course_id"], detail["is_mine"]) == (False, None, False)
    # No question, answer, concept or email anywhere in it.
    for secret in ("Che cos'e", "Consegna di denaro", "Piccolo imprenditore", "author@example.com"):
        assert secret not in response.text


def test_browsing_filters_and_sorts(client, auth_headers, author):
    listing = publish(client, author).json()
    visitor = auth_headers("visitor@example.com")

    def found(**params):
        rows = client.get(f"{API}/marketplace/listings", params=params, headers=visitor).json()
        return [row["id"] for row in rows]

    assert found() == [listing["id"]]
    assert found(category="law", level="intermediate", language="it", size="small") == [
        listing["id"]
    ]
    assert found(q="IMPRENDITORE") == [listing["id"]]
    for miss in (
        {"category": "medicine_health"},
        {"level": "beginner"},
        {"size": "large"},
        {"q": "chimica"},
    ):
        assert found(**miss) == []
    for sort in ("popular", "newest", "largest"):
        assert found(sort=sort) == [listing["id"]]
    assert (
        client.get(
            f"{API}/marketplace/listings", params={"category": "x"}, headers=visitor
        ).status_code
        == 422
    )


# --- Access ---


def test_access_puts_the_course_in_the_buyers_courses_and_dashboard(client, author, bought):
    buyer, course_id = bought["buyer"], bought["course_id"]
    course = client.get(f"{API}/courses/{course_id}", headers=buyer).json()
    assert course["title"] == INFO["title"]
    assert (course["marketplace_listing_id"], course["marketplace_version"]) == (
        bought["listing"]["id"],
        1,
    )
    cards = client.get(f"{API}/dashboard", headers=buyer).json()["courses"]
    assert [(c["id"], c["marketplace_author"]) for c in cards] == [(course_id, "Prof. Rossi")]
    origin = client.get(f"{API}/courses/{course_id}/marketplace", headers=buyer).json()
    assert origin == {
        "listing": None,
        "origin": {"listing_id": bought["listing"]["id"], "author": "Prof. Rossi", "version": 1},
    }
    items = items_of(client, buyer, course_id)
    assert [(i["title"], i["priority"], i["origin_priority"]) for i in items] == [
        ("Chi è imprenditore", 1, 1),
        ("Piccolo imprenditore", 3, 3),
    ]
    # Nothing to download: the author's documents never come with it.
    assert client.get(f"{API}/courses/{course_id}/documents", headers=buyer).json() == []
    # The author's own course is untouched and still theirs only.
    assert client.get(f"{API}/courses/{author['course']['id']}", headers=buyer).status_code == 404
    detail = client.get(
        f"{API}/marketplace/listings/{bought['listing']['id']}", headers=buyer
    ).json()
    assert (detail["has_access"], detail["course_id"], detail["acquisition_count"]) == (
        True,
        course_id,
        1,
    )


def test_access_is_once_and_for_good(client, author, bought):
    buyer, listing_id = bought["buyer"], bought["listing"]["id"]
    again = acquire(client, buyer, listing_id)
    assert again.status_code == 409
    assert again.json()["details"] == {
        "reason": "already_acquired",
        "course_id": bought["course_id"],
    }

    assert client.delete(f"{API}/courses/{bought['course_id']}", headers=buyer).status_code == 204
    # Unpublished meanwhile: whoever has access can still add it back, at no new count.
    client.post(f"{API}/marketplace/listings/{listing_id}/unpublish", headers=author["headers"])
    back = acquire(client, buyer, listing_id)
    assert back.status_code == 201, back.text
    detail = client.get(f"{API}/marketplace/listings/{listing_id}", headers=buyer).json()
    assert (detail["acquisition_count"], detail["course_id"]) == (1, back.json()["course_id"])


def test_unpublished_listings_are_hidden_from_new_people(client, auth_headers, author, bought):
    listing_id = bought["listing"]["id"]
    client.post(f"{API}/marketplace/listings/{listing_id}/unpublish", headers=author["headers"])
    newcomer = auth_headers("newcomer@example.com")
    assert client.get(f"{API}/marketplace/listings", headers=newcomer).json() == []
    assert acquire(client, newcomer, listing_id).status_code == 404
    assert (
        client.get(f"{API}/courses/{bought['course_id']}", headers=bought["buyer"]).status_code
        == 200
    )


def test_authors_cant_acquire_their_own_course(client, author):
    listing = publish(client, author).json()
    refused = acquire(client, author["headers"], listing["id"])
    assert refused.status_code == 409
    assert refused.json()["details"]["reason"] == "own_listing"


# --- Read-only content, personal study ---


def _refused(response, db_session):
    assert response.status_code == 409, response.text
    assert response.json()["details"]["reason"] == "managed_course"
    # Every request shares this session in tests; a real request's session is closed (rolled
    # back) after the refusal.
    db_session.rollback()


def test_the_buyer_cant_change_the_content(client, bought, db_session):
    buyer, course_id = bought["buyer"], bought["course_id"]
    [chapter] = _outline(client, buyer, course_id)
    topic = chapter["topics"][0]
    concept_row = topic["concepts"][0]
    first = items_of(client, buyer, course_id)[0]
    question = first["questions"][0]

    _refused(
        client.patch(f"{API}/courses/{course_id}", json={"title": "Mio"}, headers=buyer), db_session
    )
    _refused(
        client.patch(f"{API}/chapters/{chapter['id']}", json={"title": "X"}, headers=buyer),
        db_session,
    )
    _refused(
        client.post(f"{API}/courses/{course_id}/chapters", json={"title": "X"}, headers=buyer),
        db_session,
    )
    _refused(
        client.post(f"{API}/topics/{topic['id']}/concepts", json={"title": "X"}, headers=buyer),
        db_session,
    )
    _refused(
        client.patch(f"{API}/concepts/{concept_row['id']}", json={"title": "X"}, headers=buyer),
        db_session,
    )
    _refused(client.delete(f"{API}/concepts/{concept_row['id']}", headers=buyer), db_session)
    _refused(
        client.patch(f"{API}/learning-items/{first['id']}", json={"title": "X"}, headers=buyer),
        db_session,
    )
    _refused(client.delete(f"{API}/learning-items/{first['id']}", headers=buyer), db_session)
    _refused(
        client.patch(f"{API}/questions/{question['id']}", json={"text": "X?"}, headers=buyer),
        db_session,
    )
    _refused(upload(client, buyer, first["id"]), db_session)
    _refused(
        client.post(
            f"{API}/courses/{course_id}/documents",
            files={"file": ("notes.txt", b"Appunti", "text/plain")},
            headers=buyer,
        ),
        db_session,
    )
    _refused(
        client.post(f"{API}/courses/{course_id}/marketplace/publish", json=PUBLISH, headers=buyer),
        db_session,
    )
    after = items_of(client, buyer, course_id)[0]
    assert (after["title"], after["questions"][0]["text"]) == (first["title"], question["text"])


def test_the_buyer_studies_with_their_own_state_and_priorities(client, bought):
    buyer, course_id = bought["buyer"], bought["course_id"]
    concept_id = _outline(client, buyer, course_id)[0]["topics"][0]["concepts"][0]["id"]
    assert client.post(f"{API}/concepts/{concept_id}/activate", headers=buyer).status_code == 200
    first = items_of(client, buyer, course_id)[0]
    assert (
        client.post(f"{API}/learning-items/{first['id']}/pause", headers=buyer).status_code == 200
    )
    changed = client.patch(
        f"{API}/learning-items/{first['id']}", json={"priority": 3}, headers=buyer
    )
    assert changed.status_code == 200, changed.text
    assert (changed.json()["priority"], changed.json()["origin_priority"]) == (3, 1)
    bulk = client.post(
        f"{API}/courses/{course_id}/learning-items/bulk",
        json={"item_ids": [first["id"]], "action": "set_priority", "priority": 2},
        headers=buyer,
    )
    assert bulk.status_code == 200, bulk.text


# --- Republishing keeps everyone in step ---


def test_republishing_updates_every_course_with_access_and_keeps_the_study(client, author, bought):
    buyer, course_id, headers = bought["buyer"], bought["course_id"], author["headers"]
    kept, dropped = author["items"]
    mine = {i["origin_priority"]: i for i in items_of(client, buyer, course_id)}
    # The buyer pauses one question and changes the other's priority.
    client.post(f"{API}/learning-items/{mine[1]['id']}/pause", headers=buyer)
    client.patch(f"{API}/learning-items/{mine[3]['id']}", json={"priority": 2}, headers=buyer)

    # The author rewords one question, raises its priority's number, removes the other item,
    # and adds a new concept with a question.
    client.patch(
        f"{API}/questions/{kept['questions'][0]['id']}",
        json={"text": "Chi è, per il c.c., imprenditore?"},
        headers=headers,
    )
    client.patch(f"{API}/learning-items/{kept['id']}", json={"priority": 2}, headers=headers)
    client.delete(f"{API}/learning-items/{dropped['id']}", headers=headers)
    added = concept(client, headers, author["topic"]["id"], title="Impresa agricola", active=False)
    item(client, headers, added["id"], title="Impresa agricola")
    republished = publish(client, author, {**PUBLISH, "title": "Commerciale v2"}).json()
    assert republished["version"] == 2

    course = client.get(f"{API}/courses/{course_id}", headers=buyer).json()
    assert (course["title"], course["marketplace_version"]) == ("Commerciale v2", 2)
    after = items_of(client, buyer, course_id)
    assert [i["title"] for i in after] == ["Chi è imprenditore", "Impresa agricola"]
    same = after[0]
    # The same row: still paused, the reworded question in place, the unchanged priority follows.
    assert same["id"] == mine[1]["id"]
    assert same["paused"] is True
    assert same["questions"][0]["text"] == "Chi è, per il c.c., imprenditore?"
    assert (same["priority"], same["origin_priority"]) == (2, 2)
    concepts = _outline(client, buyer, course_id)[0]["topics"][0]["concepts"]
    # The author removed the item only: its concept stays, empty, as on their side.
    assert [c["title"] for c in concepts] == [
        "Imprenditore",
        "Piccolo imprenditore",
        "Impresa agricola",
    ]


def test_the_buyers_own_priority_survives_a_republish(client, author, bought):
    buyer, course_id = bought["buyer"], bought["course_id"]
    target = next(i for i in items_of(client, buyer, course_id) if i["origin_priority"] == 3)
    client.patch(f"{API}/learning-items/{target['id']}", json={"priority": 1}, headers=buyer)
    client.patch(
        f"{API}/learning-items/{author['items'][1]['id']}",
        json={"priority": 2},
        headers=author["headers"],
    )
    publish(client, author)
    after = next(i for i in items_of(client, buyer, course_id) if i["id"] == target["id"])
    assert (after["priority"], after["origin_priority"]) == (1, 2)


def test_editing_the_sales_page_of_a_published_course_needs_no_new_version(client, author, bought):
    response = client.put(
        f"{API}/courses/{author['course']['id']}/marketplace/info",
        json={**INFO, "title": "Nuovo titolo", "subtitle": "Aggiornato"},
        headers=author["headers"],
    )
    assert response.status_code == 200, response.text
    saved = response.json()
    assert (saved["status"], saved["version"], saved["subtitle"]) == ("PUBLISHED", 1, "Aggiornato")
    course = client.get(f"{API}/courses/{bought['course_id']}", headers=bought["buyer"]).json()
    assert course["title"] == "Nuovo titolo"


def test_reference_drawings_reach_the_buyer_and_follow_the_author(client, auth_headers, author):
    drawn = author["items"][0]
    assert upload(client, author["headers"], drawn["id"]).status_code == 200
    listing = publish(client, author).json()
    buyer = auth_headers("buyer@example.com")
    course_id = acquire(client, buyer, listing["id"]).json()["course_id"]
    mine = items_of(client, buyer, course_id)[0]
    assert mine["answer_format"] == "DRAWING"
    image = client.get(f"{API}/learning-items/{mine['id']}/reference-drawing", headers=buyer)
    assert image.content == REFERENCE

    # The author turns it back into a text question: so does the buyer's copy.
    client.delete(
        f"{API}/learning-items/{drawn['id']}/reference-drawing", headers=author["headers"]
    )
    publish(client, author)
    assert items_of(client, buyer, course_id)[0]["answer_format"] == "TEXT"
    missing = client.get(f"{API}/learning-items/{mine['id']}/reference-drawing", headers=buyer)
    assert missing.status_code == 404


def test_courses_without_questions_cant_be_published(client, auth_headers):
    headers = auth_headers("empty@example.com")
    course = client.post(f"{API}/courses", json={"title": "Vuoto"}, headers=headers).json()
    refused = client.post(
        f"{API}/courses/{course['id']}/marketplace/publish", json=PUBLISH, headers=headers
    )
    assert refused.status_code == 422
