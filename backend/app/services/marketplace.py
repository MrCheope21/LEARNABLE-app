"""The course marketplace: authors publish a course, others get access to it.

A listing carries a snapshot of the study content only: the chapter/topic/concept structure, each
learning item (expected answer, key points, priority, answer format), its questions, and the
reference drawings of drawing questions. Never the author's uploaded documents (so there is
nothing to download), answers, progress or schedule.

Getting access puts a course in the user's account that mirrors the listing: read-only
(services/managed_courses.py), updated whenever the author republishes, matched row by row
through `origin_key` so the user's study (activation, pauses, schedule, answers, XP, their own
priority for each question) carries over. Access is for good: removing the course from one's
courses and adding it back is free, and unpublishing only stops new people from getting it.

Before getting access, a listing shows its presentation and size only (schemas/marketplace.py).
"""

import uuid
from typing import Any

from sqlalchemy import func, or_, select
from sqlalchemy.orm import Session

from app.core.errors import ConflictError, InvalidRequestError, NotFoundError
from app.db.types import utc_now
from app.models.course import Chapter, Concept, Course, CourseSettings, Topic
from app.models.enums import ItemGenerationStatus, LearningItemRole, QuestionType
from app.models.learning import LearningItem, QuestionFormulation
from app.models.marketplace import MarketplaceAcquisition, MarketplaceListing
from app.models.user import User
from app.schemas.learning import LearningItemCreate, QuestionCreate
from app.schemas.marketplace import (
    SIZE_BOUNDS,
    Category,
    ChapterSize,
    CourseOrigin,
    Level,
    ListingDetail,
    ListingInfo,
    ListingPublish,
    ListingSize,
    ListingSort,
    ListingSummary,
    MyListing,
)
from app.services import drawings
from app.services.courses.service import get_owned_course
from app.services.learning.service import new_item
from app.services.managed_courses import ensure_editable, syncing
from app.storage.documents import DocumentStorage

MAX_ITEMS = 5000
DRAFT, PUBLISHED, UNPUBLISHED = "DRAFT", "PUBLISHED", "UNPUBLISHED"


def _listing_drawing_key(listing_id: uuid.UUID, version: int, item_key: str) -> str:
    return f"marketplace/{listing_id}/v{version}/{item_key}"


# --- Publishing (the author) ---


def publish(
    db: Session,
    storage: DocumentStorage,
    user_id: uuid.UUID,
    course_id: uuid.UUID,
    payload: ListingPublish,
) -> MyListing:
    """Publishes the course, or republishes it as a new version: everyone with access gets it."""
    course = get_owned_course(db, user_id, course_id)
    # A course from the marketplace is someone else's work.
    ensure_editable(course)
    item_count = db.scalar(
        select(func.count()).select_from(LearningItem).where(LearningItem.course_id == course.id)
    )
    if not item_count:
        raise InvalidRequestError("This course has no questions yet: add some before publishing.")
    if item_count > MAX_ITEMS:
        raise InvalidRequestError(
            f"Courses with more than {MAX_ITEMS} questions can't be published."
        )
    listing = _listing_of(db, course)
    old_drawings = [i["key"] for i in _snapshot_items(listing.snapshot) if i["drawing_type"]]
    old_version = listing.version
    listing.version += 1
    _set_info(listing, payload)
    listing.language = course.language
    listing.status = PUBLISHED
    if listing.published_at is None:
        listing.published_at = utc_now()
    listing.snapshot = _snapshot(db, storage, course, listing)
    listing.chapter_count = len(listing.snapshot["chapters"])
    listing.item_count = item_count
    db.flush()
    _sync_all(db, storage, listing)
    db.commit()
    # The previous version's drawings, now that every course with access has the new ones.
    for key in old_drawings:
        storage.delete(_listing_drawing_key(listing.id, old_version, key))
    db.refresh(listing)
    return _mine(db, listing)


def save_info(
    db: Session, user_id: uuid.UUID, course_id: uuid.UUID, payload: ListingInfo
) -> MyListing:
    """Saves the course's sales page. Before publishing it's a draft nobody else sees; once
    published, the new text shows at once (no new version: the content doesn't change)."""
    course = get_owned_course(db, user_id, course_id)
    ensure_editable(course)
    listing = _listing_of(db, course)
    _set_info(listing, payload)
    if listing.status == DRAFT:
        listing.language = course.language
    else:
        # The title and description shown on each course with access.
        with syncing(db):
            for managed in db.scalars(
                select(Course).where(Course.marketplace_listing_id == listing.id)
            ):
                managed.title = listing.title
                managed.description = listing.description[:2000]
            db.flush()
    db.commit()
    db.refresh(listing)
    return _mine(db, listing)


