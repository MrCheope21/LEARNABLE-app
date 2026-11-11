"""Question priority, from 1 Essential to 5 In depth (labels and filters for the student)."""

import pytest
from test_question_banks import _outline, _upload
from test_question_banks import course as bank_course  # noqa: F401
from test_review import concept, course, item  # noqa: F401


def get(client, headers, item_id):
    return client.get(f"/api/v1/learning-items/{item_id}", headers=headers).json()


@pytest.mark.parametrize(
    ("role", "priority"),
    [
        ("CORE_TRAINABLE", 1),
        ("SUPPORTING_TRAINABLE", 2),
        ("COMMON_TRAP", 2),
        ("OPTIONAL_EXTENSION", 3),
        ("INFORMATIONAL", 3),
    ],
)
def test_a_new_question_starts_from_its_role(client, course, role, priority):  # noqa: F811
    headers, _, _, topic_id = course
    created = item(client, headers, concept(client, headers, topic_id)["id"], role=role)
    assert created["priority"] == priority


def test_a_priority_given_when_creating_wins_over_the_role(client, course):  # noqa: F811
    headers, _, _, topic_id = course
    created = item(client, headers, concept(client, headers, topic_id)["id"], priority=3)
    assert (created["role"], created["priority"]) == ("CORE_TRAINABLE", 3)


def test_priority_can_be_changed_but_only_from_1_to_5(client, course):  # noqa: F811
    headers, _, _, topic_id = course
    created = item(client, headers, concept(client, headers, topic_id)["id"])
    url = f"/api/v1/learning-items/{created['id']}"
    assert client.patch(url, json={"priority": 2}, headers=headers).json()["priority"] == 2
    for bad in (0, 6, "high"):
        assert client.patch(url, json={"priority": bad}, headers=headers).status_code == 422
    assert get(client, headers, created["id"])["priority"] == 2
    # Accessory (4) and in depth (5): below "useful", for details and optional extras.
    for level in (4, 5):
        assert (
            client.patch(url, json={"priority": level}, headers=headers).json()["priority"] == level
        )


def test_many_questions_get_a_priority_at_once(client, course):  # noqa: F811
    headers, course_id, _, topic_id = course
    target = concept(client, headers, topic_id)["id"]
    ids = [item(client, headers, target, title=f"Item {n}")["id"] for n in range(3)]
    url = f"/api/v1/courses/{course_id}/learning-items/bulk"
    done = client.post(
        url, json={"item_ids": ids[:2], "action": "set_priority", "priority": 3}, headers=headers
    )
    assert done.json()["affected"] == 2
    assert [get(client, headers, i)["priority"] for i in ids] == [3, 3, 1]
    missing = client.post(url, json={"item_ids": ids, "action": "set_priority"}, headers=headers)
    assert missing.status_code == 422


BANK = """# Imprenditore

Domanda: Chi è imprenditore?
Risposta: Chi esercita professionalmente un'attività economica organizzata.
Priorità: 1

Domanda: Che cos'è la piccola impresa?
Priorità: approfondimento
Risposta: L'impresa esercitata con il lavoro prevalentemente proprio e della famiglia.

Domanda: Che cos'è l'impresa agricola?
Risposta: Coltivazione del fondo, selvicoltura, allevamento di animali e attività connesse.
"""


def test_question_banks_take_a_priority_line(client, bank_course):  # noqa: F811
    headers, course_id = bank_course
    document = _upload(client, headers, course_id, "Imprenditore.md", BANK.encode())
    assert document["status"] == "READY", document["error_message"]
    [chapter] = _outline(client, headers, course_id)
    concepts = [c for t in chapter["topics"] for c in t["concepts"]]
    assert [c["title"] for c in concepts] == [
        "Chi è imprenditore?",
        "Che cos'è la piccola impresa?",
        "Che cos'è l'impresa agricola?",
    ]
    items = [
        client.get(f"/api/v1/concepts/{c['id']}/learning-items", headers=headers).json()[0]
        for c in concepts
    ]
    assert [i["priority"] for i in items] == [1, 5, 1]
    # The label line is not part of the expected answer.
    assert all("Priorit" not in i["expected_knowledge"] for i in items)


@pytest.mark.parametrize(
    ("label", "priority"),
    [
        ("1", 1),
        ("Fondamentale", 1),
        ("importante", 2),
        ("utile", 3),
        ("4", 4),
        ("accessoria", 4),
        ("Accessory", 4),
        ("5", 5),
        ("facoltativa", 5),
    ],
)
def test_every_priority_level_can_be_written_in_the_file(client, bank_course, label, priority):  # noqa: F811
    headers, course_id = bank_course
    answer = "Il maggior valore dell'azienda."
    bank = f"Domanda: Che cos'è l'avviamento?\nRisposta: {answer}\nPriorità: {label}\n"
    document = _upload(client, headers, course_id, "Avviamento.md", bank.encode())
    assert document["status"] == "READY", document["error_message"]
    [chapter] = _outline(client, headers, course_id)
    [made] = [c for t in chapter["topics"] for c in t["concepts"]]
    [question] = client.get(f"/api/v1/concepts/{made['id']}/learning-items", headers=headers).json()
    assert question["priority"] == priority
    assert "Priorit" not in question["expected_knowledge"]
