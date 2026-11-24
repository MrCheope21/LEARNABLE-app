"""The XP rules (docs/XP_AND_ACTIVITY.md §1-3). Pure: no database, no clock.

    base XP of a correct answer = 10 * (the item's level when it was asked + 1)
                                  (level 0 → 10, level 1 → 20 … level 8 → 90)
    awarded XP = base, halved when a hint was revealed before answering

xp_v2 (owner decision, 2026-11-10). xp_v1 paid by the count of correct answers (10n, capped at
150), so the reward kept growing even after a failed review had sent the item back to level 0.
Now a level has one reward: an item that falls back earns what that level earns.

XP rewards effort and consistency; it is never read by the scheduler, the outcome resolver or
mastery estimates. Changing a number here means a new XP_POLICY_VERSION, because every award
row records the version that produced it.
"""

from app.models.enums import EvaluationClassification, ReviewOutcome

XP_POLICY_VERSION = "xp_v2"
XP_STEP = 10
XP_CAP = 150
# An item's first three consolidation rounds are XP-eligible; later ones (a second batch that
# repeats an item) are not.
INITIAL_ROUNDS = 3
ROUNDS_PER_ITEM = 3

_SUCCESS = frozenset({ReviewOutcome.HARD, ReviewOutcome.GOOD, ReviewOutcome.EASY})


def base_xp(level: int) -> int:
    """The reward of a correct answer to an item asked at `level` (0 = new or relearning)."""
    if level < 0:
        raise ValueError("levels start at 0")
    return min(XP_STEP * (level + 1), XP_CAP)


def awarded_xp(level: int, hint_used: bool) -> int:
    """Several hints don't compound: the penalty is one halving."""
    base = base_xp(level)
    return base // 2 if hint_used else base


def is_correct(
    classification: EvaluationClassification | None,
    resolved_outcome: ReviewOutcome | None,
    self_grade: ReviewOutcome | None = None,
) -> bool:
    """Correct for XP: the AI classified the answer CORRECT and the deterministic resolver turned
    that into a success; or the student graded it themselves as a success (owner decision,
    2026-10-04: a self-graded answer earns XP the normal way). PARTIALLY_CORRECT from the AI
    never counts, even when the resolver schedules it as HARD."""
    if self_grade is not None:
        return self_grade in _SUCCESS
    return (
        classification is EvaluationClassification.CORRECT
        and resolved_outcome is not None
        and resolved_outcome in _SUCCESS
    )
