"""Recovery of background jobs interrupted by a restart or crash.

Document processing, curriculum proposals and Learning Item generation run as in-process
background tasks. If the process dies mid-job, the row stays PROCESSING / GENERATING and no one
will ever finish it. This sweep turns such rows into a FAILED state the user can act on.

Safe to run at any time, from any number of processes: it only touches rows older than a
threshold far above a real job's duration, with one conditional UPDATE per table, so running
it twice changes nothing. It never deletes or creates domain data. A job that was merely slow
and completes after the sweep is handled by the job itself: curriculum and item generation
discard their result unless the row is still GENERATING; a document that finishes processing
becomes READY with its chunks exactly once (processing skips a document that isn't PROCESSING).
"""

import logging
import uuid
from dataclasses import dataclass
from datetime import datetime, timedelta

from sqlalchemy import or_, update
from sqlalchemy.orm import Session

from app.db.types import utc_now
from app.models.course import Concept
from app.models.curriculum import CurriculumProposal
from app.models.document import Document
from app.models.enums import CurriculumProposalStatus, DocumentStatus, ItemGenerationStatus

logger = logging.getLogger(__name__)

# Well above one extraction or two AI calls at the timeout, times the fallback providers.
STALE_JOB_AFTER = timedelta(minutes=15)

DOCUMENT_INTERRUPTED = "Processing was interrupted. Delete this document and upload it again."
GENERATION_INTERRUPTED = "Generation was interrupted. Please try again."


@dataclass(frozen=True)
class RecoveryReport:
    documents: int
    proposals: int
    concepts: int

    @property
    def total(self) -> int:
        return self.documents + self.proposals + self.concepts


def recover_stale_jobs(
    db: Session, course_id: uuid.UUID | None = None, now: datetime | None = None
) -> RecoveryReport:
    """Marks every job older than STALE_JOB_AFTER as FAILED, for one Course or all of them."""
    now = now or utc_now()
    cutoff = now - STALE_JOB_AFTER

    documents = update(Document).where(
        Document.status == DocumentStatus.PROCESSING, Document.updated_at < cutoff
    )
    proposals = update(CurriculumProposal).where(
        CurriculumProposal.status == CurriculumProposalStatus.GENERATING,
        CurriculumProposal.updated_at < cutoff,
    )
    concepts = update(Concept).where(
        Concept.item_generation_status == ItemGenerationStatus.GENERATING,
        or_(
            Concept.item_generation_started_at.is_(None),
            Concept.item_generation_started_at < cutoff,
        ),
    )
    if course_id is not None:
        documents = documents.where(Document.course_id == course_id)
        proposals = proposals.where(CurriculumProposal.course_id == course_id)
        concepts = concepts.where(Concept.course_id == course_id)

    report = RecoveryReport(
        documents=_rowcount(
            db.execute(
                documents.values(
                    status=DocumentStatus.FAILED,
                    error_message=DOCUMENT_INTERRUPTED,
                    updated_at=now,
                )
            )
        ),
        proposals=_rowcount(
            db.execute(
                proposals.values(
                    status=CurriculumProposalStatus.FAILED,
                    error_message=GENERATION_INTERRUPTED,
                    updated_at=now,
                )
            )
        ),
        concepts=_rowcount(
            db.execute(
                concepts.values(
                    item_generation_status=ItemGenerationStatus.FAILED,
                    item_generation_error=GENERATION_INTERRUPTED,
                )
            )
        ),
    )
    db.commit()
    if report.total:
        logger.warning(
            "Recovered interrupted jobs: %d documents, %d proposals, %d concepts",
            report.documents,
            report.proposals,
            report.concepts,
        )
    return report


def _rowcount(result: object) -> int:
    return int(getattr(result, "rowcount", 0) or 0)