def _listing_of(db: Session, course: Course) -> MarketplaceListing:
    """The course's listing, created as an empty draft the first time."""
    listing = db.scalar(
        select(MarketplaceListing).where(MarketplaceListing.source_course_id == course.id)
    )
    if listing is None:
        listing = MarketplaceListing(
            id=uuid.uuid4(),
            author_id=course.user_id,
            source_course_id=course.id,
            language=course.language,
            status=DRAFT,
            version=0,
            snapshot={},
        )
        db.add(listing)
    return listing


def _set_info(listing: MarketplaceListing, info: ListingInfo) -> None:
    listing.title = info.title
    listing.subtitle = info.subtitle
    listing.description = info.description
    listing.outcomes = [o.strip() for o in info.outcomes if o.strip()]
    listing.audience = info.audience
    listing.level = info.level.value
    listing.category = info.category.value
    listing.tags = list(dict.fromkeys(t.strip() for t in info.tags if t.strip()))


def unpublish(db: Session, user_id: uuid.UUID, listing_id: uuid.UUID) -> MyListing:
    """Hidden from the marketplace; whoever already has access keeps it."""
    listing = _owned_listing(db, user_id, listing_id)
    if listing.status != PUBLISHED:
        raise ConflictError("This course isn't published.", details={"reason": "not_published"})
    listing.status = UNPUBLISHED
    db.commit()
    db.refresh(listing)
    return _mine(db, listing)


def my_listings(db: Session, user_id: uuid.UUID) -> list[MyListing]:
    listings = db.scalars(
        select(MarketplaceListing)
        .where(MarketplaceListing.author_id == user_id)
        .order_by(MarketplaceListing.updated_at.desc())
    ).all()
    return [_mine(db, listing) for listing in listings]


def listing_for_course(db: Session, user_id: uuid.UUID, course_id: uuid.UUID) -> MyListing | None:
    course = get_owned_course(db, user_id, course_id)
    listing = db.scalar(
        select(MarketplaceListing).where(MarketplaceListing.source_course_id == course.id)
    )
    return _mine(db, listing) if listing else None


def _owned_listing(db: Session, user_id: uuid.UUID, listing_id: uuid.UUID) -> MarketplaceListing:
    listing = db.get(MarketplaceListing, listing_id)
    if listing is None or listing.author_id != user_id:
        raise NotFoundError("Listing not found")
    return listing


def _rows(db: Session, model: Any, course_id: uuid.UUID) -> list[Any]:
    return list(db.scalars(select(model).where(model.course_id == course_id)).all())


def _ordered(rows: list[Any], parent: str) -> dict[uuid.UUID, list[Any]]:
    out: dict[uuid.UUID, list[Any]] = {}
    for row in sorted(rows, key=lambda r: (r.order, r.created_at)):
        out.setdefault(getattr(row, parent), []).append(row)
    return out


def _snapshot(
    db: Session, storage: DocumentStorage, course: Course, listing: MarketplaceListing
) -> dict[str, Any]:
    """Keys are the author's row ids: stable across versions, so each acquirer's rows keep
    matching (and keep their study) when the author edits."""
    topics = _ordered(_rows(db, Topic, course.id), "chapter_id")
    concepts = _ordered(_rows(db, Concept, course.id), "topic_id")
    items = _ordered(_rows(db, LearningItem, course.id), "concept_id")
    chapters = sorted(_rows(db, Chapter, course.id), key=lambda r: (r.order, r.created_at))
    return {
        "chapters": [
            {
                "key": chapter.id.hex,
                "title": chapter.title,
                "description": chapter.description,
                "topics": [
                    {
                        "key": topic.id.hex,
                        "title": topic.title,
                        "description": topic.description,
                        "concepts": [
                            {
                                "key": concept.id.hex,
                                "title": concept.title,
                                "description": concept.description,
                                "items": [
                                    _item(storage, listing, item)
                                    for item in items.get(concept.id, [])
                                ],
                            }
                            for concept in concepts.get(topic.id, [])
                        ],
                    }
                    for topic in topics.get(chapter.id, [])
                ],
            }
            for chapter in chapters
        ]
    }


