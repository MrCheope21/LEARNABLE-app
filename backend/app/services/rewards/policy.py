"""The XP rules (docs/XP_AND_ACTIVITY.md §1-3). Pure: no database, no clock.

    base XP of the nth correct answer to a Learning Item = min(10 * n, 150)
    awarded XP = base, halved when a hint was revealed before answering

XP rewards effort and consistency; it is never read by the scheduler, the outcome resolver or
mastery estimates. Changing a number here means a new XP_POLICY_VERSION, because every award
row records the version that produced it.
"""

from app.models.enums import EvaluationClassification, ReviewOutcome

XP_POLICY_VERSION = "xp_v1"
XP_STEP = 10
XP_CAP = 150
# An item's first three consolidation rounds are XP-eligible; later ones (a second batch that
# repeats an item) are not.
INITIAL_ROUNDS = 3
ROUNDS_PER_ITEM = 3

_SUCCESS = frozenset({ReviewOutcome.HARD, ReviewOutcome.GOOD, ReviewOutcome.EASY})


def base_xp(ordinal: int) -> int:
    if ordinal < 1:
        raise ValueError("the first correct answer has ordinal 1")
    return min(XP_STEP * ordinal, XP_CAP)


def awarded_xp(ordinal: int, hint_used: bool) -> int:
    """Several hints don't compound: the penalty is one halving."""
    base = base_xp(ordinal)
    return base // 2 if hint_used else base


def is_correct(
    classification: EvaluationClassification | None, resolved_outcome: ReviewOutcome | None
) -> bool:
    """Correct for XP: the AI classified the answer CORRECT and the deterministic resolver turned
    that into a success. PARTIALLY_CORRECT never counts (no XP, the success counter neither
    advances nor resets), even when the resolver schedules it as HARD. The user's own grade is
    not an input: a self-selected grade can't create correctness XP."""
    return (
        classification is EvaluationClassification.CORRECT
        and resolved_outcome is not None
        and resolved_outcome in _SUCCESS
    )
