"""Dashboard aggregates, preferences, timezones, activity; downloads and storage backends
(docs/XP_AND_ACTIVITY.md, docs/DEPLOYMENT.md)."""

import io
import uuid
from datetime import UTC, date, datetime, timedelta

import pytest
from botocore.response import StreamingBody
from botocore.stub import Stubber
from sqlalchemy import select
from test_review import FULL, answer, concept, item, make_due, memory, start
from test_xp_consolidation import studied

from app.models.rewards import DailyActivity
from app.models.user import User
from app.services.dashboard import service as dashboard_service
from app.services.rewards.hints import build_hint
from app.services.rewards.service import local_day
from app.storage.documents import S3DocumentStorage, StoredFileMissingError


@pytest.fixture
def learner(client, auth_headers):
    headers = auth_headers("dash@example.com")
    course = client.post(
        "/api/v1/courses", json={"title": "Diritto", "language": "it"}, headers=headers
    ).json()
    chapter = client.post(
        f"/api/v1/courses/{course['id']}/chapters", json={"title": "Contratti"}, headers=headers
    ).json()
    topic = client.post(
        f"/api/v1/chapters/{chapter['id']}/topics", json={"title": "Prestiti"}, headers=headers
    ).json()
    return headers, course["id"], topic["id"]


def get_dashboard(client, headers, **params):
    response = client.get("/api/v1/dashboard", headers=headers, params=params)
    assert response.status_code == 200, response.text
    return response.json()


def consolidate(client, headers, concept_id, rounds=3):
    session = studied(client, headers, concept_id).json()
    for _ in range(rounds):
        answer(client, headers, session["id"], FULL)
    return session


def user_of(db_session, email):
    return db_session.scalar(select(User).where(User.email == email))


# --- Course cards and the next step ---


def test_empty_account_is_told_to_create_a_course(client, auth_headers):
    headers = auth_headers("fresh@example.com")
    data = get_dashboard(client, headers)
    assert data["courses"] == []
    assert data["next_step"]["kind"] == "create_course"
    assert data["xp"] == {"total": 0, "today": 0}
    assert data["streak"]["current"] == 0
    assert data["goal"] == {"target": 20, "done": 0, "unit": "answers"}
    assert [h["key"] for h in data["planner"]["horizons"]] == ["now", "1h", "4h", "1d", "3d", "7d"]


def test_a_course_without_material_asks_to_be_set_up(client, learner):
    headers, course_id, _ = learner
    # The fixture's course has a chapter and topic but no concept yet.
    data = get_dashboard(client, headers)
    assert data["courses"][0]["learn"] == {"kind": "setup", "concept": None, "session_id": None}
    assert data["next_step"] == {
        "kind": "setup_course",
        "course_id": course_id,
        "course_title": "Diritto",
        "concept_id": None,
        "concept_title": None,
        "session_id": None,
        "count": None,
        "round": None,
        "rounds_total": None,
    }


def test_course_card_counts_and_learn_actions(client, learner, db_session):
    headers, course_id, topic_id = learner
    first = concept(client, headers, topic_id, title="Mutuo")
    item(client, headers, first["id"], title="Uno")
    item(client, headers, first["id"], title="Due")
    later = concept(client, headers, topic_id, title="Deposito", active=False)

    [card] = get_dashboard(client, headers)["courses"]
    assert (card["concepts_total"], card["concepts_studied"]) == (2, 0)
    assert (card["items_trained"], card["items_introduced"]) == (2, 0)
    assert (card["due_now"], card["new_ready"]) == (0, 2)
    assert card["learn"]["kind"] == "study"
    assert card["learn"]["concept"]["id"] == first["id"]
    assert get_dashboard(client, headers)["next_step"]["kind"] == "learn"

    # An unfinished batch comes first, with its round.
    session = studied(client, headers, first["id"]).json()
    answer(client, headers, session["id"], FULL)
    data = get_dashboard(client, headers)
    assert data["courses"][0]["learn"] == {
        "kind": "resume",
        "concept": {"id": first["id"], "title": "Mutuo", "study_state": "ACTIVE"},
        "session_id": session["id"],
    }
    step = data["next_step"]
    assert (step["kind"], step["session_id"], step["round"], step["rounds_total"]) == (
        "resume_consolidation",
        session["id"],
        2,
        3,
    )
    assert step["count"] == 5

    for _ in range(5):
        answer(client, headers, session["id"], FULL)
    card = get_dashboard(client, headers)["courses"][0]
    # Both items consolidated: the concept counts as studied, the next concept needs activating.
    assert (card["concepts_studied"], card["items_introduced"]) == (1, 2)
    assert card["learn"]["kind"] == "activate"
    assert card["learn"]["concept"]["id"] == later["id"]
    assert card["last_studied_at"] is not None

    # Due reviews take priority over new learning.
    [one, _] = client.get(f"/api/v1/concepts/{first['id']}/learning-items", headers=headers).json()
    make_due(db_session, one["id"])
    data = get_dashboard(client, headers)
    assert data["courses"][0]["due_now"] == 1
    assert (data["next_step"]["kind"], data["next_step"]["count"]) == ("review", 1)

    summary = client.get(f"/api/v1/courses/{course_id}/summary", headers=headers).json()
    assert summary["due_now"] == 1