def _item(
    storage: DocumentStorage, listing: MarketplaceListing, item: LearningItem
) -> dict[str, Any]:
    key = item.id.hex
    drawing_type = None
    if item.answer_format == "DRAWING" and item.reference_drawing_type:
        # The listing keeps its own copy: the author can change or delete theirs later.
        storage.save(
            _listing_drawing_key(listing.id, listing.version, key),
            storage.load(drawings.reference_key(item)),
        )
        drawing_type = item.reference_drawing_type
    return {
        "key": key,
        "title": item.title,
        "objective": item.objective,
        "expected_knowledge": item.expected_knowledge,
        "essential_points": list(item.essential_points),
        "role": item.role.value,
        "difficulty": item.difficulty,
        "priority": item.priority,
        "drawing_type": drawing_type,
        "questions": [
            {"question_type": q.question_type.value, "text": q.text} for q in item.questions
        ],
    }


def _snapshot_items(snapshot: dict[str, Any]) -> list[dict[str, Any]]:
    return [
        item
        for chapter in snapshot.get("chapters", [])
        for topic in chapter["topics"]
        for concept in topic["concepts"]
        for item in concept["items"]
    ]


# --- Browsing (anyone signed in) ---


def browse(
    db: Session,
    user_id: uuid.UUID,
    *,
    query: str | None = None,
    category: Category | None = None,
    language: str | None = None,
    size: ListingSize | None = None,
    level: Level | None = None,
    sort: ListingSort = ListingSort.POPULAR,
    limit: int = 50,
) -> list[ListingSummary]:
    stmt = select(MarketplaceListing).where(MarketplaceListing.status == PUBLISHED)
    if query and query.strip():
        needle = f"%{query.strip().lower()}%"
        stmt = stmt.where(
            or_(
                func.lower(MarketplaceListing.title).like(needle),
                func.lower(MarketplaceListing.description).like(needle),
            )
        )
    if category is not None:
        stmt = stmt.where(MarketplaceListing.category == category.value)
    if language:
        stmt = stmt.where(MarketplaceListing.language == language)
    if level is not None:
        stmt = stmt.where(MarketplaceListing.level == level.value)
    if size is not None:
        low, high = SIZE_BOUNDS[size]
        stmt = stmt.where(MarketplaceListing.item_count >= low)
        if high is not None:
            stmt = stmt.where(MarketplaceListing.item_count <= high)
    order = {
        ListingSort.POPULAR: (
            MarketplaceListing.acquisition_count.desc(),
            MarketplaceListing.published_at.desc(),
        ),
        ListingSort.NEWEST: (MarketplaceListing.published_at.desc(),),
        ListingSort.LARGEST: (
            MarketplaceListing.item_count.desc(),
            MarketplaceListing.published_at.desc(),
        ),
    }[sort]
    listings = db.scalars(stmt.order_by(*order).limit(limit)).all()
    courses = _courses_with_access(db, user_id, [listing.id for listing in listings])
    return [_summary(db, listing, courses.get(listing.id)) for listing in listings]


def detail(db: Session, user_id: uuid.UUID, listing_id: uuid.UUID) -> ListingDetail:
    """The presentation and size of a listing: chapter titles and question counts, no content."""
    listing = _visible_listing(db, user_id, listing_id)
    acquisition = _acquisition(db, user_id, listing.id)
    return ListingDetail(
        **_summary(db, listing, acquisition.course_id if acquisition else None).model_dump(),
        chapters=[
            ChapterSize(
                title=chapter["title"],
                questions=sum(len(c["items"]) for t in chapter["topics"] for c in t["concepts"]),
            )
            for chapter in listing.snapshot.get("chapters", [])
        ],
        is_mine=listing.author_id == user_id,
        has_access=acquisition is not None,
    )


def _visible_listing(db: Session, user_id: uuid.UUID, listing_id: uuid.UUID) -> MarketplaceListing:
    listing = db.get(MarketplaceListing, listing_id)
    if listing is None:
        raise NotFoundError("Listing not found")
    # Unpublished: still visible to its author and to whoever has access (a draft never had any).
    if (
        listing.status != PUBLISHED
        and listing.author_id != user_id
        and _acquisition(db, user_id, listing.id) is None
    ):
        raise NotFoundError("Listing not found")
    return listing


def _acquisition(
    db: Session, user_id: uuid.UUID, listing_id: uuid.UUID
) -> MarketplaceAcquisition | None:
    return db.scalar(
        select(MarketplaceAcquisition).where(
            MarketplaceAcquisition.listing_id == listing_id,
            MarketplaceAcquisition.user_id == user_id,
        )
    )


