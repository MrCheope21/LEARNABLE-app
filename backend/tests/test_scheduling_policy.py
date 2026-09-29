"""ChessableStyleSchedulingPolicy in isolation: no database, no AI (docs/PROJECT_SPEC.md §77).

Owner decisions under test: AGAIN → level 1; HARD advances like GOOD and marks the item hard;
EASY skips a level; the ladder is 4h, 1d, 3d, 1w, 2w, 1m, 3m, 6m.
"""

from dataclasses import replace
from datetime import UTC, datetime, timedelta

import pytest

from app.models.enums import MemoryState, ReviewOutcome
from app.services.scheduling.config import CHESSABLE_V1_LADDER
from app.services.scheduling.policy import (
    ChessableStyleSchedulingPolicy,
    MemorySnapshot,
    SchedulingError,
    get_policy,
)

NOW = datetime(2026, 9, 24, 8, 0, tzinfo=UTC)
AGAIN, HARD, GOOD, EASY = (
    ReviewOutcome.AGAIN,
    ReviewOutcome.HARD,
    ReviewOutcome.GOOD,
    ReviewOutcome.EASY,
)
policy = ChessableStyleSchedulingPolicy()


def learned(level: int = 1, state: MemoryState | None = None) -> MemorySnapshot:
    """An encoded item sitting on `level`, due exactly now."""
    snapshot = MemorySnapshot()
    snapshot = policy.process_learning(snapshot, GOOD, NOW - timedelta(days=400)).after
    return replace(
        snapshot,
        level=level,
        state=state or (MemoryState.LEARNING if level == 1 else MemoryState.REVIEW),
        interval=CHESSABLE_V1_LADDER[level - 1],
        due_at=NOW,
    )


def test_ladder_matches_the_specification():
    assert [policy.interval_for(level) for level in range(1, 9)] == [
        timedelta(hours=4),
        timedelta(days=1),
        timedelta(days=3),
        timedelta(weeks=1),
        timedelta(weeks=2),
        timedelta(days=30),
        timedelta(days=91),
        timedelta(days=182),
    ]


# --- Encoding (LEARN) ---


@pytest.mark.parametrize(("outcome", "level"), [(HARD, 1), (GOOD, 1), (EASY, 2)])
def test_successful_encoding_initializes_the_schedule(outcome, level):
    t = policy.process_learning(MemorySnapshot(), outcome, NOW)
    assert t.after.level == level
    assert t.after.due_at == NOW + policy.interval_for(level)
    assert t.after.state is (MemoryState.LEARNING if level == 1 else MemoryState.REVIEW)
    assert (t.after.review_count, t.after.successful_review_count) == (1, 1)


def test_failed_encoding_leaves_the_item_new():
    t = policy.process_learning(MemorySnapshot(), AGAIN, NOW)
    assert t.after.state is MemoryState.NEW
    assert t.after.level == 0
    assert t.after.due_at is None
    assert (t.after.review_count, t.after.failed_review_count) == (1, 1)


def test_learning_an_encoded_item_is_refused():
    with pytest.raises(SchedulingError):
        policy.process_learning(learned(3), GOOD, NOW)


def test_reviewing_a_new_item_is_refused():
    with pytest.raises(SchedulingError):
        policy.process_review(MemorySnapshot(), GOOD, NOW)


# --- Reviews ---


def test_good_advances_one_level():
    t = policy.process_review(learned(3), GOOD, NOW)
    assert (t.after.level, t.after.state) == (4, MemoryState.REVIEW)
    assert t.after.due_at == NOW + timedelta(weeks=1)
    assert t.after.marked_hard is False


def test_hard_advances_like_good_and_marks_the_item_hard():
    t = policy.process_review(learned(3), HARD, NOW)
    assert t.after.level == 4
    assert t.after.due_at == NOW + timedelta(weeks=1)
    assert (t.after.marked_hard, t.after.hard_count) == (True, 1)


def test_easy_skips_a_level():
    t = policy.process_review(learned(3), EASY, NOW)
    assert t.after.level == 5


