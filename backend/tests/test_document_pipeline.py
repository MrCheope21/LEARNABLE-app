"""Unit tests for the ingestion pipeline: detect → extract → clean → chunk (spec §16-18)."""

import zipfile
from datetime import datetime
from io import BytesIO

import pytest
from samples import make_blank_pdf, make_docx, make_pdf, make_png, make_pptx

from app.models.enums import DocumentKind
from app.services.documents import extraction
from app.services.documents.chunking import chunk_blocks
from app.services.documents.cleaning import clean_text
from app.services.documents.detection import clean_filename, detect_type
from app.services.documents.extraction import Block, ExtractionError, extract


def _plain_zip() -> bytes:
    buffer = BytesIO()
    with zipfile.ZipFile(buffer, "w") as archive:
        archive.writestr("readme.txt", "not an office file")
    return buffer.getvalue()


# --- detection: by content, never by the client's claims ---


@pytest.mark.parametrize(
    ("filename", "data", "kind"),
    [
        ("notes.pdf", make_pdf([(None, "x")]), DocumentKind.PDF),
        ("renamed.txt", make_pdf([(None, "x")]), DocumentKind.PDF),  # extension ignored
        ("lecture.docx", make_docx([("para", "x")]), DocumentKind.DOCX),
        ("slides.pptx", make_pptx([("T", ["x"])]), DocumentKind.PPTX),
        ("scan.png", make_png(), DocumentKind.IMAGE),
        ("photo.jpg", b"\xff\xd8\xff\xe0" + b"\x00" * 20, DocumentKind.IMAGE),
        ("iphone.heic", b"\x00\x00\x00\x18ftypheic" + b"\x00" * 20, DocumentKind.IMAGE),
        ("notes.txt", b"Appunti di diritto", DocumentKind.TEXT),
        ("notes.md", b"# Titolo\n\nTesto", DocumentKind.MARKDOWN),
    ],
    # Explicit ids: the default would embed whole files, and pytest exports the id as an
    # environment variable (Windows caps those at 32,767 characters).
    ids=lambda value: value if isinstance(value, str) else "",
)
def test_detects_type_from_content(filename, data, kind):
    detected = detect_type(filename, data)
    assert detected is not None
    assert detected.kind is kind


@pytest.mark.parametrize(
    ("filename", "data"),
    [
        ("malware.pdf", b"MZ\x90\x00" + b"\x00" * 64),  # a Windows executable renamed to .pdf
        ("archive.docx", _plain_zip()),
        ("binary.txt", b"text\x00with\x00nuls"),
        ("unknown.bin", b"just some bytes"),
    ],
    ids=["exe-renamed-pdf", "plain-zip-named-docx", "binary-named-txt", "unknown"],
)
def test_rejects_unrecognized_content(filename, data):
    assert detect_type(filename, data) is None


@pytest.mark.parametrize(
    ("raw", "cleaned"),
    [
        ("../../etc/passwd.txt", "passwd.txt"),
        ("C:\\Users\\me\\Desktop\\Bilancio.pdf", "Bilancio.pdf"),
        ("with\x00control\x1fchars.pdf", "withcontrolchars.pdf"),
        ("", "untitled"),
        (None, "untitled"),
    ],
)
def test_filenames_are_display_metadata_only(raw, cleaned):
    assert clean_filename(raw) == cleaned


# --- cleaning ---


@pytest.mark.parametrize(
    ("raw", "cleaned"),
    [
        ("inter-\nnazionale", "internazionale"),  # line-break hyphenation rejoined
        ("Rossi-\nBianchi", "Rossi- Bianchi"),  # capitalised: a real hyphenated name, kept
        ("line one\nline two", "line one line two"),  # layout wraps, not meaning
        ("nul\x00byte", "nulbyte"),  # Postgres rejects NUL in text
        ("ﬁnanza e ﬂusso", "finanza e flusso"),  # ligatures
        ("x² is kept", "x² is kept"),  # no NFKC folding
        ("soft\u00adhyphen", "softhyphen"),
        ("  spaced   out  ", "spaced out"),
    ],
)
def test_clean_text(raw, cleaned):
    assert clean_text(raw) == cleaned


# --- chunking ---


def test_chunks_never_cross_pages_or_sections():
    blocks = [
        Block("a" * 100, page=1, heading="Intro"),
        Block("b" * 100, page=2, heading="Intro"),
        Block("c" * 100, page=2, heading="Method"),
    ]
    chunks = chunk_blocks(blocks, max_chars=10_000)
    assert [(c.page, c.section) for c in chunks] == [(1, "Intro"), (2, "Intro"), (2, "Method")]
    assert [(c.paragraph_start, c.paragraph_end) for c in chunks] == [(0, 0), (1, 1), (2, 2)]


def test_small_paragraphs_are_grouped_up_to_the_limit():
    blocks = [Block(f"Paragraph {i} " + "x" * 40) for i in range(10)]
    chunks = chunk_blocks(blocks, max_chars=200)
    assert all(len(c.text) <= 200 for c in chunks)
    assert len(chunks) > 1
    # Nothing lost, order kept.
    joined = "\n\n".join(c.text for c in chunks)
    assert [f"Paragraph {i} " in joined for i in range(10)] == [True] * 10
    assert chunks[0].paragraph_start == 0
    assert chunks[-1].paragraph_end == 9


