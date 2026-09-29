"""Background jobs interrupted by a crash or restart (app/services/recovery.py).

A crash is simulated by not running the background task, or by recovering while the task is
halfway through, then letting it finish late."""

import uuid
from datetime import timedelta

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import func, select
from sqlalchemy.orm import sessionmaker

from app.ai.mock import MockAIProvider
from app.ai.provider import LearningItemsResult
from app.ai.schemas import LearningItemsRequest
from app.core.config import get_settings
from app.db.types import utc_now
from app.main import app, sweep_interrupted_jobs
from app.models.course import Concept
from app.models.curriculum import CurriculumProposal
from app.models.document import Document, DocumentChunk
from app.models.enums import CurriculumProposalStatus, ItemGenerationStatus
from app.models.learning import LearningItem
from app.services import recovery
from app.services.curriculum import service as curriculum_service
from app.services.documents import service as documents_service
from app.services.learning import service as learning_service
from app.services.recovery import STALE_JOB_AFTER, recover_stale_jobs
from tests.test_learning_items import items_of, sourced_concept

NOTES = b"# Mutuo\n\nIl mutuo e il contratto con cui una parte consegna denaro all'altra.\n"
LATER = STALE_JOB_AFTER + timedelta(minutes=1)


@pytest.fixture
def course(client, auth_headers):
    headers = auth_headers("recovery-owner@example.com")
    course = client.post(
        "/api/v1/courses", json={"title": "Diritto", "language": "it"}, headers=headers
    ).json()
    return headers, course["id"]


@pytest.fixture
def factory(engine):
    return sessionmaker(bind=engine, autoflush=False)


def upload(client, headers, course_id, data=NOTES):
    response = client.post(
        f"/api/v1/courses/{course_id}/documents",
        files={"file": ("mutuo.md", data, "text/markdown")},
        headers=headers,
    )
    assert response.status_code == 202, response.text
    return response.json()["id"]


def crash_during_upload(monkeypatch, client, headers, course_id):
    """The process dies after the upload is recorded, before processing runs."""
    with monkeypatch.context() as patch:
        patch.setattr(documents_service, "process_document", lambda *_: None)
        return upload(client, headers, course_id)


def document(client, headers, document_id):
    return client.get(f"/api/v1/documents/{document_id}", headers=headers).json()


def chunk_count(db_session, document_id) -> int:
    return db_session.scalar(
        select(func.count())
        .select_from(DocumentChunk)
        .where(DocumentChunk.document_id == uuid.UUID(document_id))
    )


# --- Documents ---


def test_a_stuck_document_becomes_a_recoverable_failure(monkeypatch, client, course, db_session):
    headers, course_id = course
    stuck = crash_during_upload(monkeypatch, client, headers, course_id)
    assert document(client, headers, stuck)["status"] == "PROCESSING"

    # Not yet stale: a job this young may still be running in another worker.
    assert recover_stale_jobs(db_session).total == 0
    assert document(client, headers, stuck)["status"] == "PROCESSING"

    report = recover_stale_jobs(db_session, now=utc_now() + LATER)
    assert report.documents == 1
    failed = document(client, headers, stuck)
    assert failed["status"] == "FAILED"
    assert failed["error_message"] == recovery.DOCUMENT_INTERRUPTED

    # Idempotent.
    assert recover_stale_jobs(db_session, now=utc_now() + LATER).total == 0

    # The advice in the message works: delete, upload the same file again, get it processed.
    assert client.delete(f"/api/v1/documents/{stuck}", headers=headers).status_code == 204
    again = upload(client, headers, course_id)
    assert document(client, headers, again)["status"] == "READY"
    assert chunk_count(db_session, again) > 0


def test_a_ready_or_failed_document_is_never_touched(client, course, db_session):
    headers, course_id = course
    ready = upload(client, headers, course_id)
    failed = upload(client, headers, course_id, data=b"\n   \n")  # no text → FAILED

    assert recover_stale_jobs(db_session, now=utc_now() + LATER).total == 0
    assert document(client, headers, ready)["status"] == "READY"
    assert document(client, headers, failed)["error_message"] != recovery.DOCUMENT_INTERRUPTED


def test_a_slow_document_that_finishes_after_recovery_is_stored_once(
    monkeypatch, client, course, db_session, factory, storage
):
    headers, course_id = course
    stuck = crash_during_upload(monkeypatch, client, headers, course_id)
    real_extract = documents_service.extract

    def recover_midway(*args):
        with factory() as other:
            recover_stale_jobs(other, now=utc_now() + LATER)
        return real_extract(*args)

    monkeypatch.setattr(documents_service, "extract", recover_midway)
    documents_service.process_document(factory, storage, uuid.UUID(stuck))
    documents_service.process_document(factory, storage, uuid.UUID(stuck))  # a duplicate run

    assert document(client, headers, stuck)["status"] == "READY"
    first = chunk_count(db_session, stuck)
    assert first > 0
    documents_service.process_document(factory, storage, uuid.UUID(stuck))
    assert chunk_count(db_session, stuck) == first


# --- Learning Item generation ---


