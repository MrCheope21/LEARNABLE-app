"""Questions from Anki decks, Excel workbooks and CSV files, imported as question banks."""

import io
import json
import sqlite3
import zipfile
from pathlib import Path

import pytest
from openpyxl import Workbook
from test_question_banks import _outline, _upload
from test_question_banks import course as course

from app.services.question_banks.converting import convert


def _items(client, headers, course_id):
    items = []
    for chapter in _outline(client, headers, course_id):
        for topic in chapter["topics"]:
            for concept in topic["concepts"]:
                for item in client.get(
                    f"/api/v1/concepts/{concept['id']}/learning-items", headers=headers
                ).json():
                    items.append((topic["title"], item))
    return items


def make_apkg(tmp_path: Path, notes, decks=None, entry="collection.anki2", extra=None) -> bytes:
    """A minimal Anki package: the tables the importer reads, in the old (JSON decks) schema."""
    path = tmp_path / "c.sqlite"
    db = sqlite3.connect(path)
    db.execute("CREATE TABLE col (decks TEXT)")
    db.execute("CREATE TABLE notes (id INTEGER PRIMARY KEY, mid INTEGER, flds TEXT, tags TEXT)")
    db.execute("CREATE TABLE cards (id INTEGER PRIMARY KEY, nid INTEGER, did INTEGER)")
    decks = decks or {1: "Default"}
    db.execute(
        "INSERT INTO col VALUES (?)",
        (json.dumps({str(k): {"name": v} for k, v in decks.items()}),),
    )
    for index, (fields, did) in enumerate(notes, start=1):
        db.execute("INSERT INTO notes VALUES (?, 1, ?, '')", (index, "\x1f".join(fields)))
        db.execute("INSERT INTO cards VALUES (?, ?, ?)", (index, index, did))
    db.commit()
    db.close()
    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w") as archive:
        archive.writestr(entry, path.read_bytes())
        archive.writestr("media", "{}")
        for name, content in (extra or {}).items():
            archive.writestr(name, content)
    return buffer.getvalue()


def test_an_anki_deck_becomes_questions_by_deck(client, course, tmp_path):
    headers, course_id = course
    data = make_apkg(
        tmp_path,
        [
            (["Cos'è il <b>mutuo</b>?", "Consegna di denaro<br>con obbligo di restituzione"], 1),
            (["Il deposito trasferisce la {{c1::proprietà::cosa?}} del denaro.", ""], 2),
            (["Solo fronte"], 2),
            (["<img src='x.png'>Domanda: trappola?", "Risposta: vera [sound:a.mp3]"], 2),
        ],
        decks={1: "Diritto::Contratti", 2: "Diritto::Banca"},
    )
    document = _upload(client, headers, course_id, "Diritto.apkg", data)
    assert document["status"] == "READY", document["error_message"]
    assert document["filename"] == "Diritto.md"
    items = _items(client, headers, course_id)
    assert [(topic, item["questions"][0]["text"]) for topic, item in items] == [
        ("Diritto / Contratti", "Cos'è il mutuo?"),
        ("Diritto / Banca", "Il deposito trasferisce la [cosa?] del denaro."),
        ("Diritto / Banca", "Domanda: trappola?"),
    ]
    assert items[0][1]["expected_knowledge"] == "Consegna di denaro con obbligo di restituzione"
    assert items[1][1]["expected_knowledge"] == "Il deposito trasferisce la proprietà del denaro."
    # Text that looks like a label stays text, and media is dropped.
    assert items[2][1]["expected_knowledge"] == "Risposta: vera"


def test_the_newest_anki_format_explains_how_to_export_again(client, course, tmp_path):
    headers, course_id = course
    data = make_apkg(tmp_path, [(["Please update", "x"], 1)], extra={"collection.anki21b": b"z"})
    response = client.post(
        f"/api/v1/courses/{course_id}/documents",
        files={"file": ("nuovo.apkg", data, "application/octet-stream")},
        headers=headers,
    )
    assert response.status_code == 415
    assert "Support older Anki versions" in response.json()["message"]


def test_an_excel_workbook_with_named_columns_and_priorities(client, course):
    headers, course_id = course
    book = Workbook()
    sheet = book.active
    sheet.title = "IRES"
    sheet.append(["Argomento", "Domanda", "Risposta", "Priorità"])
    sheet.append(["Presupposto", "Qual è il presupposto?", "Il possesso di redditi.", 1])
    sheet.append(["Presupposto", "Senza risposta", None, None])
    sheet.append(["Soggetti", "Chi paga l'IRES?", "Le società di capitali.", "accessoria"])
    other = book.create_sheet("IVA")
    other.append(["Che cos'è l'IVA?", "Un'imposta sul valore aggiunto."])
    buffer = io.BytesIO()
    book.save(buffer)

    document = _upload(client, headers, course_id, "Tributario.xlsx", buffer.getvalue())
    assert document["status"] == "READY", document["error_message"]
    items = _items(client, headers, course_id)
    assert [(topic, item["questions"][0]["text"], item["priority"]) for topic, item in items] == [
        ("Presupposto", "Qual è il presupposto?", 1),
        ("Soggetti", "Chi paga l'IRES?", 4),
        ("IVA", "Che cos'è l'IVA?", 1),  # no priority column: the default
    ]


def test_a_csv_without_header_uses_question_answer_topic(client, course):
    headers, course_id = course
    data = (
        "Che cos'è il mutuo?;Un prestito di denaro.;Contratti\n"
        "E il comodato?;Un prestito d'uso.;Contratti\n"
    )
    document = _upload(client, headers, course_id, "domande.csv", data.encode("cp1252"))
    assert document["status"] == "READY", document["error_message"]
    items = _items(client, headers, course_id)
    assert [(t, i["questions"][0]["text"], i["expected_knowledge"]) for t, i in items] == [
        ("Contratti", "Che cos'è il mutuo?", "Un prestito di denaro."),
        ("Contratti", "E il comodato?", "Un prestito d'uso."),
    ]


def test_a_spreadsheet_without_answers_says_how_to_lay_it_out():
    with pytest.raises(Exception, match="first column"):
        convert("vuoto.csv", b"solo una colonna\naltra riga\n")
