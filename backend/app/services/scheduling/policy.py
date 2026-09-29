"""SchedulingPolicy: the only code that decides memory state, level, interval and due date
(docs/PROJECT_SPEC.md §42-48, docs/SCHEDULING.md).

Pure: no database, no AI, no clock. Callers pass `now` and a MemorySnapshot and persist the
returned one. That keeps every transition deterministic, testable and auditable, and lets other
policies (FSRS, adaptive) implement the same protocol later.

Chessable-style rules (owner decisions, 2026-09-24):
- encoding (LEARN) that isn't AGAIN puts the item on level 1 (EASY: level 2);
- GOOD and HARD advance one level; HARD also marks the item hard; EASY advances two;
- AGAIN returns to level 1 (a lapse if the item had been learned);
- the next due date counts from the moment of the review, late or not; lateness is recorded.
"""

from dataclasses import dataclass, replace
from datetime import datetime, timedelta
from typing import Protocol

from app.models.enums import MemoryState, ReviewOutcome
from app.services.scheduling.config import (
    CHESSABLE_POLICY_NAME,
    CHESSABLE_POLICY_VERSION,
    CHESSABLE_V1_LADDER,
    MASTERY_LAPSE_DISCOUNT,
)


class SchedulingError(ValueError):
    """A transition the policy doesn't allow, e.g. reviewing an item that was never learned."""


@dataclass(frozen=True)
class MemorySnapshot:
    """A Learning Item's memory state (spec §48). Level 0 means not encoded yet."""

    state: MemoryState = MemoryState.NEW
    level: int = 0
    interval: timedelta | None = None
    due_at: datetime | None = None
    last_reviewed_at: datetime | None = None
    review_count: int = 0
    successful_review_count: int = 0
    failed_review_count: int = 0
    lapse_count: int = 0
    hard_count: int = 0
    # While the most recent answer was HARD (GOOD/EASY clear it; AGAIN doesn't).
    marked_hard: bool = False
    paused_at: datetime | None = None


@dataclass(frozen=True)
class Transition:
    before: MemorySnapshot
    after: MemorySnapshot
    outcome: ReviewOutcome
    reviewed_at: datetime
    # How long after `before.due_at` the review happened; 0 when on time or not due yet.
    lateness: timedelta


class SchedulingPolicy(Protocol):
    name: str
    version: str

    def process_learning(
        self, snapshot: MemorySnapshot, outcome: ReviewOutcome, now: datetime
    ) -> Transition:
        """First retrieval of a NEW item (LEARN). Success initializes its schedule."""
        ...

    def process_review(
        self, snapshot: MemorySnapshot, outcome: ReviewOutcome, now: datetime
    ) -> Transition:
        """A review of an encoded item."""
        ...

    def pause(self, snapshot: MemorySnapshot, now: datetime) -> MemorySnapshot: ...

    def resume(self, snapshot: MemorySnapshot, now: datetime) -> MemorySnapshot: ...

    def mastery_estimate(self, snapshot: MemorySnapshot) -> float:
        """0-1: how well the item is likely retained, in this policy's own terms (spec §52).
        An estimate for progress displays, never used for scheduling."""
        ...


