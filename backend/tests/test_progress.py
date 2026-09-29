"""Progress, mastery estimates and review load (docs/PROJECT_SPEC.md §40, §52-54, §68)."""

import uuid
from datetime import timedelta

import pytest
from sqlalchemy import select

from app.ai.factory import get_ai_provider
from app.ai.mock import MockAIProvider
from app.ai.schemas import EvaluationOutput
from app.db.types import utc_now
from app.main import app
from app.models.enums import EvaluationClassification, MemoryState
from app.models.learning import ReviewState
from app.services.scheduling.policy import ChessableStyleSchedulingPolicy, MemorySnapshot

FULL = "Il mutuo prevede la consegna di denaro e l'obbligo di restituzione."


@pytest.fixture
def course(client, auth_headers):
    headers = auth_headers("progress@example.com")
    course = client.post("/api/v1/courses", json={"title": "Diritto"}, headers=headers).json()
    chapter = client.post(
        f"/api/v1/courses/{course['id']}/chapters", json={"title": "Contratti"}, headers=headers
    ).json()
    topic = client.post(
        f"/api/v1/chapters/{chapter['id']}/topics", json={"title": "Prestiti"}, headers=headers
    ).json()
    return headers, course["id"], topic["id"]


def concept_with_item(client, headers, topic_id, title, activate=True):
    concept = client.post(
        f"/api/v1/topics/{topic_id}/concepts", json={"title": title}, headers=headers
    ).json()
    if activate:
        client.post(f"/api/v1/concepts/{concept['id']}/activate", headers=headers)
    item = client.post(
        f"/api/v1/concepts/{concept['id']}/learning-items",
        json={
            "title": f"{title}: definizione",
            "expected_knowledge": "Consegna di denaro con obbligo di restituzione.",
            "essential_points": ["consegna di denaro", "obbligo di restituzione"],
            "questions": [{"question_type": "DEFINITION", "text": f"{title}?"}],
        },
        headers=headers,
    ).json()
    return concept, item


def progress(client, headers, course_id, offset=0):
    return client.get(
        f"/api/v1/courses/{course_id}/progress",
        params={"utc_offset_minutes": offset},
        headers=headers,
    ).json()


def learn_all(client, headers, course_id, text=FULL):
    session = client.post(
        f"/api/v1/courses/{course_id}/review-sessions", json={"intent": "LEARN"}, headers=headers
    ).json()
    while not (
        card := client.get(f"/api/v1/review-sessions/{session['id']}/next", headers=headers).json()
    )["done"]:
        client.post(
            f"/api/v1/review-sessions/{session['id']}/answers",
            json={"question_formulation_id": card["card"]["question"]["id"], "text": text},
            headers=headers,
        )


def state_of(db_session, item_id):
    db_session.expire_all()
    return db_session.scalar(
        select(ReviewState).where(ReviewState.learning_item_id == uuid.UUID(item_id))
    )


def test_curriculum_and_memory_progress_are_separate_at_every_level(client, course):
    headers, course_id, topic_id = course
    concept_with_item(client, headers, topic_id, "Mutuo")
    studied, _ = concept_with_item(client, headers, topic_id, "Deposito", activate=False)
    client.post(f"/api/v1/concepts/{studied['id']}/mark-studied", headers=headers)

    before = progress(client, headers, course_id)
    assert before["curriculum"] == {
        "concepts": 2,
        "not_studied": 0,
        "studied": 1,
        "active": 1,
        "paused": 0,
        "completed": 0,
    }
    assert before["memory"]["items_trained"] == 2
    assert (before["memory"]["new"], before["memory"]["mastery"]) == (2, 0.0)

    learn_all(client, headers, course_id)
    after = progress(client, headers, course_id)
    # Learning moved memory, not the curriculum.
    assert after["curriculum"] == before["curriculum"]
    assert (after["memory"]["new"], after["memory"]["learning"]) == (1, 1)
    assert after["memory"]["mastery"] == pytest.approx((1 / 8) / 2, abs=1e-3)
    [chapter] = after["chapters"]
    [topic] = chapter["topics"]
    assert chapter["memory"] == topic["memory"] == after["memory"]
    mutuo = next(c for c in topic["concepts"] if c["title"] == "Mutuo")
    assert (mutuo["study_state"], mutuo["memory"]["mastery"]) == ("ACTIVE", 0.125)


def test_mastery_estimate_rises_with_level_and_falls_with_lapses():
    policy = ChessableStyleSchedulingPolicy()
    base = MemorySnapshot(state=MemoryState.REVIEW, level=4)
    assert policy.mastery_estimate(MemorySnapshot()) == 0.0
    assert policy.mastery_estimate(base) == 0.5
    lapsed = MemorySnapshot(state=MemoryState.REVIEW, level=4, lapse_count=2)
    assert policy.mastery_estimate(lapsed) == pytest.approx(0.5 / 1.5)
    top = MemorySnapshot(state=MemoryState.MASTERED, level=8)
    assert policy.mastery_estimate(top) == 1.0


def test_untrained_items_are_left_out_of_memory_progress(client, course):
    headers, course_id, topic_id = course
    _, item = concept_with_item(client, headers, topic_id, "Mutuo")
    client.post(f"/api/v1/learning-items/{item['id']}/untrain", headers=headers)
    memory = progress(client, headers, course_id)["memory"]
    assert (memory["items_trained"], memory["mastery"]) == (0, None)