def mark_generating(db_session, concept_id, started_at):
    db_session.expire_all()
    row = db_session.get(Concept, uuid.UUID(concept_id))
    row.item_generation_status = ItemGenerationStatus.GENERATING
    row.item_generation_started_at = started_at
    db_session.commit()


def concept_read(client, headers, concept_id):
    return client.get(f"/api/v1/concepts/{concept_id}", headers=headers).json()


def test_an_interrupted_item_generation_can_be_retried_exactly_once(client, course, db_session):
    headers, course_id = course
    concept = sourced_concept(client, headers, course_id)
    mark_generating(db_session, concept["id"], utc_now())

    assert recover_stale_jobs(db_session, now=utc_now() + LATER).concepts == 1
    state = concept_read(client, headers, concept["id"])
    assert state["item_generation_status"] == "FAILED"

    url = f"/api/v1/concepts/{concept['id']}/learning-items/generate"
    assert client.post(url, headers=headers).status_code == 202
    produced = items_of(client, headers, concept["id"])
    assert produced
    assert client.post(url, headers=headers).status_code == 409  # items exist: no second set
    assert items_of(client, headers, concept["id"]) == produced


def test_an_old_item_generation_finishing_late_discards_its_result(
    client, course, db_session, factory
):
    headers, course_id = course
    concept = sourced_concept(client, headers, course_id)
    concept_id = uuid.UUID(concept["id"])
    mark_generating(db_session, concept["id"], utc_now())

    class InterruptedMidCall(MockAIProvider):
        """While the old job waits on the AI, it is recovered and the user retries."""

        produced = 0

        def generate_learning_items(self, request: LearningItemsRequest) -> LearningItemsResult:
            with factory() as other:
                recover_stale_jobs(other, now=utc_now() + LATER)
            url = f"/api/v1/concepts/{concept_id}/learning-items/generate"
            assert client.post(url, headers=headers).status_code == 202
            result = super().generate_learning_items(request)
            InterruptedMidCall.produced = len(result.output.items)
            return result

    learning_service.generate_items(factory, InterruptedMidCall(), concept_id, 60_000)

    stored = db_session.scalar(
        select(func.count()).select_from(LearningItem).where(LearningItem.concept_id == concept_id)
    )
    assert stored == InterruptedMidCall.produced  # the retry's set only, not a second one
    assert concept_read(client, headers, concept["id"])["item_generation_status"] == "READY"


# --- Curriculum proposals ---


def test_an_interrupted_proposal_fails_and_its_late_result_is_discarded(
    client, course, db_session, factory
):
    headers, course_id = course
    document_id = upload(client, headers, course_id)
    running = CurriculumProposal(
        course_id=uuid.UUID(course_id), status=CurriculumProposalStatus.GENERATING
    )
    db_session.add(running)
    db_session.commit()

    assert recover_stale_jobs(db_session, now=utc_now() + LATER).proposals == 1
    proposal = client.get(f"/api/v1/curriculum-proposals/{running.id}", headers=headers).json()
    assert proposal["status"] == "FAILED"
    assert proposal["error_message"] == recovery.GENERATION_INTERRUPTED

    curriculum_service.generate_proposal(
        factory, MockAIProvider(), running.id, [uuid.UUID(document_id)], 60_000
    )
    db_session.expire_all()
    assert db_session.get(CurriculumProposal, running.id).status is (
        CurriculumProposalStatus.FAILED
    )
    assert db_session.get(CurriculumProposal, running.id).content is None


def test_recovery_is_scoped_to_one_course_when_asked(
    monkeypatch, client, auth_headers, course, db_session
):
    headers, course_id = course
    other_headers = auth_headers("other-recovery@example.com")
    other = client.post(
        "/api/v1/courses", json={"title": "Altro", "language": "it"}, headers=other_headers
    ).json()["id"]
    mine = crash_during_upload(monkeypatch, client, headers, course_id)
    theirs = crash_during_upload(monkeypatch, client, other_headers, other)

    report = recover_stale_jobs(db_session, uuid.UUID(course_id), now=utc_now() + LATER)
    assert report.documents == 1
    assert document(client, headers, mine)["status"] == "FAILED"
    assert document(client, other_headers, theirs)["status"] == "PROCESSING"


# --- Wiring ---


def test_the_server_recovers_interrupted_jobs_at_startup(monkeypatch, client, course, db_session):
    headers, course_id = course
    stuck = crash_during_upload(monkeypatch, client, headers, course_id)
    row = db_session.get(Document, uuid.UUID(stuck))
    row.updated_at = utc_now() - LATER
    db_session.commit()

    monkeypatch.setenv("JOB_RECOVERY_INTERVAL_SECONDS", "3600")
    get_settings.cache_clear()
    try:
        with TestClient(app):  # a restart: the lifespan runs again
            pass
    finally:
        get_settings.cache_clear()

    assert document(client, headers, stuck)["status"] == "FAILED"


def test_a_failing_sweep_never_raises():
    def broken():
        raise RuntimeError("database unreachable")

    sweep_interrupted_jobs(broken)  # type: ignore[arg-type]
