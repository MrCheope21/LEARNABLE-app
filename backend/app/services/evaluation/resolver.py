"""ReviewOutcomeResolver: turns AI evaluation evidence into a review outcome, deterministically.

    AI Evaluation (semantic evidence) → ReviewOutcomeResolver → AGAIN | HARD | GOOD | None
    → (user override) → SchedulingPolicy

The AI never chooses the outcome (spec §42). These rules do, so the same evidence always gives
the same outcome whichever model produced it, and changing them is a versioned code change,
never a prompt tweak. `None` means "can't decide": the user grades the answer themselves.

Decisions (2026-09-24, documented in SCHEDULING.md §3b):
- EASY is never resolved from an evaluation. Correctness is observable in an answer; ease of
  recall isn't. The user can grade EASY themselves.
- HARD is a correct but incomplete or shaky answer (owner: "correct, with difficulty").
- Insufficient context, UNCERTAIN, low confidence, or scores that contradict the
  classification all resolve to None rather than a guess.
"""

from dataclasses import dataclass

from app.ai.schemas import EvaluationOutput
from app.models.enums import EvaluationClassification, ReviewOutcome

RESOLVER_VERSION = "outcome_resolver_v1"


@dataclass(frozen=True)
class ResolverThresholds:
    min_confidence: float = 0.5
    # A PARTIALLY_CORRECT answer this good is a success, graded HARD; below it, AGAIN.
    partial_min_correctness: float = 0.6
    partial_min_completeness: float = 0.5
    # A CORRECT answer below either of these is graded HARD instead of GOOD.
    good_min_completeness: float = 0.7
    good_min_understanding: float = 0.6
    # Scores contradicting the classification make the evaluation unusable.
    correct_min_correctness: float = 0.6
    wrong_max_correctness: float = 0.6


THRESHOLDS = ResolverThresholds()

# "Green" is a score the answer screen shows as Strong; the answer is judged on four of them.
GREEN_SCORE = 0.8
GREEN_NEEDED = 3


def green_count(evaluation: EvaluationOutput) -> int:
    scores = (
        evaluation.correctness,
        evaluation.completeness,
        evaluation.conceptual_understanding,
        evaluation.precision,
    )
    return sum(score >= GREEN_SCORE for score in scores)


def repeat_offered(
    evaluation: EvaluationOutput,
    outcome: ReviewOutcome | None,
    thresholds: ResolverThresholds = THRESHOLDS,
) -> bool:
    """Owner decision (2026-10-10): an answer that is green on at least 3 of the 4 scores but
    would not be graded GOOD (so the schedule would hold or reset) is not graded yet: the student
    reviews the reference answer and repeats it, and the attempt then counts as a correct first
    answer. Only for answers the evaluator is sure about and calls CORRECT or PARTIALLY_CORRECT;
    inconclusive evaluations stay with the student's own grade."""
    c = EvaluationClassification
    return (
        outcome in (ReviewOutcome.AGAIN, ReviewOutcome.HARD)
        and evaluation.context_sufficient
        and evaluation.confidence >= thresholds.min_confidence
        and evaluation.classification in (c.CORRECT, c.PARTIALLY_CORRECT)
        and green_count(evaluation) >= GREEN_NEEDED
    )


def resolve_outcome(
    evaluation: EvaluationOutput, thresholds: ResolverThresholds = THRESHOLDS
) -> ReviewOutcome | None:
    c = EvaluationClassification
    if not evaluation.context_sufficient:
        return None
    if (
        evaluation.classification is c.UNCERTAIN
        or evaluation.confidence < thresholds.min_confidence
    ):
        return None
    if evaluation.classification in (c.WRONG, c.MISCONCEPTION):
        if evaluation.correctness > thresholds.wrong_max_correctness:
            return None  # "wrong" but scored mostly correct: inconsistent
        return ReviewOutcome.AGAIN
    if evaluation.classification is c.PARTIALLY_CORRECT:
        if (
            evaluation.correctness >= thresholds.partial_min_correctness
            and evaluation.completeness >= thresholds.partial_min_completeness
        ):
            return ReviewOutcome.HARD
        return ReviewOutcome.AGAIN
    # CORRECT
    if evaluation.correctness < thresholds.correct_min_correctness:
        return None  # "correct" but scored mostly wrong: inconsistent
    if (
        evaluation.completeness < thresholds.good_min_completeness
        or evaluation.conceptual_understanding < thresholds.good_min_understanding
    ):
        return ReviewOutcome.HARD
    return ReviewOutcome.GOOD
