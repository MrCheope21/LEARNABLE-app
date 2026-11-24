"""Multiple-choice questions: created by hand or imported, answered by picking options,
graded without AI."""

import pytest
from sqlalchemy import select
from test_marketplace import author as author
from test_question_banks import _upload
from test_review import concept, start
from test_review import course as course

from app.models.auth import AiUsage

API = "/api/v1"
OPTIONS = [
    {"text": "Il mutuante", "correct": False},
    {"text": "Il mutuatario", "correct": True},
    {"text": "La banca d'Italia", "correct": False},
]


def mc_item(client, headers, concept_id, options=OPTIONS):
    return client.post(
        f"{API}/concepts/{concept_id}/learning-items",
        json={
            "title": "Mutuo: chi restituisce",
            "questions": [{"question_type": "RECALL", "text": "Chi deve restituire il denaro?"}],
            "choices": options,
        },
        headers=headers,
    )


def card(client, headers, session_id):
    return client.get(f"{API}/review-sessions/{session_id}/next", headers=headers).json()["card"]


def pick(client, headers, session_id, card, positions):
    return client.post(
        f"{API}/review-sessions/{session_id}/answers",
        json={"question_formulation_id": card["question"]["id"], "choices": positions},
        headers=headers,
    )


def test_a_multiple_choice_item_is_graded_without_ai(client, course, db_session):
    headers, course_id, _, topic_id = course
    made = concept(client, headers, topic_id)
    item = mc_item(client, headers, made["id"])
    assert item.status_code == 201, item.text
    item = item.json()
    assert item["answer_format"] == "CHOICE"
    assert item["expected_knowledge"] == "✓ Il mutuatario"
    assert [c["correct"] for c in item["choices"]] == [False, True, False]

    session = start(client, headers, course_id).json()
    shown = card(client, headers, session["id"])
    assert shown["answer_format"] == "CHOICE"
    assert shown["choices"] == ["Il mutuante", "Il mutuatario", "La banca d'Italia"]
    assert shown["multiple"] is False

    wrong = pick(client, headers, session["id"], shown, [0]).json()
    assert wrong["evaluation"]["classification"] == "WRONG"
    assert wrong["evaluation"]["gap"] == "Risposta giusta: B) Il mutuatario"
    assert wrong["evaluation"]["ai_provider"] == "choice"
    assert wrong["final_outcome"] == "AGAIN"

    shown = card(client, headers, session["id"])
    right = pick(client, headers, session["id"], shown, [1]).json()
    assert right["evaluation"]["classification"] == "CORRECT"
    assert right["final_outcome"] == "GOOD"
    assert right["text"] == "B) Il mutuatario"
    # No AI allowance was used.
    assert db_session.scalar(select(AiUsage).where(AiUsage.kind == "evaluation")) is None


def test_several_correct_options_must_all_be_picked(client, course):
    headers, course_id, _, topic_id = course
    made = concept(client, headers, topic_id)
    mc_item(
        client,
        headers,
        made["id"],
        [
            {"text": "Consegna", "correct": True},
            {"text": "Restituzione", "correct": True},
            {"text": "Gratuità necessaria", "correct": False},
        ],
    )
    session = start(client, headers, course_id).json()
    shown = card(client, headers, session["id"])
    assert shown["multiple"] is True
    partial = pick(client, headers, session["id"], shown, [0]).json()
    assert partial["evaluation"]["classification"] == "PARTIALLY_CORRECT"
    assert partial["evaluation"]["missing_points"] == ["Restituzione"]
    assert partial["needs_repeat"] is False


@pytest.mark.parametrize(
    ("options", "message"),
    [
        ([{"text": "Solo una", "correct": True}], "2 to 8 options"),
        ([{"text": "A", "correct": False}, {"text": "B", "correct": False}], "at least one"),
        ([{"text": "Uguale", "correct": True}, {"text": "uguale", "correct": False}], "same text"),
    ],
)
def test_invalid_options_are_refused(client, course, options, message):
    headers, _, _, topic_id = course
    made = concept(client, headers, topic_id)
    refused = mc_item(client, headers, made["id"], options)
    assert refused.status_code == 422
    assert message in refused.json()["message"]


