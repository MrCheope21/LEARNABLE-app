from datetime import date
from typing import Literal
from uuid import UUID

from pydantic import BaseModel

from app.models.enums import StudyState
from app.schemas.common import UTCTimestamp

LearnKind = Literal["resume", "study", "activate", "setup", "none"]
NextStepKind = Literal[
    "resume_consolidation",
    "review",
    "learn",
    "activate",
    "setup_course",
    "create_course",
    "all_caught_up",
]


class NextConcept(BaseModel):
    id: UUID
    title: str
    study_state: StudyState


class LearnAction(BaseModel):
    """What the course's Learn button does. resume: an unfinished consolidation batch;
    study: open the next concept with material waiting ("I have studied this concept" is
    there); activate: the next concept needs activating first; setup: the course has no
    concepts yet (add material or questions); none: everything has been learned."""

    kind: LearnKind
    concept: NextConcept | None
    session_id: UUID | None


class CourseCard(BaseModel):
    """One course in the library. Every figure is a count with its own denominator; none of
    them is mastery (docs/XP_AND_ACTIVITY.md §7)."""

    id: UUID
    title: str
    description: str
    language: str
    paused: bool
    # A course from the marketplace: its author's display name.
    marketplace_author: str | None
    created_at: UTCTimestamp
    # The user's last completed answer in this course.
    last_studied_at: UTCTimestamp | None
    concepts_total: int
    # Concepts with trained items, none of them still NEW (all consolidated or learned).
    concepts_studied: int
    # Items in training / of those, no longer NEW.
    items_trained: int
    items_introduced: int
    # Reviewable now (same eligibility as a SCHEDULED_REVIEW session).
    due_now: int
    # NEW items ready for consolidation in active concepts.
    new_ready: int
    learn: LearnAction


class XpSummary(BaseModel):
    total: int
    today: int


class StreakDay(BaseModel):
    date: date
    active: bool


class Streak(BaseModel):
    # Consecutive days with a completed answer, ending today, or yesterday when today has no
    # activity yet (the streak is still alive until today ends).
    current: int
    today_complete: bool
    last_7_days: list[StreakDay]


class DailyGoal(BaseModel):
    target: int
    done: int
    unit: Literal["answers"] = "answers"


class PlannerHorizon(BaseModel):
    key: Literal["now", "1h", "4h", "1d", "3d", "7d"]
    due_by: UTCTimestamp
    # Cumulative: every reviewable item due by `due_by`, overdue ones included.
    items: int


class Planner(BaseModel):
    as_of: UTCTimestamp
    horizons: list[PlannerHorizon]


class WeakMisconception(BaseModel):
    text: str
    # In how many of the item's recent evaluations it appeared.
    count: int
    last_seen: UTCTimestamp


class WeakConcept(BaseModel):
    concept_id: UUID
    concept_title: str
    topic_title: str
    chapter_title: str
    total: int
    misconceptions: list[WeakMisconception]


class WeakSpots(BaseModel):
    """Misconceptions the evaluator keeps finding, by concept: the last few evaluations of each
    item, so something fixed stops showing once it has been answered correctly."""

    concepts: list[WeakConcept]


class ActivityDay(BaseModel):
    date: date
    attempts: int
    xp: int


class Activity(BaseModel):
    """Completed answers per local day, from `start` (a Monday) to `end` (the Sunday of the
    current week). Days after `today` are in the future, not missed."""

    start: date
    end: date
    today: date
    days: list[ActivityDay]


class NextStep(BaseModel):
    kind: NextStepKind
    course_id: UUID | None = None
    course_title: str | None = None
    concept_id: UUID | None = None
    concept_title: str | None = None
    session_id: UUID | None = None
    # review: items due; resume_consolidation: answers left in the batch.
    count: int | None = None
    round: int | None = None
    rounds_total: int | None = None


class Dashboard(BaseModel):
    as_of: UTCTimestamp
    timezone: str
    today: date
    next_step: NextStep
    courses: list[CourseCard]
    xp: XpSummary
    streak: Streak
    goal: DailyGoal
    planner: Planner
    activity: Activity