class ChessableStyleSchedulingPolicy:
    name = CHESSABLE_POLICY_NAME
    version = CHESSABLE_POLICY_VERSION

    def __init__(self, ladder: tuple[timedelta, ...] = CHESSABLE_V1_LADDER) -> None:
        if not ladder:
            raise ValueError("the ladder needs at least one level")
        self._ladder = ladder

    @property
    def max_level(self) -> int:
        return len(self._ladder)

    def interval_for(self, level: int) -> timedelta:
        return self._ladder[level - 1]

    def process_learning(
        self, snapshot: MemorySnapshot, outcome: ReviewOutcome, now: datetime
    ) -> Transition:
        if snapshot.state is not MemoryState.NEW:
            raise SchedulingError("only a NEW item can be learned; review it instead")
        counted = _count(snapshot, outcome, now)
        if outcome is ReviewOutcome.AGAIN:
            # Not encoded yet: it stays NEW and comes back in the next LEARN session.
            return Transition(snapshot, counted, outcome, now, timedelta(0))
        level = min(2 if outcome is ReviewOutcome.EASY else 1, self.max_level)
        return Transition(snapshot, self._place(counted, level, now), outcome, now, timedelta(0))

    def process_review(
        self, snapshot: MemorySnapshot, outcome: ReviewOutcome, now: datetime
    ) -> Transition:
        if snapshot.state is MemoryState.NEW:
            raise SchedulingError("a NEW item must be learned before it can be reviewed")
        lateness = max(now - snapshot.due_at, timedelta(0)) if snapshot.due_at else timedelta(0)
        counted = _count(snapshot, outcome, now)
        if outcome is ReviewOutcome.AGAIN:
            # A lapse is forgetting something already learned; failing again while relearning,
            # or at level 1, isn't a new one.
            lapse = snapshot.state in (MemoryState.REVIEW, MemoryState.MASTERED)
            learned_before = lapse or snapshot.state is MemoryState.RELEARNING
            after = self._place(
                replace(counted, lapse_count=counted.lapse_count + (1 if lapse else 0)), 1, now
            )
            if learned_before:
                after = replace(after, state=MemoryState.RELEARNING)
            return Transition(snapshot, after, outcome, now, lateness)
        step = 2 if outcome is ReviewOutcome.EASY else 1
        level = min(snapshot.level + step, self.max_level)
        return Transition(snapshot, self._place(counted, level, now), outcome, now, lateness)

    def pause(self, snapshot: MemorySnapshot, now: datetime) -> MemorySnapshot:
        return snapshot if snapshot.paused_at else replace(snapshot, paused_at=now)

    def resume(self, snapshot: MemorySnapshot, now: datetime) -> MemorySnapshot:
        """Restores the previous state (spec §56): the time spent paused is added to the due
        date, so a paused item doesn't come back overdue."""
        if snapshot.paused_at is None:
            return snapshot
        due = snapshot.due_at + (now - snapshot.paused_at) if snapshot.due_at else None
        return replace(snapshot, paused_at=None, due_at=due)

    def mastery_estimate(self, snapshot: MemorySnapshot) -> float:
        """Level over top level, discounted per lapse (1 lapse: 0.8x, 2: 0.67x, ...)."""
        if snapshot.state is MemoryState.NEW:
            return 0.0
        return (snapshot.level / self.max_level) / (
            1 + MASTERY_LAPSE_DISCOUNT * snapshot.lapse_count
        )

    def _place(self, snapshot: MemorySnapshot, level: int, now: datetime) -> MemorySnapshot:
        interval = self.interval_for(level)
        if level == self.max_level:
            state = MemoryState.MASTERED
        elif level == 1:
            state = MemoryState.LEARNING
        else:
            state = MemoryState.REVIEW
        return replace(snapshot, state=state, level=level, interval=interval, due_at=now + interval)


def _count(snapshot: MemorySnapshot, outcome: ReviewOutcome, now: datetime) -> MemorySnapshot:
    failed = outcome is ReviewOutcome.AGAIN
    hard = outcome is ReviewOutcome.HARD
    return replace(
        snapshot,
        last_reviewed_at=now,
        review_count=snapshot.review_count + 1,
        successful_review_count=snapshot.successful_review_count + (0 if failed else 1),
        failed_review_count=snapshot.failed_review_count + (1 if failed else 0),
        hard_count=snapshot.hard_count + (1 if hard else 0),
        marked_hard=hard or (snapshot.marked_hard if failed else False),
    )


_POLICIES: dict[tuple[str, str], SchedulingPolicy] = {
    (CHESSABLE_POLICY_NAME, CHESSABLE_POLICY_VERSION): ChessableStyleSchedulingPolicy(),
}


def get_policy(name: str = CHESSABLE_POLICY_NAME, version: str | None = None) -> SchedulingPolicy:
    """The policy a Learning Item is scheduled with. Items keep the version they started on."""
    if version is None:
        version = CHESSABLE_POLICY_VERSION if name == CHESSABLE_POLICY_NAME else ""
    try:
        return _POLICIES[(name, version)]
    except KeyError:
        raise SchedulingError(f"unknown scheduling policy {name} v{version}") from None
