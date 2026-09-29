"""Scheduling configuration: the only place interval values live (docs/PROJECT_SPEC.md §44).

A ladder is versioned with its policy. Changing any value means a new version (e.g.
`chessable_v2`), because every Review history row records the policy version that produced it.
"""

from datetime import timedelta

CHESSABLE_POLICY_NAME = "chessable"
CHESSABLE_POLICY_VERSION = "1"

# Level → interval until the next review. Level 1 is where an item lands right after encoding.
CHESSABLE_V1_LADDER: tuple[timedelta, ...] = (
    timedelta(hours=4),  # 1
    timedelta(days=1),  # 2
    timedelta(days=3),  # 3
    timedelta(weeks=1),  # 4
    timedelta(weeks=2),  # 5
    timedelta(days=30),  # 6: "1 month"
    timedelta(days=91),  # 7: "3 months"
    timedelta(days=182),  # 8: "6 months"
)

# Progress displays only (never scheduling): each lapse discounts an item's mastery estimate.
MASTERY_LAPSE_DISCOUNT = 0.25
