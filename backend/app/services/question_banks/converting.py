"""Questions people already have elsewhere: an Anki deck (.apkg) or a spreadsheet (.xlsx, .csv,
.tsv) becomes a question bank in the labelled text format the importer reads
(services/question_banks/parsing.py):

    # Deck or sheet name, or the "topic" column
    Domanda: …
    Risposta: …
    Priorità: 2

The converted text is what is stored and shown as the document, so "View source" shows exactly
what was imported. Nothing here calls the AI.

Spreadsheets: a header row is recognised by its names (question / domanda / front / fronte,
answer / risposta / back / retro, topic / argomento / capitolo / deck, priority / priorità);
without one, the first column is the question, the second the answer and a third, if any, the
topic. Every sheet of a workbook is read; with several, each sheet is a topic.

Anki: notes are read from the collection inside the package; the first field is the question
and the second the answer, cloze notes ({{c1::…}}) ask the sentence with the gap and answer
with it filled in. Formatting, images and sounds are dropped. Packages exported only in the
newest format (collection.anki21b) can't be read: Anki's "Support older Anki versions" option
makes one that can.
"""

import csv
import html
import io
import json
import re
import sqlite3
import tempfile
import zipfile
from dataclasses import dataclass
from pathlib import Path, PureWindowsPath

from app.services.documents.extraction import ExtractionError, _check_archive

MAX_ROWS = 5000


@dataclass(frozen=True)
class Card:
    question: str
    answer: str
    topic: str | None = None
    priority: str | None = None


@dataclass(frozen=True)
class Converted:
    filename: str
    text: str
    cards: int


class ConversionError(ExtractionError):
    """str(error) is safe to show the user."""


def convertible(filename: str, data: bytes) -> bool:
    suffix = PureWindowsPath(filename).suffix.lower()
    if suffix in {".csv", ".tsv"}:
        return b"\x00" not in data[:8192]
    if not data.startswith(b"PK\x03\x04"):
        return False
    try:
        with zipfile.ZipFile(io.BytesIO(data)) as archive:
            names = set(archive.namelist())
    except zipfile.BadZipFile:
        return False
    return "xl/workbook.xml" in names or bool(
        names & {"collection.anki2", "collection.anki21", "collection.anki21b"}
    )


def convert(filename: str, data: bytes) -> Converted:
    suffix = PureWindowsPath(filename).suffix.lower()
    if suffix in {".csv", ".tsv"}:
        cards = _from_csv(data, "\t" if suffix == ".tsv" else None)
        kind = "spreadsheet"
    else:
        _check_archive(data)
        with zipfile.ZipFile(io.BytesIO(data)) as archive:
            names = set(archive.namelist())
        if "xl/workbook.xml" in names:
            cards = _from_xlsx(data)
            kind = "spreadsheet"
        else:
            cards = _from_anki(data, names)
            kind = "Anki"
    if not cards:
        raise ConversionError(
            f"No questions with an answer were found in this {kind} file. "
            + (
                "Put the questions in the first column and the answers in the second (or name "
                'the columns "Domanda" and "Risposta").'
                if kind == "spreadsheet"
                else "Each note needs a front and a back (or a cloze)."
            )
        )
    stem = PureWindowsPath(filename).stem or "domande"
    return Converted(f"{stem}.md"[:255], _as_text(cards[:MAX_ROWS]), min(len(cards), MAX_ROWS))


# --- The labelled text ---

# Lines the importer or the Markdown reader would take for a label, a heading or a code fence.
_SPECIAL_LINE = re.compile(
    r"^\s*(?:#|```|(?:[-*•]\s*)?(?:\d+\s*[.)]\s*)?(?:(?i:domanda|quesito|question|risposta|soluzione|answer|priorit[aà]|priority)\b|[DQRA]\s*\d*\s*:))"
)
# Invisible, and removed again when the text is read (services/documents/cleaning.py).
_GUARD = "​"


def _safe(text: str) -> str:
    lines = [(_GUARD + line if _SPECIAL_LINE.match(line) else line) for line in text.split("\n")]
    return "\n".join(lines).strip()


def _as_text(cards: list[Card]) -> str:
    out: list[str] = []
    topic: str | None = None
    for card in cards:
        if card.topic and card.topic != topic:
            topic = card.topic
            out.append(f"# {' '.join(topic.split())}\n")
        out.append(f"Domanda: {_safe(card.question)}")
        out.append(f"Risposta: {_safe(card.answer)}")
        if card.priority:
            out.append(f"Priorità: {card.priority}")
        out.append("")
    return "\n".join(out).strip() + "\n"


# --- Spreadsheets ---

_COLUMNS = {
    "question": {"question", "domanda", "domande", "front", "fronte", "quesito", "q", "d"},
    "answer": {"answer", "risposta", "risposte", "back", "retro", "soluzione", "a", "r"},
    "topic": {
        "topic",
        "argomento",
        "capitolo",
        "chapter",
        "deck",
        "mazzo",
        "sezione",
        "section",
        "tema",
    },
    "priority": {"priority", "priorità", "priorita", "importanza"},
}


def _columns(header: list[str]) -> dict[str, int] | None:
    found: dict[str, int] = {}
    for index, name in enumerate(header):
        key = name.strip().lower().rstrip(":")
        for column, names in _COLUMNS.items():
            if key in names and column not in found:
                found[column] = index
    return found if {"question", "answer"} <= found.keys() else None