def test_long_paragraphs_split_at_sentences_then_words():
    sentence = "Il costo opportunità è il valore della migliore alternativa. "
    chunks = chunk_blocks([Block(sentence * 30)], max_chars=200)
    assert all(len(c.text) <= 200 for c in chunks)
    assert all(c.text.endswith(".") for c in chunks[:-1])  # split at sentence ends
    endless = chunk_blocks([Block("parola " * 200 + "x" * 450)], max_chars=200)
    assert all(len(c.text) <= 200 for c in endless)


def test_headings_become_sections_not_passage_text():
    blocks = [
        Block("Capitolo 1", heading="Capitolo 1", is_heading=True),
        Block("Contenuto", heading="Capitolo 1"),
    ]
    [chunk] = chunk_blocks(blocks)
    assert chunk.text == "Contenuto"
    assert chunk.section == "Capitolo 1"


# --- extraction, per format ---


def test_pdf_keeps_page_numbers_and_bookmark_sections():
    data = make_pdf(
        [
            ("Stato patrimoniale", "Cassa e disponibilita liquide."),
            (None, "Crediti verso banche."),  # no bookmark: still under the previous one
            ("Conto economico", "Interessi attivi."),
        ]
    )
    result = extract(DocumentKind.PDF, data)
    assert result.page_count == 3
    located = [(b.page, b.heading) for b in result.blocks]
    assert located == [
        (1, "Stato patrimoniale"),
        (2, "Stato patrimoniale"),
        (3, "Conto economico"),
    ]
    assert "Cassa" in result.blocks[0].text
    assert isinstance(result.source_created_at, datetime)
    assert result.source_created_at.tzinfo is not None


def test_pdf_with_owner_password_only_is_readable():
    # Common for published textbooks: opens freely, printing/copying restricted.
    data = make_pdf([(None, "Contenuto protetto dalla stampa.")], owner_password="publisher")
    result = extract(DocumentKind.PDF, data)
    assert "Contenuto protetto" in result.blocks[0].text


def test_pdf_with_open_password_fails_with_a_clear_reason():
    data = make_pdf([(None, "Segreto.")], user_password="secret")
    with pytest.raises(ExtractionError, match="password-protected"):
        extract(DocumentKind.PDF, data)


def test_scanned_pdf_yields_no_blocks():
    assert extract(DocumentKind.PDF, make_blank_pdf(2)).blocks == []


def test_damaged_pdf_fails_with_a_clear_reason():
    with pytest.raises(ExtractionError, match="couldn't be read"):
        extract(DocumentKind.PDF, b"%PDF-1.7\nthis is not really a pdf")


def test_docx_headings_tables_and_order():
    data = make_docx(
        [
            ("heading", "Imprenditore"),
            ("para", "Chi esercita professionalmente un'attivita economica."),
            ("table", "Tipo|Esempio;Commerciale|Industria"),
            ("para", "Dopo la tabella."),
        ]
    )
    blocks = extract(DocumentKind.DOCX, data).blocks
    assert blocks[0].is_heading
    assert [b.text for b in blocks[1:]] == [
        "Chi esercita professionalmente un'attivita economica.",
        "Tipo | Esempio",
        "Commerciale | Industria",
        "Dopo la tabella.",
    ]
    assert {b.heading for b in blocks} == {"Imprenditore"}


def test_pptx_slides_are_pages_and_titles_are_sections():
    data = make_pptx([("Cassa", ["Monete", "Banconote"]), ("Crediti", ["Verso banche"])])
    result = extract(DocumentKind.PPTX, data)
    assert result.page_count == 2
    content = [(b.page, b.heading, b.text) for b in result.blocks if not b.is_heading]
    assert content == [
        (1, "Cassa", "Monete"),
        (1, "Cassa", "Banconote"),
        (2, "Crediti", "Verso banche"),
    ]


def test_markdown_headings_but_not_inside_code_fences():
    text = "# Bilancio\n\nIntro.\n\n```\n# not a heading\n```\n\n## Attivo\n\nCassa."
    blocks = extract(DocumentKind.MARKDOWN, text.encode()).blocks
    headings = [b.text for b in blocks if b.is_heading]
    assert headings == ["Bilancio", "Attivo"]
    assert blocks[-1].heading == "Attivo"


def test_text_falls_back_from_utf8_to_cp1252():
    blocks = extract(DocumentKind.TEXT, "perché è così".encode("cp1252")).blocks
    assert blocks[0].text == "perché è così"


def test_images_fail_with_a_clear_reason():
    with pytest.raises(ExtractionError, match="images and scans"):
        extract(DocumentKind.IMAGE, make_png())


def test_zip_bomb_guard(monkeypatch):
    monkeypatch.setattr(extraction, "MAX_UNCOMPRESSED_BYTES", 1000)
    data = make_docx([("para", "x" * 5000)])
    with pytest.raises(ExtractionError, match="too large"):
        extract(DocumentKind.DOCX, data)