def test_review_load_buckets_follow_the_users_calendar_day(client, course, db_session):
    headers, course_id, topic_id = course
    items = [concept_with_item(client, headers, topic_id, f"C{i}")[1] for i in range(6)]
    learn_all(client, headers, course_id)
    concept_with_item(client, headers, topic_id, "Nuovo")  # added after learning: stays NEW

    now = utc_now()
    local_midnight = (now + timedelta(hours=2)).replace(hour=0, minute=0, second=0, microsecond=0)
    start_of_today = local_midnight - timedelta(hours=2)  # UTC+2 midnight, in UTC
    dues = [
        now - timedelta(hours=1),  # due now
        # later today (or due now, if this runs in the last minute of the day)
        min(now + timedelta(minutes=1), start_of_today + timedelta(days=1, seconds=-1)),
        start_of_today + timedelta(days=1, hours=12),  # tomorrow
        start_of_today + timedelta(days=4),  # within the week
        start_of_today + timedelta(days=30),  # later
        start_of_today + timedelta(days=1, hours=1),  # tomorrow
    ]
    for item, due in zip(items, dues, strict=True):
        state_of(db_session, item["id"]).due_at = due
        db_session.commit()

    load = client.get(
        f"/api/v1/courses/{course_id}/review-load",
        params={"utc_offset_minutes": 120},
        headers=headers,
    ).json()
    assert load["due_now"] + load["later_today"] == 2
    assert (load["tomorrow"], load["next_7_days"], load["later"]) == (2, 1, 1)
    assert load["new_to_learn"] == 1
    assert progress(client, headers, course_id, 120)["review_load"] == load


def test_paused_and_inactive_items_are_not_review_load(client, course, db_session):
    headers, course_id, topic_id = course
    concept, item = concept_with_item(client, headers, topic_id, "Mutuo")
    learn_all(client, headers, course_id)
    state_of(db_session, item["id"]).due_at = utc_now() - timedelta(hours=1)
    db_session.commit()
    load_url = f"/api/v1/courses/{course_id}/review-load"
    assert client.get(load_url, headers=headers).json()["due_now"] == 1

    client.post(f"/api/v1/learning-items/{item['id']}/pause", headers=headers)
    assert client.get(load_url, headers=headers).json()["due_now"] == 0
    client.post(f"/api/v1/learning-items/{item['id']}/resume", headers=headers)
    client.post(f"/api/v1/concepts/{concept['id']}/deactivate", headers=headers)
    assert client.get(load_url, headers=headers).json()["due_now"] == 0


def test_misconceptions_are_surfaced_on_their_concept(client, course):
    headers, course_id, topic_id = course
    concept_with_item(client, headers, topic_id, "Mutuo")
    app.dependency_overrides[get_ai_provider] = lambda: MockAIProvider(
        evaluation=EvaluationOutput(
            classification=EvaluationClassification.MISCONCEPTION,
            correctness=0.3,
            completeness=0.3,
            conceptual_understanding=0.2,
            precision=0.4,
            confidence=0.9,
            misconceptions=["Confonde il mutuo con il comodato"],
            context_sufficient=True,
        )
    )
    learn_all(client, headers, course_id, text="E un comodato.")
    [concept] = progress(client, headers, course_id)["chapters"][0]["topics"][0]["concepts"]
    assert concept["misconceptions"] == ["Confonde il mutuo con il comodato"]


def test_progress_of_another_course_is_404(client, course, auth_headers):
    _, course_id, _ = course
    stranger = auth_headers("stranger@example.com")
    assert client.get(f"/api/v1/courses/{course_id}/progress", headers=stranger).status_code == 404


def test_overdue_is_the_part_of_due_now_from_before_today(client, course, db_session):
    headers, course_id, topic_id = course
    _, yesterday = concept_with_item(client, headers, topic_id, "Ieri")
    _, this_morning = concept_with_item(client, headers, topic_id, "Stamattina")
    learn_all(client, headers, course_id)
    state_of(db_session, yesterday["id"]).due_at = utc_now() - timedelta(days=1, hours=1)
    db_session.commit()
    state_of(db_session, this_morning["id"]).due_at = utc_now() - timedelta(seconds=1)
    db_session.commit()

    load = client.get(f"/api/v1/courses/{course_id}/review-load", headers=headers).json()
    assert (load["due_now"], load["overdue"]) == (2, 1)


def test_home_summarizes_each_of_my_courses_and_nothing_else(
    client, course, auth_headers, db_session
):
    headers, course_id, topic_id = course
    weak, item = concept_with_item(client, headers, topic_id, "Debole")
    concept_with_item(client, headers, topic_id, "Solido")
    learn_all(client, headers, course_id)
    state_of(db_session, item["id"]).lapse_count = 2
    db_session.commit()
    state_of(db_session, item["id"]).due_at = utc_now() - timedelta(minutes=5)
    db_session.commit()
    stranger = auth_headers("stranger@example.com")
    client.post("/api/v1/courses", json={"title": "Not yours"}, headers=stranger)

    home = client.get("/api/v1/home", headers=headers).json()

    [summary] = home["courses"]
    assert (summary["course_id"], summary["title"]) == (course_id, "Diritto")
    assert summary["active_concepts"] == 2
    assert summary["review_load"]["due_now"] == 1
    assert [(w["id"], w["lapses"]) for w in summary["weak_concepts"]] == [(weak["id"], 2)]
    assert summary["mastery"] is not None
    assert home["totals"] == summary["review_load"]
    theirs = client.get("/api/v1/home", headers=stranger).json()
    assert [c["title"] for c in theirs["courses"]] == ["Not yours"]
    assert theirs["totals"]["due_now"] == 0