def test_due_count_matches_what_a_review_session_asks(client, learner, db_session):
    headers, course_id, topic_id = learner
    c = concept(client, headers, topic_id)
    it = item(client, headers, c["id"])
    consolidate(client, headers, c["id"])
    make_due(db_session, it["id"])
    # Pausing the concept removes it from reviews, and from the due count.
    client.post(f"/api/v1/concepts/{c['id']}/pause", headers=headers)
    assert get_dashboard(client, headers)["courses"][0]["due_now"] == 0
    assert start(client, headers, course_id, intent="SCHEDULED_REVIEW").status_code == 409
    client.post(f"/api/v1/concepts/{c['id']}/resume", headers=headers)
    assert get_dashboard(client, headers)["courses"][0]["due_now"] == 1
    session = start(client, headers, course_id, intent="SCHEDULED_REVIEW").json()
    assert session["total"] == 1


def test_planner_is_cumulative(client, learner, db_session):
    headers, _, topic_id = learner
    c = concept(client, headers, topic_id)
    items = [item(client, headers, c["id"], title=f"Voce {n}") for n in range(4)]
    consolidate(client, headers, c["id"], rounds=12)
    offsets = [timedelta(minutes=-5), timedelta(minutes=30), timedelta(hours=20), timedelta(days=5)]
    for it, offset in zip(items, offsets, strict=True):
        state = memory(db_session, it["id"])
        state.due_at = datetime.now(UTC) + offset
        db_session.commit()  # memory() expires the session: save each change first

    horizons = {h["key"]: h["items"] for h in get_dashboard(client, headers)["planner"]["horizons"]}
    assert horizons == {"now": 1, "1h": 2, "4h": 2, "1d": 3, "3d": 3, "7d": 4}


# --- XP, goal, streak, activity ---


def test_goal_and_xp_today_count_completed_answers(client, learner):
    headers, _, topic_id = learner
    c = concept(client, headers, topic_id)
    item(client, headers, c["id"])
    consolidate(client, headers, c["id"])

    data = get_dashboard(client, headers)
    assert data["xp"] == {"total": 60, "today": 60}
    assert data["goal"]["done"] == 3
    assert data["streak"]["current"] == 1
    assert data["streak"]["today_complete"] is True
    assert [d["attempts"] for d in data["activity"]["days"]] == [3]
    assert data["activity"]["days"][0]["date"] == data["today"]


def test_goal_is_editable_and_validated(client, learner):
    headers, _, _ = learner
    updated = client.patch("/api/v1/auth/me", json={"daily_goal": 35}, headers=headers)
    assert updated.status_code == 200
    assert updated.json()["daily_goal"] == 35
    assert get_dashboard(client, headers)["goal"]["target"] == 35
    for bad in (0, 501, "many"):
        response = client.patch("/api/v1/auth/me", json={"daily_goal": bad}, headers=headers)
        assert response.status_code == 422


def test_timezone_is_set_at_registration_and_validated(client):
    created = client.post(
        "/api/v1/auth/register",
        json={
            "email": "rome@example.com",
            "password": "correct-horse-battery-staple",
            "timezone": "Europe/Rome",
        },
    )
    assert created.json()["timezone"] == "Europe/Rome"
    bad = client.post(
        "/api/v1/auth/register",
        json={
            "email": "nowhere@example.com",
            "password": "correct-horse-battery-staple",
            "timezone": "Mars/Olympus",
        },
    )
    assert bad.status_code == 422
    default = client.post(
        "/api/v1/auth/register",
        json={"email": "utc@example.com", "password": "correct-horse-battery-staple"},
    )
    assert default.json()["timezone"] == "UTC"


