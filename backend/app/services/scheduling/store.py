"""Moves memory state between ReviewState rows and the pure SchedulingPolicy."""

from datetime import datetime, timedelta

from app.models.enums import MemoryState
from app.models.learning import ReviewState
from app.services.scheduling.policy import MemorySnapshot, SchedulingPolicy, get_policy


def policy_for(state: ReviewState) -> SchedulingPolicy:
    """The policy (and version) the item was started on, even if the default changed since."""
    return get_policy(state.scheduling_policy, state.scheduling_policy_version)


def snapshot_of(state: ReviewState) -> MemorySnapshot:
    return MemorySnapshot(
        state=state.state,
        level=state.level,
        interval=None
        if state.interval_seconds is None
        else timedelta(seconds=state.interval_seconds),
        due_at=state.due_at,
        last_reviewed_at=state.last_reviewed_at,
        review_count=state.review_count,
        successful_review_count=state.successful_review_count,
        failed_review_count=state.failed_review_count,
        lapse_count=state.lapse_count,
        hard_count=state.hard_count,
        marked_hard=state.marked_hard,
        paused_at=state.paused_at,
    )


def store(state: ReviewState, snapshot: MemorySnapshot) -> None:
    state.state = snapshot.state
    state.level = snapshot.level
    state.interval_seconds = (
        None if snapshot.interval is None else int(snapshot.interval.total_seconds())
    )
    state.due_at = snapshot.due_at
    state.last_reviewed_at = snapshot.last_reviewed_at
    state.review_count = snapshot.review_count
    state.successful_review_count = snapshot.successful_review_count
    state.failed_review_count = snapshot.failed_review_count
    state.lapse_count = snapshot.lapse_count
    state.hard_count = snapshot.hard_count
    state.marked_hard = snapshot.marked_hard
    state.paused_at = snapshot.paused_at


def snapshot_to_json(snapshot: MemorySnapshot) -> dict[str, object]:
    """For the history row: the full state before a review, so an override can be replayed
    from exactly where the item was."""
    return {
        "state": snapshot.state.value,
        "level": snapshot.level,
        "interval_seconds": None
        if snapshot.interval is None
        else int(snapshot.interval.total_seconds()),
        "due_at": snapshot.due_at.isoformat() if snapshot.due_at else None,
        "last_reviewed_at": snapshot.last_reviewed_at.isoformat()
        if snapshot.last_reviewed_at
        else None,
        "review_count": snapshot.review_count,
        "successful_review_count": snapshot.successful_review_count,
        "failed_review_count": snapshot.failed_review_count,
        "lapse_count": snapshot.lapse_count,
        "hard_count": snapshot.hard_count,
        "marked_hard": snapshot.marked_hard,
        "paused_at": snapshot.paused_at.isoformat() if snapshot.paused_at else None,
    }


def snapshot_from_json(data: dict[str, object]) -> MemorySnapshot:
    def when(key: str) -> datetime | None:
        value = data.get(key)
        return datetime.fromisoformat(value) if isinstance(value, str) else None

    def number(key: str) -> int:
        value = data.get(key)
        return value if isinstance(value, int) else 0

    interval = data.get("interval_seconds")
    return MemorySnapshot(
        state=MemoryState(str(data["state"])),
        level=number("level"),
        interval=timedelta(seconds=interval) if isinstance(interval, int) else None,
        due_at=when("due_at"),
        last_reviewed_at=when("last_reviewed_at"),
        review_count=number("review_count"),
        successful_review_count=number("successful_review_count"),
        failed_review_count=number("failed_review_count"),
        lapse_count=number("lapse_count"),
        hard_count=number("hard_count"),
        marked_hard=bool(data.get("marked_hard")),
        paused_at=when("paused_at"),
    )
