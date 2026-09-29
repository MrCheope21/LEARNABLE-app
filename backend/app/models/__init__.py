"""Importing this package registers every model on Base.metadata (needed by Alembic and tests)."""

from app.models.auth import PasswordResetToken
from app.models.course import Chapter, Concept, Course, CourseSettings, Topic
from app.models.curriculum import ConceptSource, CurriculumProposal
from app.models.document import Document, DocumentChunk
from app.models.learning import (
    LearningItem,
    LearningItemSource,
    QuestionFormulation,
    ReviewState,
)
from app.models.review import Answer, Evaluation, Review, ReviewSession
from app.models.rewards import DailyActivity, HintReveal, ItemSuccessCounter, XpAward
from app.models.user import User

__all__ = [
    "Answer",
    "Chapter",
    "Concept",
    "ConceptSource",
    "Course",
    "CourseSettings",
    "CurriculumProposal",
    "DailyActivity",
    "Document",
    "DocumentChunk",
    "Evaluation",
    "HintReveal",
    "ItemSuccessCounter",
    "LearningItem",
    "LearningItemSource",
    "PasswordResetToken",
    "QuestionFormulation",
    "Review",
    "ReviewSession",
    "ReviewState",
    "Topic",
    "User",
    "XpAward",
]
