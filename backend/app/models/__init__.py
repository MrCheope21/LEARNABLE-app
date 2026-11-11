"""Importing this package registers every model on Base.metadata (needed by Alembic and tests)."""

from app.models.auth import AiUsage, Invitation, PasswordResetToken
from app.models.community import (
    Block,
    Friendship,
    Message,
    Notification,
    Report,
    TagSubscription,
)
from app.models.course import Chapter, Concept, Course, CourseSettings, Topic
from app.models.curriculum import ConceptSource, CurriculumProposal
from app.models.document import Document, DocumentChunk
from app.models.learning import (
    LearningItem,
    LearningItemSource,
    QuestionFormulation,
    ReviewState,
)
from app.models.marketplace import (
    MarketplaceAcquisition,
    MarketplaceListing,
    MarketplaceOrder,
    MarketplaceReview,
    MarketplaceUpdate,
)
from app.models.review import Answer, Evaluation, Review, ReviewSession
from app.models.rewards import DailyActivity, HintReveal, ItemSuccessCounter, XpAward
from app.models.user import User

__all__ = [
    "AiUsage",
    "Answer",
    "Block",
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
    "Friendship",
    "HintReveal",
    "Invitation",
    "ItemSuccessCounter",
    "LearningItem",
    "LearningItemSource",
    "MarketplaceAcquisition",
    "MarketplaceListing",
    "MarketplaceOrder",
    "MarketplaceReview",
    "MarketplaceUpdate",
    "Message",
    "Notification",
    "PasswordResetToken",
    "QuestionFormulation",
    "Report",
    "Review",
    "ReviewSession",
    "ReviewState",
    "TagSubscription",
    "Topic",
    "User",
    "XpAward",
]