@pytest.mark.parametrize("start", [2, 5, 8])
def test_again_returns_to_level_1_as_a_lapse(start):
    t = policy.process_review(learned(start), AGAIN, NOW)
    assert (t.after.level, t.after.state) == (1, MemoryState.RELEARNING)
    assert t.after.due_at == NOW + timedelta(hours=4)
    assert (t.after.lapse_count, t.after.failed_review_count) == (1, 1)


def test_failing_at_level_1_is_not_a_lapse():
    t = policy.process_review(learned(1), AGAIN, NOW)
    assert (t.after.level, t.after.state, t.after.lapse_count) == (1, MemoryState.LEARNING, 0)


def test_failing_again_while_relearning_is_not_a_second_lapse():
    relearning = policy.process_review(learned(4), AGAIN, NOW).after
    t = policy.process_review(relearning, AGAIN, NOW + timedelta(hours=5))
    assert (t.after.state, t.after.lapse_count) == (MemoryState.RELEARNING, 1)


def test_recovering_from_relearning():
    relearning = policy.process_review(learned(4), AGAIN, NOW).after
    t = policy.process_review(relearning, GOOD, NOW + timedelta(hours=5))
    assert (t.after.level, t.after.state) == (2, MemoryState.REVIEW)


def test_top_of_the_ladder_is_mastered_and_stays_there():
    t = policy.process_review(learned(7), GOOD, NOW)
    assert (t.after.level, t.after.state) == (8, MemoryState.MASTERED)
    t = policy.process_review(t.after, EASY, NOW + timedelta(days=200))
    assert (t.after.level, t.after.due_at) == (8, NOW + timedelta(days=200 + 182))


def test_mastered_item_can_lapse():
    t = policy.process_review(learned(8, MemoryState.MASTERED), AGAIN, NOW)
    assert (t.after.level, t.after.state, t.after.lapse_count) == (1, MemoryState.RELEARNING, 1)


# --- Marked hard ---


def test_marked_hard_clears_on_good_or_easy_but_survives_again():
    hard = policy.process_review(learned(3), HARD, NOW).after
    assert policy.process_review(hard, GOOD, NOW).after.marked_hard is False
    assert policy.process_review(hard, EASY, NOW).after.marked_hard is False
    failed = policy.process_review(hard, AGAIN, NOW).after
    assert (failed.marked_hard, failed.hard_count) == (True, 1)


# --- Overdue (spec §47) ---


def test_overdue_review_records_lateness_and_keeps_progress():
    item = learned(5)  # due NOW
    late = NOW + timedelta(days=10)
    t = policy.process_review(item, GOOD, late)
    assert t.lateness == timedelta(days=10)
    assert t.after.level == 6  # progress not erased by lateness
    assert t.after.due_at == late + timedelta(days=30)  # counted from the actual review
    assert t.before.due_at == NOW


def test_early_review_has_no_lateness():
    t = policy.process_review(learned(5), GOOD, NOW - timedelta(days=1))
    assert t.lateness == timedelta(0)


# --- Pause / resume (spec §56) ---


def test_resume_restores_the_remaining_interval():
    item = replace(learned(4), due_at=NOW + timedelta(days=3))
    paused = policy.pause(item, NOW)
    resumed = policy.resume(paused, NOW + timedelta(days=20))
    assert resumed.paused_at is None
    assert resumed.due_at == NOW + timedelta(days=23)
    assert (resumed.level, resumed.state) == (item.level, item.state)


def test_pause_and_resume_are_idempotent():
    item = learned(4)
    paused = policy.pause(item, NOW)
    assert policy.pause(paused, NOW + timedelta(days=1)) == paused
    assert policy.resume(item, NOW) == item


# --- Independence (spec §26) ---


def test_items_are_independent_values():
    definition, scenario = learned(6), learned(2)
    failed = policy.process_review(scenario, AGAIN, NOW).after
    assert failed.level == 1
    # The sibling is a separate snapshot: nothing in the policy can reach it.
    assert definition.level == 6


def test_policy_registry():
    assert get_policy().name == "chessable"
    assert get_policy("chessable", "1") is get_policy()
    with pytest.raises(SchedulingError):
        get_policy("fsrs", "1")
