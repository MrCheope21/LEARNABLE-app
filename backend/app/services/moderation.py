"""Reports to the administrator about a person, a message or a review (docs/COMMUNITY.md §7).

The administrator sees the reported text only: the name, the one message or the one review,
copied when the report was made. Nothing else of anyone's conversations is shown."""

import uuid

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.core.errors import ConflictError, NotFoundError
from app.db.types import utc_now
from app.models.community import REPORT_OPEN, REPORT_RESOLVED, Message, Report
from app.models.marketplace import MarketplaceListing, MarketplaceReview
from app.models.user import User
from app.schemas.community import ReportKind, ReportRead

EXCERPT = 2000
LIST_LIMIT = 200


def _target(
    db: Session, reporter: User, kind: ReportKind, target_id: uuid.UUID
) -> tuple[uuid.UUID, str]:
    """Who the report is about and what is reported. 404 unless the reporter can see it."""
    if kind is ReportKind.USER:
        user = db.get(User, target_id)
        if user is None:
            raise NotFoundError("Not found")
        return user.id, user.display_name or ""
    if kind is ReportKind.MESSAGE:
        message = db.get(Message, target_id)
        # Only a message the reporter received.
        if message is None or message.recipient_id != reporter.id:
            raise NotFoundError("Not found")
        return message.sender_id, message.body
    review = db.get(MarketplaceReview, target_id)
    if review is None:
        raise NotFoundError("Not found")
    listing = db.get(MarketplaceListing, review.listing_id)
    title = listing.title if listing else ""
    text = f"{'★' * review.rating} {review.comment}".strip()
    if review.reply:
        text += f"\n↳ {review.reply}"
    return review.user_id, f"[{title}] {text}"


def report(
    db: Session, reporter: User, kind: ReportKind, target_id: uuid.UUID, reason: str
) -> None:
    """Files a report. Reporting the same thing again updates the reason and reopens it."""
    subject_id, excerpt = _target(db, reporter, kind, target_id)
    if subject_id == reporter.id:
        raise ConflictError("You can't report yourself.", details={"reason": "self_report"})
    row = db.scalar(
        select(Report).where(
            Report.reporter_id == reporter.id,
            Report.kind == kind.value,
            Report.target_id == target_id,
        )
    )
    if row is None:
        row = Report(reporter_id=reporter.id, kind=kind.value, target_id=target_id)
        db.add(row)
    row.subject_id = subject_id
    row.reason = reason.strip()
    row.excerpt = excerpt[:EXCERPT]
    row.status = REPORT_OPEN
    row.resolved_at = None
    db.commit()


def open_count(db: Session) -> int:
    return int(
        db.scalar(select(func.count()).select_from(Report).where(Report.status == REPORT_OPEN)) or 0
    )


def listed(db: Session) -> list[ReportRead]:
    """Open ones first, then the most recent."""
    rows = db.scalars(
        select(Report)
        .order_by((Report.status != REPORT_OPEN), Report.created_at.desc(), Report.id)
        .limit(LIST_LIMIT)
    ).all()
    ids = {r.reporter_id for r in rows} | {r.subject_id for r in rows if r.subject_id}
    users = {u.id: u for u in db.scalars(select(User).where(User.id.in_(ids)))} if ids else {}
    about: dict[uuid.UUID, int] = {}
    if ids:
        about = {
            subject_id: int(n)
            for subject_id, n in db.execute(
                select(Report.subject_id, func.count())
                .where(Report.subject_id.in_(ids))
                .group_by(Report.subject_id)
            ).all()
            if subject_id is not None
        }
    result: list[ReportRead] = []
    for row in rows:
        reporter = users.get(row.reporter_id)
        subject = users.get(row.subject_id) if row.subject_id else None
        result.append(
            ReportRead(
                id=row.id,
                kind=ReportKind(row.kind),
                target_id=row.target_id,
                reporter=(reporter.display_name or reporter.email) if reporter else "",
                reporter_email=reporter.email if reporter else "",
                subject_id=row.subject_id,
                subject=(subject.display_name or subject.email) if subject else None,
                subject_email=subject.email if subject else None,
                reason=row.reason,
                excerpt=row.excerpt,
                status="OPEN" if row.status == REPORT_OPEN else "RESOLVED",
                created_at=row.created_at,
                resolved_at=row.resolved_at,
                subject_reports=about.get(row.subject_id, 0) if row.subject_id else 0,
            )
        )
    return result


def set_resolved(db: Session, report_id: uuid.UUID, resolved: bool) -> None:
    row = db.get(Report, report_id)
    if row is None:
        raise NotFoundError("Report not found")
    row.status = REPORT_RESOLVED if resolved else REPORT_OPEN
    row.resolved_at = utc_now() if resolved else None
    db.commit()
