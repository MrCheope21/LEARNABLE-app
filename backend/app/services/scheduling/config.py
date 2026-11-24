"""Scheduling configuration: the only place interval values live (docs/PROJECT_SPEC.md §44).

A ladder is versioned with its policy. Changing any value means a new version (e.g.
`chessable_v2`), because every Review history row records the policy version that produced it.
"""

from datetime import timedelta

CHESSABLE_POLICY_NAME = "chessable"
# v2 (2026-10-04, owner decision): same ladder; HARD keeps the level instead of advancing, and the
# first slip of a learned item drops two levels instead of to level 1 (a second slip in a row
# still goes to level 1). v1 stays registered for the history rows it produced.
# v3 (2026-10-17, owner decision): a failed review sends the item back to level 0 (the timer is
# reset and the item is due at once); it must then be answered well once before it moves on, and
# that good answer puts it on level 1. v2 and v1 stay registered for the history they produced.
CHESSABLE_POLICY_VERSION = "3"
CHESSABLE_V2_VERSION = "2"
CHESSABLE_V1_VERSION = "1"
# How far a first slip drops a learned item under v2.
GENTLE_LAPSE_DROP = 2

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