def _cards_from_rows(rows: list[list[str]], sheet: str | None = None) -> list[Card]:
    rows = [[(cell or "").strip() for cell in row] for row in rows]
    rows = [row for row in rows if any(row)]
    if not rows:
        return []
    columns = _columns(rows[0])
    if columns is not None:
        rows = rows[1:]
    else:
        columns = {"question": 0, "answer": 1}
        if max(len(row) for row in rows) >= 3:
            columns["topic"] = 2

    def cell(row: list[str], name: str) -> str:
        index = columns.get(name)
        return row[index] if index is not None and index < len(row) else ""

    cards = []
    for row in rows[: MAX_ROWS + 1]:
        question, answer = cell(row, "question"), cell(row, "answer")
        if question and answer:
            cards.append(
                Card(question, answer, cell(row, "topic") or sheet, cell(row, "priority") or None)
            )
    return cards


def _decode(data: bytes) -> str:
    for encoding in ("utf-8-sig", "cp1252"):
        try:
            return data.decode(encoding)
        except UnicodeDecodeError:
            continue
    return data.decode("latin-1")


def _from_csv(data: bytes, delimiter: str | None) -> list[Card]:
    text = _decode(data)
    if delimiter is None:
        try:
            delimiter = csv.Sniffer().sniff(text[:8192], delimiters=",;\t|").delimiter
        except csv.Error:
            delimiter = ";" if text[:8192].count(";") > text[:8192].count(",") else ","
    return _cards_from_rows(list(csv.reader(io.StringIO(text), delimiter=delimiter)))


def _from_xlsx(data: bytes) -> list[Card]:
    from openpyxl import load_workbook

    try:
        workbook = load_workbook(io.BytesIO(data), read_only=True, data_only=True)
    except Exception as exc:
        raise ConversionError("This spreadsheet is damaged and couldn't be opened.") from exc
    sheets = workbook.worksheets
    cards: list[Card] = []
    for sheet in sheets:
        rows = [
            ["" if value is None else str(value) for value in row]
            for _, row in zip(range(MAX_ROWS + 2), sheet.iter_rows(values_only=True), strict=False)
        ]
        cards += _cards_from_rows(rows, sheet.title if len(sheets) > 1 else None)
    workbook.close()
    return cards


# --- Anki ---

_TAG = re.compile(r"<[^>]+>")
_BREAK = re.compile(r"<\s*(?:br|/div|/p|/li)\s*/?>", re.IGNORECASE)
_MEDIA = re.compile(r"\[sound:[^\]]*\]|<img[^>]*>", re.IGNORECASE)
_CLOZE = re.compile(r"\{\{c\d+::(.*?)(?:::(.*?))?\}\}", re.DOTALL)


def _plain(field: str) -> str:
    text = _MEDIA.sub("", field)
    text = _BREAK.sub("\n", text)
    text = html.unescape(_TAG.sub("", text)).replace("\xa0", " ")
    lines = [" ".join(line.split()) for line in text.split("\n")]
    return "\n".join(line for line in lines if line)


def _note_card(fields: list[str]) -> tuple[str, str] | None:
    first = fields[0] if fields else ""
    if _CLOZE.search(first):
        question = _plain(_CLOZE.sub(lambda m: f"[{m.group(2) or '…'}]", first))
        answer = _plain(_CLOZE.sub(lambda m: m.group(1), first))
        extra = _plain(fields[1]) if len(fields) > 1 else ""
        return question, f"{answer}\n{extra}".strip()
    if len(fields) < 2:
        return None
    question, answer = _plain(fields[0]), _plain(fields[1])
    return (question, answer) if question and answer else None


def _deck_names(db: sqlite3.Connection) -> dict[int, str]:
    try:
        return {int(i): str(n) for i, n in db.execute("SELECT id, name FROM decks")}
    except sqlite3.Error:
        row = db.execute("SELECT decks FROM col").fetchone()
        decks = json.loads(row[0]) if row and row[0] else {}
        return {int(k): str(v.get("name", "")) for k, v in decks.items()}


def _from_anki(data: bytes, names: set[str]) -> list[Card]:
    entry = next((n for n in ("collection.anki21", "collection.anki2") if n in names), None)
    if entry is None or ("collection.anki21b" in names and entry == "collection.anki2"):
        # Newer exports keep the real collection compressed in collection.anki21b, and a
        # placeholder in collection.anki2 that only says to update Anki.
        raise ConversionError(
            "This Anki package uses the newest format. In Anki, export the deck again with "
            '"Support older Anki versions" ticked, then upload that file.'
        )
    with tempfile.TemporaryDirectory() as folder:
        path = Path(folder) / "collection.sqlite"
        with zipfile.ZipFile(io.BytesIO(data)) as archive:
            path.write_bytes(archive.read(entry))
        try:
            db = sqlite3.connect(f"file:{path}?mode=ro", uri=True)
            try:
                decks = _deck_names(db)
                rows = db.execute(
                    "SELECT n.flds, MIN(c.did) FROM notes n LEFT JOIN cards c ON c.nid = n.id "
                    "GROUP BY n.id ORDER BY MIN(c.did), n.id"
                ).fetchall()
            finally:
                db.close()
        except (sqlite3.Error, json.JSONDecodeError) as exc:
            raise ConversionError("This Anki package is damaged and couldn't be read.") from exc
    single_deck = len({did for _, did in rows}) <= 1
    cards: list[Card] = []
    for fields, did in rows[: MAX_ROWS + 1]:
        made = _note_card(str(fields).split("\x1f"))
        if made is None:
            continue
        deck = decks.get(int(did)) if did is not None else None
        topic = None if single_deck or not deck else deck.replace("::", " / ")
        cards.append(Card(made[0], made[1], topic))
    return cards
