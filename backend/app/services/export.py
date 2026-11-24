"""A copy of everything the site holds about one account, as JSON (the privacy notice's
"get a copy of your data"): the profile, the user's own courses with their questions, what
they answered and how it was graded, XP and study days, friends, messages, reviews, purchases.

Rows are written as they are stored, column by column, so a new column is exported without
touching this file. Left out: secrets (password hash, payment account id), other people's
email addresses, the text extracted from uploaded files (the files themselves are the user's
own) and the content of courses that belong to another author.
"""

import uuid
from datetime import date, datetime
from enum import Enum
from typing import Any

from sqlalchemy import inspect, or_, select
from sqlalchemy.orm import Session

from app.db.types import utc_now
from app.models import (
    Answer,
    Block,
    Chapter,
    Concept,
    Course,
    DailyActivity,
    Document,
    Evaluation,
    Friendship,
    LearningItem,
    MarketplaceAcquisition,
    MarketplaceListing,
    MarketplaceOrder,
    MarketplaceReview,
    Message,
    Notification,
    QuestionFormulation,
    Report,
    Review,
    ReviewState,
    TagSubscription,
    Topic,
    User,
    XpAward,
)

SECRET = {"hashed_password", "payout_account_id", "token_version", "snapshot"}


def _value(value: Any) -> Any:
    if isinstance(value, uuid.UUID):
        return str(value)
    if isinstance(value, datetime | date):
        return value.isoformat()
    if isinstance(value, Enum):
        return value.value
    return value


def _row(row: Any) -> dict[str, Any]:
    return {
        column.key: _value(getattr(row, column.key))
        for column in inspect(type(row)).columns
        if column.key not in SECRET
    }


def _rows(db: Session, model: Any, *where: Any) -> list[dict[str, Any]]:
    return [_row(row) for row in db.scalars(select(model).where(*where)).all()]


def export_account(db: Session, user: User) -> dict[str, Any]:
    me = user.id
    courses = db.scalars(select(Course).where(Course.user_id == me)).all()
    all_ids = [c.id for c in courses]
    # A course from the marketplace is its author's work: only the user's study of it is theirs.
    own_ids = [c.id for c in courses if c.marketplace_listing_id is None]
    return {
        "exported_at": utc_now().isoformat(),
        "account": _row(user),
        "courses": [_row(c) for c in courses],
        "chapters": _rows(db, Chapter, Chapter.course_id.in_(own_ids)),
        "topics": _rows(db, Topic, Topic.course_id.in_(own_ids)),
        "concepts": _rows(db, Concept, Concept.course_id.in_(own_ids)),
        "learning_items": _rows(db, LearningItem, LearningItem.course_id.in_(own_ids)),
        "questions": _rows(db, QuestionFormulation, QuestionFormulation.course_id.in_(own_ids)),
        "uploaded_files": _rows(db, Document, Document.course_id.in_(own_ids)),
        "answers": _rows(db, Answer, Answer.user_id == me),
        "evaluations": _rows(db, Evaluation, Evaluation.course_id.in_(all_ids)),
        "reviews": _rows(db, Review, Review.course_id.in_(all_ids)),
        "schedule": _rows(db, ReviewState, ReviewState.course_id.in_(all_ids)),
        "xp": _rows(db, XpAward, XpAward.user_id == me),
        "study_days": _rows(db, DailyActivity, DailyActivity.user_id == me),
        "friendships": _rows(
            db, Friendship, or_(Friendship.requester_id == me, Friendship.addressee_id == me)
        ),
        "blocked": _rows(db, Block, Block.blocker_id == me),
        "messages": _rows(db, Message, or_(Message.sender_id == me, Message.recipient_id == me)),
        "notifications": _rows(db, Notification, Notification.user_id == me),
        "followed_tags": _rows(db, TagSubscription, TagSubscription.user_id == me),
        "reports_sent": _rows(db, Report, Report.reporter_id == me),
        "published_courses": _rows(db, MarketplaceListing, MarketplaceListing.author_id == me),
        "courses_from_marketplace": _rows(
            db, MarketplaceAcquisition, MarketplaceAcquisition.user_id == me
        ),
        "course_reviews": _rows(db, MarketplaceReview, MarketplaceReview.user_id == me),
        "purchases": _rows(db, MarketplaceOrder, MarketplaceOrder.buyer_id == me),
        "sales": _rows(db, MarketplaceOrder, MarketplaceOrder.seller_id == me),
    }