@pytest.mark.parametrize(
    ("zone", "moment", "day"),
    [
        # 23:30 UTC is already tomorrow in Rome (UTC+1 in winter)…
        ("Europe/Rome", datetime(2026, 1, 10, 23, 30, tzinfo=UTC), date(2026, 1, 11)),
        # …but not in New York.
        ("America/New_York", datetime(2026, 1, 10, 23, 30, tzinfo=UTC), date(2026, 1, 10)),
        # Daylight saving: Rome moves to UTC+2 on 29 March 2026 at 01:00 UTC.
        ("Europe/Rome", datetime(2026, 3, 28, 22, 30, tzinfo=UTC), date(2026, 3, 28)),
        ("Europe/Rome", datetime(2026, 3, 29, 22, 30, tzinfo=UTC), date(2026, 3, 30)),
        # And back to UTC+1 on 25 October 2026.
        ("Europe/Rome", datetime(2026, 10, 24, 22, 30, tzinfo=UTC), date(2026, 10, 25)),
        ("Europe/Rome", datetime(2026, 10, 25, 22, 30, tzinfo=UTC), date(2026, 10, 25)),
        # Unknown zones fall back to UTC instead of failing.
        ("Not/AZone", datetime(2026, 1, 10, 23, 30, tzinfo=UTC), date(2026, 1, 10)),
    ],
)
def test_local_calendar_day(zone, moment, day):
    assert local_day(zone, moment) == day


def test_streak_stays_alive_until_the_first_answer_of_today(client, learner, db_session):
    headers, _, topic_id = learner
    user = user_of(db_session, "dash@example.com")
    today = local_day(user.timezone, datetime.now(UTC))
    for offset in (1, 2, 3, 5):  # yesterday, the two days before, and a gap
        db_session.add(
            DailyActivity(user_id=user.id, day=today - timedelta(days=offset), attempts=2)
        )
    db_session.commit()

    streak = get_dashboard(client, headers)["streak"]
    assert (streak["current"], streak["today_complete"]) == (3, False)
    assert [d["active"] for d in streak["last_7_days"]] == [
        False,
        True,
        False,
        True,
        True,
        True,
        False,
    ]

    c = concept(client, headers, topic_id)
    item(client, headers, c["id"])
    consolidate(client, headers, c["id"], rounds=1)
    streak = get_dashboard(client, headers)["streak"]
    assert (streak["current"], streak["today_complete"]) == (4, True)


def test_answers_count_on_the_users_local_day(client, learner, db_session, monkeypatch):
    headers, _, topic_id = learner
    client.patch("/api/v1/auth/me", json={"timezone": "Europe/Rome"}, headers=headers)
    late_evening_utc = datetime(2026, 1, 10, 23, 30, tzinfo=UTC)
    monkeypatch.setattr("app.services.review.service.utc_now", lambda: late_evening_utc)
    c = concept(client, headers, topic_id)
    item(client, headers, c["id"])
    consolidate(client, headers, c["id"], rounds=1)

    user = user_of(db_session, "dash@example.com")
    db_session.expire_all()
    [row] = db_session.scalars(select(DailyActivity).where(DailyActivity.user_id == user.id)).all()
    assert row.day == date(2026, 1, 11)  # Rome was already on the 11th


def test_activity_calendar_shape(client, learner):
    headers, _, _ = learner
    activity = client.get("/api/v1/activity", headers=headers, params={"weeks": 52}).json()
    start_day = date.fromisoformat(activity["start"])
    end_day = date.fromisoformat(activity["end"])
    assert start_day.weekday() == 0
    assert end_day.weekday() == 6
    assert (end_day - start_day).days + 1 == 52 * 7
    assert start_day <= date.fromisoformat(activity["today"]) <= end_day
    twelve = get_dashboard(client, headers)["activity"]
    assert (date.fromisoformat(twelve["end"]) - date.fromisoformat(twelve["start"])).days == 83


def test_metrics_are_private_to_each_account(client, learner, auth_headers):
    headers, course_id, topic_id = learner
    c = concept(client, headers, topic_id)
    item(client, headers, c["id"])
    consolidate(client, headers, c["id"])

    other = auth_headers("someone-else@example.com")
    theirs = get_dashboard(client, other)
    assert theirs["courses"] == []
    assert theirs["xp"] == {"total": 0, "today": 0}
    assert theirs["goal"]["done"] == 0
    assert theirs["activity"]["days"] == []
    assert client.get(f"/api/v1/courses/{course_id}/summary", headers=other).status_code == 404
    plan = client.get(f"/api/v1/concepts/{c['id']}/consolidation", headers=other)
    assert plan.status_code == 404


def test_dashboard_query_count_does_not_grow_with_courses(client, learner, engine):
    """No per-course round trips: 1 course and 6 courses cost the same number of queries."""
    from sqlalchemy import event

    headers, _, _ = learner

    def count_queries():
        statements = []

        def before(*_args):
            statements.append(1)

        event.listen(engine, "before_cursor_execute", before)
        try:
            get_dashboard(client, headers)
        finally:
            event.remove(engine, "before_cursor_execute", before)
        return len(statements)

    one = count_queries()
    for n in range(5):
        client.post("/api/v1/courses", json={"title": f"Corso {n}"}, headers=headers)
    assert count_queries() == one


