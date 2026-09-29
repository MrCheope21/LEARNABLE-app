"""Question banks: the user's own labelled questions and expected answers, imported without AI."""

import pytest
from samples import make_docx, make_layout_pdf, make_png

from app.services.documents.blocks import Block
from app.services.question_banks.parsing import parse_question_bank

BANK = """# Presupposto
Domanda: Qual è il presupposto dell'IRES?
Risposta: Il possesso di redditi in denaro o in natura.
Per le società commerciali tutti i redditi sono reddito d'impresa.

Domanda: Chi sono i soggetti passivi?
Risposta: Le società e gli enti elencati dall'art. 73 del TUIR:
- società di capitali residenti;
- enti commerciali residenti.

# Deduzioni
D: Quando sono deducibili le perdite su crediti?
R: Quando risultano da elementi certi e precisi (art. 101, comma 5).
"""


def _blocks(text: str) -> list[Block]:
    """Markdown-like blocks: "# " lines are headings, blank lines end paragraphs."""
    blocks: list[Block] = []
    heading = None
    for paragraph in text.split("\n\n"):
        lines: list[str] = []
        for line in paragraph.splitlines():
            if line.startswith("# "):
                if lines:
                    blocks.append(Block("\n".join(lines), heading=heading))
                    lines = []
                heading = line[2:]
                blocks.append(Block(heading, heading=heading, is_heading=True))
            else:
                lines.append(line)
        if lines:
            blocks.append(Block("\n".join(lines), heading=heading))
    return blocks


# --- Parsing ---


def test_parses_labelled_pairs_under_their_headings():
    result = parse_question_bank(_blocks(BANK))

    assert [(p.heading, p.question) for p in result.pairs] == [
        ("Presupposto", "Qual è il presupposto dell'IRES?"),
        ("Presupposto", "Chi sono i soggetti passivi?"),
        ("Deduzioni", "Quando sono deducibili le perdite su crediti?"),
    ]
    # Wrapped lines rejoin; list items keep their own lines.
    assert result.pairs[0].answer == (
        "Il possesso di redditi in denaro o in natura. "
        "Per le società commerciali tutti i redditi sono reddito d'impresa."
    )
    assert result.pairs[1].answer == (
        "Le società e gli enti elencati dall'art. 73 del TUIR:\n"
        "- società di capitali residenti;\n"
        "- enti commerciali residenti."
    )
    assert result.unanswered_pages == []


@pytest.mark.parametrize(
    "text",
    [
        "Domanda: Che cos'è X?\nRisposta: Una cosa.",
        "domanda 1: Che cos'è X?\nrisposta 1: Una cosa.",
        "1. Domanda: Che cos'è X?\nRisposta - Una cosa.",
        "Quesito n. 3) Che cos'è X?\nSoluzione: Una cosa.",
        "Question: Che cos'è X?\nAnswer: Una cosa.",
        "Q: Che cos'è X?\nA: Una cosa.",
        "Domanda: Che cos'è X? Risposta: Una cosa.",
    ],
    ids=["plain", "numbered", "list-numbered", "quesito", "english", "letters", "inline"],
)
def test_label_variants(text: str):
    [pair] = parse_question_bank(_blocks(text)).pairs
    assert (pair.question, pair.answer) == ("Che cos'è X?", "Una cosa.")


def test_ordinary_text_is_not_mistaken_for_labels():
    text = (
        "Domanda: Cosa ha cambiato il decreto?\n"
        "Risposta: Il D. Lgs. 209/2023 ha riformato la materia.\n"
        "D. Lgs. significa decreto legislativo; vedi anche:\n"
        "a) primo punto\n"
        "Domande frequenti restano escluse."
    )
    [pair] = parse_question_bank(_blocks(text)).pairs
    assert pair.answer.startswith("Il D. Lgs. 209/2023")
    assert "primo punto" in pair.answer
    assert pair.answer.endswith("Domande frequenti restano escluse.")


def test_questions_without_an_answer_are_reported_not_imported():
    text = (
        "Intro text ignored.\n\nDomanda: Senza risposta?\n\nDomanda: Con risposta?\nRisposta: Sì."
    )
    result = parse_question_bank(_blocks(text))

    assert [p.question for p in result.pairs] == ["Con risposta?"]
    assert result.unanswered_pages == [None]


# --- Import over the API ---


@pytest.fixture
def course(client, auth_headers):
    headers = auth_headers("bank-owner@example.com")
    course = client.post(
        "/api/v1/courses", json={"title": "Tributario", "language": "it"}, headers=headers
    ).json()
    return headers, course["id"]


def _upload(client, headers, course_id, filename, data, **form):
    response = client.post(
        f"/api/v1/courses/{course_id}/documents",
        files={"file": (filename, data, "application/octet-stream")},
        data={"purpose": "QUESTION_BANK", **form},
        headers=headers,
    )
    assert response.status_code == 202, response.text
    assert response.json()["purpose"] == "QUESTION_BANK"
    # TestClient runs the background processing before returning.
    return client.get(f"/api/v1/documents/{response.json()['id']}", headers=headers).json()


def _outline(client, headers, course_id):
    return client.get(f"/api/v1/courses/{course_id}/outline", headers=headers).json()