def _courses_with_access(
    db: Session, user_id: uuid.UUID, listing_ids: list[uuid.UUID]
) -> dict[uuid.UUID, uuid.UUID | None]:
    if not listing_ids:
        return {}
    rows = db.execute(
        select(MarketplaceAcquisition.listing_id, MarketplaceAcquisition.course_id).where(
            MarketplaceAcquisition.user_id == user_id,
            MarketplaceAcquisition.listing_id.in_(listing_ids),
        )
    ).all()
    return {row.listing_id: row.course_id for row in rows}


# --- Getting access (anyone signed in, not the author) ---


def acquire(
    db: Session, storage: DocumentStorage, user_id: uuid.UUID, listing_id: uuid.UUID
) -> uuid.UUID:
    """Adds the course to the user's courses, giving them access for good (free listings only,
    for now). With access already given, adds it back if they removed it."""
    listing = _visible_listing(db, user_id, listing_id)
    if listing.author_id == user_id:
        raise ConflictError("This is your own course.", details={"reason": "own_listing"})
    acquisition = _acquisition(db, user_id, listing.id)
    if acquisition is not None and acquisition.course_id is not None:
        raise ConflictError(
            "This course is already in your courses.",
            details={"reason": "already_acquired", "course_id": str(acquisition.course_id)},
        )
    if acquisition is None:
        if listing.status != PUBLISHED:
            raise NotFoundError("Listing not found")
        if listing.price_cents > 0:
            raise ConflictError(
                "Paid courses aren't available yet.", details={"reason": "payments_unavailable"}
            )
        acquisition = MarketplaceAcquisition(
            listing_id=listing.id,
            user_id=user_id,
            version=listing.version,
            price_cents=listing.price_cents,
        )
        db.add(acquisition)
        listing.acquisition_count += 1
    course = Course(
        id=uuid.uuid4(),
        user_id=user_id,
        title=listing.title,
        description=listing.description[:2000],
        language=listing.language,
        marketplace_listing_id=listing.id,
    )
    course.settings = CourseSettings()
    db.add(course)
    db.flush()
    _sync(db, storage, course, listing)
    acquisition.course_id = course.id
    db.commit()
    return course.id


def origin(db: Session, course: Course) -> CourseOrigin | None:
    if course.marketplace_listing_id is None:
        return None
    listing = db.get(MarketplaceListing, course.marketplace_listing_id)
    if listing is None:
        return None
    return CourseOrigin(
        listing_id=listing.id, author=_author(db, listing), version=course.marketplace_version or 1
    )


# --- Keeping courses with access in step with the listing ---


def _sync_all(db: Session, storage: DocumentStorage, listing: MarketplaceListing) -> None:
    courses = db.scalars(select(Course).where(Course.marketplace_listing_id == listing.id)).all()
    for course in courses:
        _sync(db, storage, course, listing)


def _sync(
    db: Session, storage: DocumentStorage, course: Course, listing: MarketplaceListing
) -> None:
    """Makes the course's content the listing's current version. Rows are matched by origin_key:
    a matched row is updated in place (the user's study stays), a new one is added, a row the
    author removed goes. Questions are updated in place by position, so answers stay attached."""
    with syncing(db):
        course.title = listing.title
        course.description = listing.description[:2000]
        course.language = listing.language
        course.marketplace_version = listing.version
        chapters = {r.origin_key: r for r in _rows(db, Chapter, course.id)}
        topics = {r.origin_key: r for r in _rows(db, Topic, course.id)}
        concepts = {r.origin_key: r for r in _rows(db, Concept, course.id)}
        items = {r.origin_key: r for r in _rows(db, LearningItem, course.id)}

        for c_order, c_data in enumerate(listing.snapshot.get("chapters", [])):
            chapter = chapters.pop(c_data["key"], None)
            if chapter is None:
                chapter = Chapter(id=uuid.uuid4(), course_id=course.id, origin_key=c_data["key"])
                db.add(chapter)
            chapter.title = c_data["title"]
            chapter.description = c_data["description"]
            chapter.order = c_order
            for t_order, t_data in enumerate(c_data["topics"]):
                topic = topics.pop(t_data["key"], None)
                if topic is None:
                    topic = Topic(id=uuid.uuid4(), course_id=course.id, origin_key=t_data["key"])
                    db.add(topic)
                topic.chapter_id = chapter.id
                topic.title = t_data["title"]
                topic.description = t_data["description"]
                topic.order = t_order
                for k_order, k_data in enumerate(t_data["concepts"]):
                    concept = concepts.pop(k_data["key"], None)
                    if concept is None:
                        concept = Concept(
                            id=uuid.uuid4(),
                            course_id=course.id,
                            origin_key=k_data["key"],
                            # Its items come with it: activation must not generate more.
                            item_generation_status=ItemGenerationStatus.READY,
                        )
                        db.add(concept)
                    concept.topic_id = topic.id
                    concept.chapter_id = chapter.id
                    concept.title = k_data["title"]
                    concept.description = k_data["description"]
                    concept.order = k_order
                    db.flush()
                    for i_order, i_data in enumerate(k_data["items"]):
                        _sync_item(
                            db,
                            storage,
                            listing,
                            concept,
                            items.pop(i_data["key"], None),
                            i_data,
                            i_order,
                        )

        db.flush()
        # What the author removed, deepest first (each level's rows may have moved elsewhere).
        for leftovers in (items, concepts, topics, chapters):
            for row in leftovers.values():
                if isinstance(row, LearningItem) and row.reference_drawing_type:
                    storage.delete(drawings.reference_key(row))
                db.delete(row)
            db.flush()


