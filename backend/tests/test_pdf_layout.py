"""Layout-aware PDF reading: headings from font size, paragraphs from spacing, running headers
dropped, and sentences broken by a page break kept whole."""

from samples import make_layout_pdf

from app.models.enums import DocumentKind
from app.services.documents.chunking import chunk_blocks
from app.services.documents.extraction import extract

BODY = 11.0
HEADING = 16.0


def test_larger_font_lines_become_sections():
    data = make_layout_pdf(
        [
            [
                (HEADING, "Reddito d'impresa"),
                (BODY, "Il reddito d'impresa si determina dal risultato del conto economico."),
                (HEADING, "Svalutazione crediti e perdite su crediti (artt. 101 e 106)"),
                (BODY, "Le perdite su crediti sono deducibili se risultano da elementi certi."),
            ]
        ]
    )
    blocks = extract(DocumentKind.PDF, data).blocks

    headings = [b.text for b in blocks if b.is_heading]
    assert headings == [
        "Reddito d'impresa",
        "Svalutazione crediti e perdite su crediti (artt. 101 e 106)",
    ]
    body = [b for b in blocks if not b.is_heading]
    assert [b.heading for b in body] == headings
    assert body[1].text.startswith("Le perdite su crediti")


def test_running_headers_are_dropped():
    pages = [[(BODY, f"Contenuto della pagina {n}. Fine della pagina.")] for n in range(1, 5)]
    blocks = extract(
        DocumentKind.PDF, make_layout_pdf(pages, running_header="IRES - Dispensa")
    ).blocks

    assert blocks
    assert not any("Dispensa" in b.text for b in blocks)


def test_a_sentence_cut_by_a_page_break_stays_whole():
    data = make_layout_pdf(
        [
            [(BODY, "La deduzione spetta ai sensi dell'art.")],
            [(BODY, "109, comma 4, previa imputazione a conto economico. Nuova frase.")],
        ]
    )
    chunks = chunk_blocks(extract(DocumentKind.PDF, data).blocks)

    [chunk] = chunks
    assert "dell'art. 109, comma 4" in chunk.text
    assert (chunk.page, chunk.page_end) == (1, 2)


def test_a_finished_sentence_does_not_join_the_next_page():
    data = make_layout_pdf(
        [
            [(BODY, "Prima pagina completa.")],
            [(BODY, "Seconda pagina, nuovo argomento.")],
        ]
    )
    chunks = chunk_blocks(extract(DocumentKind.PDF, data).blocks)

    assert [(c.page, c.page_end) for c in chunks] == [(1, None), (2, None)]