def test_markdown_bank_becomes_concepts_with_items(client, course):
    headers, course_id = course
    document = _upload(client, headers, course_id, "IRES domande.md", BANK.encode())

    assert document["status"] == "READY", document["error_message"]
    assert document["chunk_count"] == 3
    assert document["import_notice"] is None
    assert document["analyzed_at"] is not None

    [chapter] = _outline(client, headers, course_id)
    assert chapter["title"] == "IRES domande"
    assert chapter["id"] == document["chapter_id"]
    assert [t["title"] for t in chapter["topics"]] == ["Presupposto", "Deduzioni"]
    concepts = [c for t in chapter["topics"] for c in t["concepts"]]
    assert [c["study_state"] for c in concepts] == ["NOT_STUDIED"] * 3
    assert concepts[0]["title"] == "Qual è il presupposto dell'IRES?"

    [item] = client.get(
        f"/api/v1/concepts/{concepts[0]['id']}/learning-items", headers=headers
    ).json()
    assert item["in_training"] is True
    assert item["role"] == "CORE_TRAINABLE"
    assert item["expected_knowledge"].startswith("Il possesso di redditi")
    assert item["essential_points"] == [
        "Il possesso di redditi in denaro o in natura.",
        "Per le società commerciali tutti i redditi sono reddito d'impresa.",
    ]
    assert [(q["question_type"], q["text"]) for q in item["questions"]] == [
        ("RECALL", "Qual è il presupposto dell'IRES?")
    ]

    # "View source" shows exactly what the user wrote.
    [source] = client.get(f"/api/v1/concepts/{concepts[0]['id']}/sources", headers=headers).json()
    assert source["text"].startswith("Domanda: Qual è il presupposto dell'IRES?\n\nRisposta:")


def test_activation_keeps_the_imported_items(client, course):
    headers, course_id = course
    _upload(client, headers, course_id, "bank.md", BANK.encode())
    concept = _outline(client, headers, course_id)[0]["topics"][0]["concepts"][0]

    activated = client.post(f"/api/v1/concepts/{concept['id']}/activate", headers=headers)
    assert activated.status_code == 200
    assert activated.json()["study_state"] == "ACTIVE"
    assert activated.json()["item_generation_status"] == "READY"
    items = client.get(f"/api/v1/concepts/{concept['id']}/learning-items", headers=headers).json()
    assert len(items) == 1


def test_docx_bank_into_an_existing_chapter_reuses_topics(client, course):
    headers, course_id = course
    chapter = client.post(
        f"/api/v1/courses/{course_id}/chapters", json={"title": "Capitolo 1"}, headers=headers
    ).json()
    first = make_docx([("para", "Domanda: Uno?"), ("para", "Risposta: Primo.")])
    second = make_docx(
        [
            ("para", "Domanda: Due?"),
            ("para", "Risposta: Secondo, su"),
            ("para", "più paragrafi."),
            ("para", "Domanda: Tre?"),
        ]
    )
    _upload(client, headers, course_id, "a.docx", first, chapter_id=chapter["id"])
    document = _upload(client, headers, course_id, "b.docx", second, chapter_id=chapter["id"])

    assert document["import_notice"] == "1 question was skipped because no answer followed."
    [outline] = _outline(client, headers, course_id)
    [topic] = outline["topics"]
    assert topic["title"] == "Domande"  # no headings: one default Topic, reused
    assert [c["title"] for c in topic["concepts"]] == ["Uno?", "Due?"]
    items = client.get(
        f"/api/v1/concepts/{topic['concepts'][1]['id']}/learning-items", headers=headers
    ).json()
    assert items[0]["expected_knowledge"] == "Secondo, su\npiù paragrafi."


def test_pdf_bank_keeps_pages_and_headings(client, course):
    headers, course_id = course
    data = make_layout_pdf(
        [
            [(16, "Reddito d'impresa"), (11, "Domanda: Cos'è?\nRisposta: Un reddito.")],
            [(11, "Domanda: E poi?\nRisposta: Altro.")],
        ]
    )
    document = _upload(client, headers, course_id, "bank.pdf", data)

    assert document["status"] == "READY", document["error_message"]
    chunks = client.get(f"/api/v1/documents/{document['id']}/chunks", headers=headers).json()
    assert [(c["page_number"], c["section"]) for c in chunks] == [
        (1, "Reddito d'impresa"),
        (2, "Reddito d'impresa"),
    ]


def test_a_file_without_labels_fails_with_instructions(client, course):
    headers, course_id = course
    document = _upload(client, headers, course_id, "notes.md", b"Solo appunti, nessuna domanda.")

    assert document["status"] == "FAILED"
    assert "Domanda:" in document["error_message"]
    assert _outline(client, headers, course_id) == []


def test_images_cannot_be_question_banks(client, course):
    headers, course_id = course
    response = client.post(
        f"/api/v1/courses/{course_id}/documents",
        files={"file": ("foto.png", make_png(), "image/png")},
        data={"purpose": "QUESTION_BANK"},
        headers=headers,
    )
    assert response.status_code == 415


def test_question_banks_never_feed_curriculum_generation(client, course):
    headers, course_id = course
    document = _upload(client, headers, course_id, "bank.md", BANK.encode())
    url = f"/api/v1/courses/{course_id}/curriculum-proposals"

    response = client.post(url, json={}, headers=headers)
    assert response.status_code == 409
    assert response.json()["details"]["reason"] == "no_source_material"

    response = client.post(url, json={"document_ids": [document["id"]]}, headers=headers)
    assert response.status_code == 409
    assert response.json()["details"]["reason"] == "documents_are_question_banks"


def test_material_is_the_default_purpose(client, course):
    headers, course_id = course
    response = client.post(
        f"/api/v1/courses/{course_id}/documents",
        files={"file": ("n.md", BANK.encode(), "application/octet-stream")},
        headers=headers,
    )
    assert response.json()["purpose"] == "MATERIAL"
    assert _outline(client, headers, course_id) == []
