"""ReviewOutcomeResolver: evaluation evidence → outcome, deterministically (task §5.5).

The spec's answer fixtures (§78, A-I) as the evidence a good evaluator would return for them,
and what the rules must make of it. Semantic judgement itself is the model's job and is tested
against real models, not here; this pins down that scheduling never depends on it directly.
"""

import pytest

from app.ai.schemas import EvaluationOutput
from app.models.enums import EvaluationClassification as C
from app.models.enums import ReviewOutcome
from app.services.evaluation.resolver import resolve_outcome


def evidence(classification: C, score: float = 1.0, **overrides) -> EvaluationOutput:
    values = {
        "classification": classification,
        "correctness": score,
        "completeness": score,
        "conceptual_understanding": score,
        "precision": score,
        "confidence": 0.9,
        "context_sufficient": True,
        **overrides,
    }
    return EvaluationOutput(**values)


@pytest.mark.parametrize(
    ("fixture", "evaluation", "outcome"),
    [
        ("A fully correct", evidence(C.CORRECT), ReviewOutcome.GOOD),
        (
            "B correct but incomplete",
            evidence(C.PARTIALLY_CORRECT, 0.8, completeness=0.55),
            ReviewOutcome.HARD,
        ),
        ("C incorrect", evidence(C.WRONG, 0.1), ReviewOutcome.AGAIN),
        ("D same meaning, other words", evidence(C.CORRECT, 0.95), ReviewOutcome.GOOD),
        ("E misconception", evidence(C.MISCONCEPTION, 0.4), ReviewOutcome.AGAIN),
        ("F ambiguous", evidence(C.UNCERTAIN, 0.5, confidence=0.3), None),
        # G: right by outside knowledge, unsupported by the course: the evaluator must not count
        # it as correct; whatever it then says, a low-scored WRONG resolves to AGAIN.
        ("G unsupported by the course", evidence(C.WRONG, 0.3), ReviewOutcome.AGAIN),
        ("H correct plus irrelevant extras", evidence(C.CORRECT, 0.9), ReviewOutcome.GOOD),
        (
            "I insufficient source context",
            evidence(C.CORRECT, context_sufficient=False),
            None,
        ),
    ],
)
def test_answer_fixtures(fixture, evaluation, outcome):
    assert resolve_outcome(evaluation) is outcome, fixture


def test_easy_is_never_resolved_from_an_evaluation():
    perfect = evidence(C.CORRECT, 1.0, confidence=1.0)
    assert resolve_outcome(perfect) is ReviewOutcome.GOOD


@pytest.mark.parametrize(
    ("overrides", "outcome"),
    [
        ({"completeness": 0.69}, ReviewOutcome.HARD),
        ({"conceptual_understanding": 0.59}, ReviewOutcome.HARD),
        ({"completeness": 0.7, "conceptual_understanding": 0.6}, ReviewOutcome.GOOD),
    ],
)
def test_correct_but_shaky_is_hard(overrides, outcome):
    assert resolve_outcome(evidence(C.CORRECT, 0.9, **overrides)) is outcome


@pytest.mark.parametrize(
    ("correctness", "completeness", "outcome"),
    [
        (0.6, 0.5, ReviewOutcome.HARD),
        (0.59, 0.9, ReviewOutcome.AGAIN),
        (0.9, 0.49, ReviewOutcome.AGAIN),
    ],
)
def test_partially_correct_boundaries(correctness, completeness, outcome):
    e = evidence(C.PARTIALLY_CORRECT, correctness, completeness=completeness)
    assert resolve_outcome(e) is outcome


def test_low_confidence_is_left_to_the_user():
    assert resolve_outcome(evidence(C.CORRECT, confidence=0.49)) is None
    assert resolve_outcome(evidence(C.CORRECT, confidence=0.5)) is ReviewOutcome.GOOD


@pytest.mark.parametrize(
    "inconsistent",
    [
        evidence(C.CORRECT, 0.2),  # "correct" scored mostly wrong
        evidence(C.WRONG, 0.9),  # "wrong" scored mostly correct
        evidence(C.MISCONCEPTION, 0.95),
    ],
)
def test_self_contradicting_evaluations_are_not_guessed_at(inconsistent):
    assert resolve_outcome(inconsistent) is None


def test_same_evidence_same_outcome_regardless_of_feedback_or_points():
    a = evidence(C.PARTIALLY_CORRECT, 0.7, feedback="Bene", correct_points=["x"])
    b = evidence(C.PARTIALLY_CORRECT, 0.7, feedback="Something else", missing_points=["y"])
    assert resolve_outcome(a) is resolve_outcome(b) is ReviewOutcome.HARD