def test_wrong_answer_shapes_and_no_second_opinion(client, course):
    headers, course_id, _, topic_id = course
    made = concept(client, headers, topic_id)
    mc_item(client, headers, made["id"])
    session = start(client, headers, course_id).json()
    shown = card(client, headers, session["id"])
    assert pick(client, headers, session["id"], shown, []).status_code == 422
    assert pick(client, headers, session["id"], shown, [7]).status_code == 422
    answer = pick(client, headers, session["id"], shown, [0]).json()
    disputed = client.post(
        f"{API}/answers/{answer['answer_id']}/dispute",
        json={"argument": "Era giusta"},
        headers=headers,
    )
    assert disputed.status_code == 409


def test_editing_options_and_turning_back_to_written(client, course):
    headers, _, _, topic_id = course
    made = concept(client, headers, topic_id)
    item = mc_item(client, headers, made["id"]).json()
    url = f"{API}/learning-items/{item['id']}"
    edited = client.patch(
        url,
        json={"choices": [{"text": "Sì", "correct": True}, {"text": "No", "correct": False}]},
        headers=headers,
    ).json()
    assert [c["text"] for c in edited["choices"]] == ["Sì", "No"]
    assert edited["expected_knowledge"] == "✓ Sì"
    back = client.patch(url, json={"choices": []}, headers=headers).json()
    assert (back["answer_format"], back["choices"]) == ("TEXT", None)


BANK = """# Contratti
Domanda: Chi deve restituire il denaro nel mutuo?
A) Il mutuante
B) Il mutuatario
C) Nessuno
Risposta: B

Domanda: Quali sono elementi del mutuo?
a) La consegna
b) La restituzione
c) La forma scritta sempre
Risposta: a e b
Priorità: 1

Domanda: Una domanda normale?
Risposta: A) non è una scelta, è una risposta scritta.
"""


def test_a_question_bank_with_options_imports_multiple_choice(client, auth_headers):
    headers = auth_headers("mc-bank@example.com")
    course_id = client.post(
        f"{API}/courses", json={"title": "Diritto", "language": "it"}, headers=headers
    ).json()["id"]
    document = _upload(client, headers, course_id, "mc.md", BANK.encode())
    assert document["status"] == "READY", document["error_message"]
    outline = client.get(f"{API}/courses/{course_id}/outline", headers=headers).json()
    concepts = [c for t in outline[0]["topics"] for c in t["concepts"]]
    items = [
        client.get(f"{API}/concepts/{c['id']}/learning-items", headers=headers).json()[0]
        for c in concepts
    ]
    first, second, third = items
    assert first["answer_format"] == "CHOICE"
    assert first["questions"][0]["text"] == "Chi deve restituire il denaro nel mutuo?"
    assert [(c["text"], c["correct"]) for c in first["choices"]] == [
        ("Il mutuante", False),
        ("Il mutuatario", True),
        ("Nessuno", False),
    ]
    assert [c["correct"] for c in second["choices"]] == [True, True, False]
    assert second["priority"] == 1
    assert third["answer_format"] == "TEXT"


def test_options_reach_who_gets_the_course_from_the_marketplace(client, auth_headers, author):
    from test_marketplace import acquire, items_of, publish

    [first, *_] = items_of(client, author["headers"], author["course"]["id"])
    client.patch(
        f"{API}/learning-items/{first['id']}", json={"choices": OPTIONS}, headers=author["headers"]
    )
    listing = publish(client, author).json()
    buyer = auth_headers("mc-buyer@example.com")
    course_id = acquire(client, buyer, listing["id"]).json()["course_id"]
    copied = [i for i in items_of(client, buyer, course_id) if i["answer_format"] == "CHOICE"]
    assert len(copied) == 1
    assert [c["correct"] for c in copied[0]["choices"]] == [False, True, False]
    # The options are the author's: the buyer can't change them.
    refused = client.patch(
        f"{API}/learning-items/{copied[0]['id']}", json={"choices": []}, headers=buyer
    )
    assert refused.status_code in (403, 409)


