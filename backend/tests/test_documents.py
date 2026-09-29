"""Knowledge Repository over the API (docs/PROJECT_SPEC.md §16-18, §66, §70)."""

import pytest
from samples import make_blank_pdf, make_docx, make_pdf, make_png, make_pptx

from app.api.documents import get_max_upload_bytes
from app.main import app
from app.storage.documents import StoredFileMissingError

TEXT = b"Il costo opportunita e il valore della migliore alternativa.\n\nSecondo paragrafo."


@pytest.fixture
def course(client, auth_headers):
    headers = auth_headers("docs-owner@example.com")
    course_id = client.post("/api/v1/courses", json={"title": "Economia"}, headers=headers).json()[
        "id"
    ]
    return headers, course_id


def _upload(client, headers, course_id, filename, data):
    return client.post(
        f"/api/v1/courses/{course_id}/documents",
        files={"file": (filename, data, "application/octet-stream")},
        headers=headers,
    )


def _processed(client, headers, response):
    """The document after its background processing (TestClient runs it before returning)."""
    assert response.status_code == 202, response.text
    return client.get(f"/api/v1/documents/{response.json()['id']}", headers=headers).json()


def test_upload_returns_immediately_then_processes(client, course, storage):
    headers, course_id = course
    response = _upload(client, headers, course_id, "appunti.txt", TEXT)

    assert response.json()["status"] == "PROCESSING"
    document = _processed(client, headers, response)
    assert document["status"] == "READY"
    assert document["kind"] == "TEXT"
    assert document["mime_type"] == "text/plain"
    assert document["filename"] == "appunti.txt"
    assert document["size_bytes"] == len(TEXT)
    assert document["chunk_count"] == 1
    assert document["error_message"] is None

    [chunk] = client.get(f"/api/v1/documents/{document['id']}/chunks", headers=headers).json()
    assert chunk["text"].startswith("Il costo opportunita")
    assert chunk["paragraph_start"] == 0
    assert chunk["paragraph_end"] == 1


def test_pdf_passages_carry_page_and_section(client, course):
    headers, course_id = course
    data = make_pdf([("Attivo", "Cassa."), ("Passivo", "Debiti verso banche.")])
    document = _processed(client, headers, _upload(client, headers, course_id, "b.pdf", data))

    assert document["page_count"] == 2
    assert document["source_created_at"] is not None
    chunks = client.get(f"/api/v1/documents/{document['id']}/chunks", headers=headers).json()
    assert [(c["page_number"], c["section"]) for c in chunks] == [(1, "Attivo"), (2, "Passivo")]

    # "View source" for one passage (spec §66).
    chunk_id = chunks[1]["id"]
    source = client.get(f"/api/v1/documents/{document['id']}/chunks/{chunk_id}", headers=headers)
    assert source.status_code == 200
    assert source.json()["text"] == "Debiti verso banche."


@pytest.mark.parametrize(
    ("filename", "data", "kind"),
    [
        ("lezione.docx", make_docx([("heading", "Mutuo"), ("para", "Contratto reale.")]), "DOCX"),
        ("slide.pptx", make_pptx([("Deposito", ["Contratto bancario"])]), "PPTX"),
        ("note.md", b"# Cassa\n\nMonete e banconote.", "MARKDOWN"),
    ],
    ids=["docx", "pptx", "markdown"],
)
def test_other_formats_are_processed(client, course, filename, data, kind):
    headers, course_id = course
    document = _processed(client, headers, _upload(client, headers, course_id, filename, data))
    assert document["kind"] == kind
    assert document["status"] == "READY"
    [chunk] = client.get(f"/api/v1/documents/{document['id']}/chunks", headers=headers).json()
    assert chunk["section"] in {"Mutuo", "Deposito", "Cassa"}


@pytest.mark.parametrize(
    ("filename", "data", "reason"),
    [
        ("scan.png", make_png(), "images and scans"),
        ("scansione.pdf", make_blank_pdf(), "No text could be found"),
        ("locked.pdf", make_pdf([(None, "x")], user_password="pw"), "password-protected"),
    ],
    ids=["image", "scanned-pdf", "password-pdf"],
)
def test_unprocessable_files_are_kept_with_a_reason(
    client, course, storage, filename, data, reason
):
    headers, course_id = course
    document = _processed(client, headers, _upload(client, headers, course_id, filename, data))
    assert document["status"] == "FAILED"
    assert reason in document["error_message"]
    assert document["chunk_count"] == 0
    # Stored, listed, not silently dropped.
    listed = client.get(f"/api/v1/courses/{course_id}/documents", headers=headers).json()
    assert [d["id"] for d in listed] == [document["id"]]
    assert storage.load(f"courses/{course_id}/documents/{document['id']}") == data