# --- Hints (pure) ---


@pytest.mark.parametrize(
    ("points", "reference", "expected"),
    [
        (
            ["consegna di denaro", "obbligo di restituzione"],
            "Consegna di denaro e obbligo.",
            "consegna…",
        ),
        (
            ["Il deposito bancario trasferisce la proprietà del denaro alla banca"],
            "Il deposito bancario trasferisce la proprietà del denaro alla banca, "
            "che deve restituirlo.",
            "Il deposito bancario…",
        ),
        ([], "Sì.", None),
        ([], "", None),
        (["ok"], "ok", None),
    ],
)
def test_hint_is_a_cue_not_the_answer(points, reference, expected):
    assert build_hint(points, reference) == expected


# --- Downloads and storage ---


def test_owner_downloads_the_original_as_an_attachment(client, learner, auth_headers):
    headers, course_id, _ = learner
    data = b"<script>alert('x')</script> Appunti"
    uploaded = client.post(
        f"/api/v1/courses/{course_id}/documents",
        files={"file": ("appunti è.md", data, "text/markdown")},
        headers=headers,
    ).json()

    response = client.get(f"/api/v1/documents/{uploaded['id']}/file", headers=headers)
    assert response.status_code == 200
    assert response.content == data
    assert response.headers["content-type"] == "application/octet-stream"
    assert response.headers["content-disposition"].startswith("attachment;")
    assert "filename*=UTF-8''appunti%20%C3%A8.md" in response.headers["content-disposition"]
    assert response.headers["x-content-type-options"] == "nosniff"
    assert "no-store" in response.headers["cache-control"]

    other = auth_headers("intruder-downloads@example.com")
    denied = client.get(f"/api/v1/documents/{uploaded['id']}/file", headers=other)
    assert denied.status_code == 404
    unauthenticated = client.get(f"/api/v1/documents/{uploaded['id']}/file")
    assert unauthenticated.status_code == 401


def test_a_missing_stored_file_is_reported_not_crashed(client, learner, storage):
    headers, course_id, _ = learner
    uploaded = client.post(
        f"/api/v1/courses/{course_id}/documents",
        files={"file": ("a.txt", b"Testo.", "text/plain")},
        headers=headers,
    ).json()
    storage.delete(f"courses/{course_id}/documents/{uploaded['id']}")
    response = client.get(f"/api/v1/documents/{uploaded['id']}/file", headers=headers)
    assert response.status_code == 404
    assert response.json()["details"]["reason"] == "file_missing"


def test_s3_storage_round_trip_with_a_private_bucket():
    import boto3

    client = boto3.client(
        "s3", region_name="eu-west-1", aws_access_key_id="x", aws_secret_access_key="y"
    )
    storage = S3DocumentStorage(client, "learnable-private", prefix="app/")
    key = f"courses/{uuid.uuid4()}/documents/{uuid.uuid4()}"
    with Stubber(client) as stub:
        stub.add_response(
            "put_object", {}, {"Bucket": "learnable-private", "Key": f"app/{key}", "Body": b"PDF"}
        )
        stub.add_response(
            "get_object",
            {"Body": StreamingBody(io.BytesIO(b"PDF"), 3)},
            {"Bucket": "learnable-private", "Key": f"app/{key}"},
        )
        stub.add_client_error("get_object", service_error_code="NoSuchKey", http_status_code=404)
        stub.add_response("delete_object", {}, {"Bucket": "learnable-private", "Key": f"app/{key}"})
        storage.save(key, b"PDF")
        assert storage.load(key) == b"PDF"
        with pytest.raises(StoredFileMissingError):
            storage.load(key)
        storage.delete(key)
        stub.assert_no_pending_responses()


def test_s3_requires_a_bucket():
    from pydantic import ValidationError

    from app.core.config import Settings

    with pytest.raises(ValidationError, match="STORAGE_BUCKET"):
        Settings(auth_secret="s" * 40, storage_backend="s3", storage_bucket="")


def test_local_storage_leaves_no_partial_file_on_failure(tmp_path, monkeypatch):
    from app.storage.documents import LocalDocumentStorage

    storage = LocalDocumentStorage(tmp_path)

    def failing_replace(*_args):
        raise OSError("disk full")

    monkeypatch.setattr("app.storage.documents.os.replace", failing_replace)
    with pytest.raises(OSError, match="disk full"):
        storage.save("courses/a/documents/b", b"data")
    assert list(tmp_path.rglob("*.partial")) == []


def test_dashboard_default_weeks_constant():
    assert dashboard_service.DEFAULT_ACTIVITY_WEEKS == 12