CHATBOT_BANK = r"""# **Il sistema finanziario**

**Domanda:** Qual è la differenza tra mercati monetari e mercati finanziari?\
**Risposta:** I mercati monetari riguardano strumenti a breve termine.\
Priorità: 1

**Domanda:** Quale organo vigila sulle banche?\
- **A)** La Consob\
- **B)** La Banca d'Italia\
- **C)** L'IVASS\
**Risposta:** **B**\
Priorità: 3

Domanda: Chi emette le banconote in euro? A) La BCE B) Il Tesoro C) La Consob
Risposta: A
"""


def test_a_chatbot_written_bank_is_read_without_markdown_and_with_its_options(client, auth_headers):
    headers = auth_headers("chatbot@example.com")
    course_id = client.post(
        f"{API}/courses", json={"title": "Finanza", "language": "it"}, headers=headers
    ).json()["id"]
    document = _upload(client, headers, course_id, "domande.md", CHATBOT_BANK.encode())
    assert document["status"] == "READY", document["error_message"]
    outline = client.get(f"{API}/courses/{course_id}/outline", headers=headers).json()
    topic = outline[0]["topics"][0]
    assert topic["title"] == "Il sistema finanziario"
    items = [
        client.get(f"{API}/concepts/{c['id']}/learning-items", headers=headers).json()[0]
        for c in topic["concepts"]
    ]
    written, vigilance, notes = items
    assert written["answer_format"] == "TEXT"
    assert written["questions"][0]["text"].endswith("mercati finanziari?")
    assert (
        written["expected_knowledge"] == "I mercati monetari riguardano strumenti a breve termine."
    )
    assert vigilance["answer_format"] == "CHOICE"
    assert vigilance["questions"][0]["text"] == "Quale organo vigila sulle banche?"
    assert [c["correct"] for c in vigilance["choices"]] == [False, True, False]
    assert notes["answer_format"] == "CHOICE"
    assert [c["text"] for c in notes["choices"]] == ["La BCE", "Il Tesoro", "La Consob"]


def test_questions_already_saved_are_tidied_and_turned_into_multiple_choice(client, course):
    headers, _, _, topic_id = course
    made = concept(client, headers, topic_id, title="**Vigilanza**")
    client.post(
        f"{API}/concepts/{made['id']}/learning-items",
        json={
            "title": "Chi vigila?\\",
            "expected_knowledge": "B\\",
            "questions": [
                {
                    "question_type": "RECALL",
                    "text": "Chi vigila sulle banche?\\ A) La Consob\\ B) La Banca d'Italia\\ "
                    "C) L'IVASS\\",
                }
            ],
        },
        headers=headers,
    )
    plain = client.post(
        f"{API}/concepts/{made['id']}/learning-items",
        json={
            "title": "Spiega la vigilanza\\",
            "expected_knowledge": "La vigilanza è prudenziale.\\",
            "questions": [{"question_type": "RECALL", "text": "Spiega la vigilanza\\"}],
        },
        headers=headers,
    ).json()
    course_id = plain["course_id"]
    done = client.post(f"{API}/courses/{course_id}/learning-items/detect-choices", headers=headers)
    assert done.json() == {"converted": 1}
    items = client.get(f"{API}/concepts/{made['id']}/learning-items", headers=headers).json()
    choice = next(i for i in items if i["answer_format"] == "CHOICE")
    assert choice["questions"][0]["text"] == "Chi vigila sulle banche?"
    assert [c["correct"] for c in choice["choices"]] == [False, True, False]
    text = next(i for i in items if i["answer_format"] == "TEXT")
    assert text["questions"][0]["text"] == "Spiega la vigilanza"
    assert text["expected_knowledge"] == "La vigilanza è prudenziale."
    concept_title = client.get(f"{API}/concepts/{made['id']}", headers=headers).json()["title"]
    assert concept_title == "Vigilanza"


def test_the_result_shows_the_options_and_what_was_picked(client, course):
    headers, course_id, _, topic_id = course
    made = concept(client, headers, topic_id)
    mc_item(client, headers, made["id"])
    session = start(client, headers, course_id).json()
    shown = card(client, headers, session["id"])
    result = pick(client, headers, session["id"], shown, [0]).json()
    assert result["reference"]["choices"] == OPTIONS
    assert result["reference"]["picked"] == [0]