def _sync_item(
    db: Session,
    storage: DocumentStorage,
    listing: MarketplaceListing,
    concept: Concept,
    item: LearningItem | None,
    data: dict[str, Any],
    order: int,
) -> None:
    if item is None:
        item = new_item(db, concept, _item_create(data), order=order)
        item.origin_key = data["key"]
        item.origin_priority = data["priority"]
    else:
        item.concept_id = concept.id
        item.topic_id = concept.topic_id
        item.chapter_id = concept.chapter_id
        item.title = data["title"]
        item.objective = data["objective"]
        item.expected_knowledge = data["expected_knowledge"]
        item.essential_points = list(data["essential_points"])
        item.role = LearningItemRole(data["role"])
        item.difficulty = data["difficulty"]
        item.order = order
        # The user's own priority stays; one they never changed follows the author's.
        if item.priority == item.origin_priority:
            item.priority = data["priority"]
        item.origin_priority = data["priority"]
        _sync_questions(item, data["questions"])
    if data["drawing_type"]:
        storage.save(
            drawings.reference_key(item),
            storage.load(_listing_drawing_key(listing.id, listing.version, data["key"])),
        )
        item.answer_format = "DRAWING"
        item.reference_drawing_type = data["drawing_type"]
    elif item.reference_drawing_type:
        storage.delete(drawings.reference_key(item))
        item.answer_format = "TEXT"
        item.reference_drawing_type = None


def _sync_questions(item: LearningItem, questions: list[dict[str, Any]]) -> None:
    existing = list(item.questions)
    for position, q in enumerate(questions):
        if position < len(existing):
            existing[position].question_type = QuestionType(q["question_type"])
            existing[position].text = q["text"]
        else:
            item.questions.append(
                QuestionFormulation(
                    course_id=item.course_id,
                    question_type=QuestionType(q["question_type"]),
                    text=q["text"],
                )
            )
    for extra in existing[len(questions) :]:
        item.questions.remove(extra)


def _item_create(data: dict[str, Any]) -> LearningItemCreate:
    # model_construct: the snapshot was validated when it was taken from the author's course.
    return LearningItemCreate.model_construct(
        title=data["title"],
        objective=data["objective"],
        expected_knowledge=data["expected_knowledge"],
        essential_points=data["essential_points"],
        role=LearningItemRole(data["role"]),
        difficulty=data["difficulty"],
        priority=data["priority"],
        questions=[
            QuestionCreate.model_construct(
                question_type=QuestionType(q["question_type"]), text=q["text"]
            )
            for q in data["questions"]
        ],
    )


# --- Shapes ---


def _author(db: Session, listing: MarketplaceListing) -> str:
    user = db.get(User, listing.author_id)
    return (user.display_name if user and user.display_name else None) or "A LEARNABLE user"


def _summary(
    db: Session, listing: MarketplaceListing, course_id: uuid.UUID | None
) -> ListingSummary:
    return ListingSummary(
        id=listing.id,
        title=listing.title,
        subtitle=listing.subtitle,
        description=listing.description,
        outcomes=list(listing.outcomes),
        audience=listing.audience,
        level=Level(listing.level),
        category=Category(listing.category),
        language=listing.language,
        tags=list(listing.tags),
        author=_author(db, listing),
        price_cents=listing.price_cents,
        currency=listing.currency,
        version=listing.version,
        chapter_count=listing.chapter_count,
        item_count=listing.item_count,
        acquisition_count=listing.acquisition_count,
        published_at=listing.published_at,
        updated_at=listing.updated_at,
        status=listing.status,
        course_id=course_id,
    )


def _mine(db: Session, listing: MarketplaceListing) -> MyListing:
    return MyListing(
        **_summary(db, listing, None).model_dump(), source_course_id=listing.source_course_id
    )
