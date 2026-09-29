from uuid import UUID

from pydantic import BaseModel

from app.models.enums import StudyState


class CurriculumProgress(BaseModel):
    """How far through the material the user is (study states, spec §22). Says nothing about
    memory."""

    concepts: int
    not_studied: int
    studied: int
    active: int
    paused: int
    completed: int


class MemoryProgress(BaseModel):
    """How well the trained material is retained (spec §23, §52). `mastery` is an estimate
    (0-1), not a measurement: the mean over trained items of level / top level, discounted
    for lapses. Null when nothing is trained yet."""

    items_trained: int
    new: int
    learning: int
    review: int
    relearning: int
    mastered: int
    marked_hard: int
    mastery: float | None


class ConceptProgress(BaseModel):
    id: UUID
    title: str
    study_state: StudyState
    memory: MemoryProgress
    # Recent distinct misconceptions found in this Concept's answers (spec §40).
    misconceptions: list[str]


class TopicProgress(BaseModel):
    id: UUID
    title: str
    curriculum: CurriculumProgress
    memory: MemoryProgress
    concepts: list[ConceptProgress]


class ChapterProgress(BaseModel):
    id: UUID
    title: str
    curriculum: CurriculumProgress
    memory: MemoryProgress
    topics: list[TopicProgress]


class ReviewLoad(BaseModel):
    """Upcoming reviews of items that can be reviewed now (active, trained, not paused), by the
    user's calendar day. Buckets don't overlap: everything due today is due_now + later_today.
    """

    due_now: int
    # Part of due_now: due before the start of the user's today.
    overdue: int
    later_today: int
    tomorrow: int
    next_7_days: int  # after tomorrow, up to 7 days from today
    later: int
    new_to_learn: int


class CourseProgress(BaseModel):
    course_id: UUID
    curriculum: CurriculumProgress
    memory: MemoryProgress
    review_load: ReviewLoad
    chapters: list[ChapterProgress]


class WeakConcept(BaseModel):
    id: UUID
    title: str
    lapses: int
    marked_hard: int


class CourseSummary(BaseModel):
    course_id: UUID
    title: str
    review_load: ReviewLoad
    active_concepts: int
    mastery: float | None
    # Up to 3 Concepts with the most lapses and hard-marked items.
    weak_concepts: list[WeakConcept]


class HomeSummary(BaseModel):
    """The signed-in user's day, per Course. `totals` sums the Courses' review loads; nothing
    else is combined across Courses."""

    totals: ReviewLoad
    courses: list[CourseSummary]