def test_unsupported_and_empty_uploads_are_rejected(client, course):
    headers, course_id = course
    exe = _upload(client, headers, course_id, "tesi.pdf", b"MZ\x90\x00" + b"\x00" * 64)
    assert exe.status_code == 415
    assert exe.json()["error_type"] == "unsupported_media_type"
    empty = _upload(client, headers, course_id, "vuoto.txt", b"")
    assert empty.status_code == 415
    assert client.get(f"/api/v1/courses/{course_id}/documents", headers=headers).json() == []


def test_oversized_upload_is_rejected(client, course):
    headers, course_id = course
    app.dependency_overrides[get_max_upload_bytes] = lambda: 100
    response = _upload(client, headers, course_id, "big.txt", b"x" * 101)
    assert response.status_code == 413
    assert response.json()["error_type"] == "payload_too_large"
    assert client.get(f"/api/v1/courses/{course_id}/documents", headers=headers).json() == []


def test_duplicates_are_detected_per_course_only(client, course):
    headers, course_id = course
    first = _upload(client, headers, course_id, "a.txt", TEXT)
    again = _upload(client, headers, course_id, "renamed.txt", TEXT)
    assert again.status_code == 409
    assert again.json()["details"]["document_id"] == first.json()["id"]

    other_course = client.post("/api/v1/courses", json={"title": "Altro"}, headers=headers).json()
    assert _upload(client, headers, other_course["id"], "a.txt", TEXT).status_code == 202


def test_path_like_filenames_cannot_escape_storage(client, course, storage, tmp_path):
    headers, course_id = course
    document = _processed(
        client, headers, _upload(client, headers, course_id, "../../../evil.txt", TEXT)
    )
    assert document["filename"] == "evil.txt"
    assert not (tmp_path / "evil.txt").exists()
    assert storage.load(f"courses/{course_id}/documents/{document['id']}") == TEXT


def test_chunk_pagination(client, course):
    headers, course_id = course
    data = "\n\n".join(f"Paragrafo {i}. " + "parola " * 150 for i in range(12)).encode()
    document = _processed(client, headers, _upload(client, headers, course_id, "lungo.txt", data))
    url = f"/api/v1/documents/{document['id']}/chunks"

    first = client.get(url, params={"limit": 2}, headers=headers).json()
    rest = client.get(url, params={"offset": 2, "limit": 200}, headers=headers).json()
    assert [c["position"] for c in first] == [0, 1]
    assert [c["position"] for c in rest] == list(range(2, document["chunk_count"]))
    assert client.get(url, params={"limit": 201}, headers=headers).status_code == 422


def test_a_chunk_is_only_reachable_through_its_own_document(client, course):
    headers, course_id = course
    doc_a = _processed(client, headers, _upload(client, headers, course_id, "a.txt", b"Uno."))
    doc_b = _processed(client, headers, _upload(client, headers, course_id, "b.txt", b"Due."))
    [chunk_a] = client.get(f"/api/v1/documents/{doc_a['id']}/chunks", headers=headers).json()
    mismatched = client.get(
        f"/api/v1/documents/{doc_b['id']}/chunks/{chunk_a['id']}", headers=headers
    )
    assert mismatched.status_code == 404


def test_deleting_a_document_removes_its_file_and_passages(client, course, storage):
    headers, course_id = course
    document = _processed(client, headers, _upload(client, headers, course_id, "a.txt", TEXT))
    key = f"courses/{course_id}/documents/{document['id']}"

    assert client.delete(f"/api/v1/documents/{document['id']}", headers=headers).status_code == 204
    assert client.get(f"/api/v1/documents/{document['id']}", headers=headers).status_code == 404
    with pytest.raises(StoredFileMissingError):
        storage.load(key)


def test_deleting_a_course_removes_its_files(client, course, storage):
    headers, course_id = course
    document = _processed(client, headers, _upload(client, headers, course_id, "a.txt", TEXT))

    assert client.delete(f"/api/v1/courses/{course_id}", headers=headers).status_code == 204
    with pytest.raises(StoredFileMissingError):
        storage.load(f"courses/{course_id}/documents/{document['id']}")


def _run_middleware(content_length: bytes) -> tuple[bool, list[dict]]:
    """Drives BodySizeLimitMiddleware directly with a fake request carrying the given header."""
    import asyncio

    from app.api.limits import BodySizeLimitMiddleware

    reached_app: list[bool] = []
    sent: list[dict] = []

    async def downstream(scope, receive, send):
        reached_app.append(True)

    async def receive():
        return {"type": "http.request", "body": b"", "more_body": False}

    async def send(message):
        sent.append(message)

    middleware = BodySizeLimitMiddleware(downstream, limit_bytes=lambda: 10)
    scope = {
        "type": "http",
        "method": "POST",
        "path": "/",
        "headers": [(b"content-length", content_length)],
    }
    asyncio.run(middleware(scope, receive, send))
    return bool(reached_app), sent


def test_oversized_bodies_are_refused_before_being_read():
    reached_app, sent = _run_middleware(b"11")
    assert not reached_app
    assert sent[0]["status"] == 413


def test_bodies_within_the_limit_pass_through():
    reached_app, sent = _run_middleware(b"10")
    assert reached_app
    assert sent == []
