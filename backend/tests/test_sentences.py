"""Sentence splitting on legal and academic prose: a full stop is not always a sentence end."""

import pytest

from app.services.documents.sentences import split_sentences


@pytest.mark.parametrize(
    ("text", "expected"),
    [
        ("Primo punto. Secondo punto.", ["Primo punto.", "Secondo punto."]),
        ("Davvero? Sì! Bene…", ["Davvero?", "Sì!", "Bene…"]),
        (
            "Si applicano gli artt. 72 e 73 del TUIR. Il resto segue.",
            ["Si applicano gli artt. 72 e 73 del TUIR.", "Il resto segue."],
        ),
        (
            "Il D.Lgs. 209/2023 ha modificato la norma. Vedi Cass. Sez. Unite.",
            ["Il D.Lgs. 209/2023 ha modificato la norma.", "Vedi Cass. Sez. Unite."],
        ),
        ("La società X S.p.A. Ha sede a Roma.", ["La società X S.p.A. Ha sede a Roma."]),
        ("Come osserva A. Rossi. Poi basta.", ["Come osserva A. Rossi.", "Poi basta."]),
        ("Vale per i nn. 1 e 2. Fine.", ["Vale per i nn. 1 e 2.", "Fine."]),
        # A lowercase or numeric continuation is never a new sentence.
        ("Il valore è 3. meno di prima.", ["Il valore è 3. meno di prima."]),
        ('Disse: "Basta." Poi uscì.', ['Disse: "Basta."', "Poi uscì."]),
        (
            "Words that end sentences: say no. Then go.",
            ["Words that end sentences: say no.", "Then go."],
        ),
        ("", []),
        ("   ", []),
    ],
)
def test_split_sentences(text: str, expected: list[str]) -> None:
    assert split_sentences(text) == expected
