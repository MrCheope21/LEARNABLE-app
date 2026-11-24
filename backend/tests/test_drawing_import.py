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


def _png(color: str, size: int = 200) -> bytes:
    from PIL import Image

    buffer = io.BytesIO()
    Image.new("RGB", (size, size), color).save(buffer, format="PNG")
    return buffer.getvalue()


def test_a_picture_under_the_question_is_shown_with_it(client, course):
    headers, course_id = course
    chart = _png("red")
    document = new_docx()
    document.add_paragraph("Domanda: Che cosa mostra questo grafico?")
    document.add_picture(io.BytesIO(chart), width=Cm(5))
    document.add_paragraph("Risposta: L'andamento dei tassi di interesse.")
    buffer = io.BytesIO()
    document.save(buffer)
    uploaded = _upload(client, headers, course_id, "grafici.docx", buffer.getvalue())
    assert uploaded["status"] == "READY", uploaded["error_message"]
    [item] = _items(client, headers, course_id)
    assert item["answer_format"] == "TEXT"
    assert item["question_image_type"] == "image/png"
    assert item["questions"][0]["text"] == "Che cosa mostra questo grafico?"
    shown = client.get(f"{API}/learning-items/{item['id']}/question-image", headers=headers)
    assert shown.status_code == 200
    assert shown.content == chart
    removed = client.delete(f"{API}/learning-items/{item['id']}/question-image", headers=headers)
    assert removed.json()["question_image_type"] is None


def test_a_pdf_bank_keeps_its_pictures_but_not_a_logo_on_every_page(client, course):
    from fpdf import FPDF

    headers, course_id = course
    logo, chart = io.BytesIO(_png("blue")), io.BytesIO(_png("green"))
    pdf = FPDF()
    pdf.set_auto_page_break(auto=False)
    pdf.set_font("Helvetica", size=12)
    for page in range(3):
        pdf.add_page()
        logo.seek(0)
        pdf.image(logo, x=10, y=10, w=30, h=30)  # the same logo on every page
        pdf.set_xy(20, 60)
        pdf.cell(0, 8, f"Domanda: Domanda numero {page + 1}?")
        if page == 1:
            chart.seek(0)
            pdf.image(chart, x=20, y=75, w=60, h=60)
        pdf.set_xy(20, 150)
        pdf.cell(0, 8, f"Risposta: Risposta numero {page + 1}.")
    uploaded = _upload(client, headers, course_id, "slide.pdf", bytes(pdf.output()))
    assert uploaded["status"] == "READY", uploaded["error_message"]
    items = _items(client, headers, course_id)
    assert [i["question_image_type"] for i in items] == [None, "image/png", None]


def test_administrators_upload_larger_files_and_have_no_storage_limit(
    client, auth_headers, db_session
):
    from sqlalchemy import select

    from app.api.documents import get_max_upload_bytes
    from app.main import app
    from app.models.user import User

    headers = auth_headers("boss-upload@example.com")
    db_session.scalar(select(User).where(User.email == "boss-upload@example.com")).is_admin = True
    db_session.commit()
    course_id = client.post(
        f"{API}/courses", json={"title": "Grande", "language": "it"}, headers=headers
    ).json()["id"]
    app.dependency_overrides[get_max_upload_bytes] = lambda: 10
    try:
        big = b"Domanda: Che cos'e?\nRisposta: Una prova abbastanza lunga.\n" * 3
        uploaded = client.post(
            f"{API}/courses/{course_id}/documents",
            files={"file": ("grande.txt", big, "text/plain")},
            headers=headers,
        )
        assert uploaded.status_code == 202, uploaded.text
    finally:
        app.dependency_overrides.pop(get_max_upload_bytes, None)
