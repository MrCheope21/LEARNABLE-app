"""Question banks whose answers are pictures: imported as drawing questions."""

import io

from docx import Document as new_docx
from docx.shared import Cm
from samples import make_png
from test_import_formats import make_apkg
from test_question_banks import _upload
from test_question_banks import course as course

API = "/api/v1"


def _items(client, headers, course_id):
    outline = client.get(f"{API}/courses/{course_id}/outline", headers=headers).json()
    return [
        client.get(f"{API}/concepts/{c['id']}/learning-items", headers=headers).json()[0]
        for chapter in outline
        for topic in chapter["topics"]
        for c in topic["concepts"]
    ]


def test_a_word_question_bank_with_a_picture_as_answer_makes_a_drawing_question(client, course):
    headers, course_id = course
    picture = make_png()
    document = new_docx()
    document.add_heading("Anatomia", level=1)
    document.add_paragraph("Domanda: Disegna la sezione del cuore.")
    document.add_paragraph("Risposta:")
    document.add_picture(io.BytesIO(picture), width=Cm(4))
    document.add_paragraph("")
    document.add_paragraph("Domanda: Quante camere ha il cuore?")
    document.add_paragraph("Risposta: Quattro: due atri e due ventricoli.")
    buffer = io.BytesIO()
    document.save(buffer)

    uploaded = _upload(client, headers, course_id, "cuore.docx", buffer.getvalue())
    assert uploaded["status"] == "READY", uploaded["error_message"]
    drawn, written = _items(client, headers, course_id)
    assert drawn["answer_format"] == "DRAWING"
    assert drawn["questions"][0]["text"] == "Disegna la sezione del cuore."
    reference = client.get(f"{API}/learning-items/{drawn['id']}/reference-drawing", headers=headers)
    assert reference.status_code == 200
    assert reference.content == picture
    assert written["answer_format"] == "TEXT"


def test_an_anki_card_with_a_picture_on_the_back_becomes_a_drawing_question(
    client, course, tmp_path
):
    headers, course_id = course
    picture = make_png()
    data = make_apkg(
        tmp_path,
        [
            (["Disegna una cellula", '<img src="cellula.png">'], 1),
            (["Cos'è il nucleo?", "Contiene il DNA."], 1),
        ],
        extra={"media": '{"0": "cellula.png"}', "0": picture},
    )
    uploaded = _upload(client, headers, course_id, "Biologia.apkg", data)
    assert uploaded["status"] == "READY", uploaded["error_message"]
    assert uploaded["filename"] == "Biologia.docx"
    drawn, written = _items(client, headers, course_id)
    assert drawn["answer_format"] == "DRAWING"
    assert written["expected_knowledge"] == "Contiene il DNA."
