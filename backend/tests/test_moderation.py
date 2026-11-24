"""Tags to hear about, reports to the administrator, deleting your own account."""

import uuid

import pytest
from conftest import DEFAULT_PASSWORD
from sqlalchemy import select
from test_community import make_friends, make_learner, uid
from test_marketplace import API, PUBLISH, acquire, publish
from test_marketplace import author as author

from app.models.user import User


def _notifications(client, headers, kind):
    items = client.get(f"{API}/notifications", headers=headers).json()["items"]
    return [n for n in items if n["kind"] == kind]


@pytest.fixture
def admin(auth_headers, db_session):
    headers = auth_headers("boss@example.com")
    db_session.scalar(select(User).where(User.email == "boss@example.com")).is_admin = True
    db_session.commit()
    return headers


# --- Interests ---


def test_following_a_tag_tells_you_when_a_course_with_it_is_first_published(
    client, auth_headers, author
):
    reader = auth_headers("reader@example.com")
    other = auth_headers("other@example.com")
    followed = client.put(f"{API}/interests", json={"tag": "  #Diritto "}, headers=reader).json()
    assert followed["tags"] == ["diritto"]
    client.put(f"{API}/interests", json={"tag": "chimica"}, headers=other)
    # The author follows their own tag: they aren't told about their own course.
    client.put(f"{API}/interests", json={"tag": "esame"}, headers=author["headers"])

    listing = publish(client, author).json()
    told = _notifications(client, reader, "course_new")
    assert len(told) == 1
    assert told[0]["data"] == {
        "listing_id": listing["id"],
        "title": PUBLISH["title"],
        "tag": "diritto",
    }
    assert told[0]["link"] == f"/marketplace/{listing['id']}"
    assert told[0]["actor"] == "Prof. Rossi"
    assert _notifications(client, other, "course_new") == []
    assert _notifications(client, author["headers"], "course_new") == []

    # A new version isn't a new course: nobody is told again.
    publish(client, author)
    assert len(_notifications(client, reader, "course_new")) == 1


def test_interests_suggest_tags_in_use_and_can_be_removed(client, auth_headers, author):
    publish(client, author)
    reader = auth_headers("reader@example.com")
    assert client.get(f"{API}/interests", headers=reader).json() == {
        "tags": [],
        "suggestions": ["diritto", "esame"],
    }
    client.put(f"{API}/interests", json={"tag": "Esame"}, headers=reader)
    client.put(f"{API}/interests", json={"tag": "esame"}, headers=reader)  # twice: once
    state = client.get(f"{API}/interests", headers=reader).json()
    assert state == {"tags": ["esame"], "suggestions": ["diritto"]}
    gone = client.delete(f"{API}/interests", params={"tag": "ESAME"}, headers=reader).json()
    assert gone["tags"] == []
    assert client.put(f"{API}/interests", json={"tag": "x"}, headers=reader).status_code == 422


# --- Reports ---


def test_report_a_person_a_message_and_a_review(client, auth_headers, db_session, admin, author):
    ada = make_learner(client, auth_headers, db_session, "ada@example.com", "Ada", xp=False)
    bob = make_learner(client, auth_headers, db_session, "bob@example.com", "Bob", xp=False)
    make_friends(client, ada, bob)
    bob_id, ada_id = uid(client, bob), uid(client, ada)
    message = client.post(
        f"{API}/chats/{ada_id}", json={"body": "Testo offensivo"}, headers=bob["headers"]
    ).json()

    def report(headers, kind, target, reason=""):
        return client.post(
            f"{API}/reports",
            json={"kind": kind, "target_id": target, "reason": reason},
            headers=headers,
        )

    assert report(ada["headers"], "user", bob_id, "Nome falso").status_code == 204
    assert report(ada["headers"], "message", message["id"], "Insulti").status_code == 204
    # Only a message you received; never yourself; never something that doesn't exist.
    assert report(bob["headers"], "message", message["id"]).status_code == 404
    assert report(ada["headers"], "user", ada_id).status_code == 409
    assert report(ada["headers"], "user", str(uuid.uuid4())).status_code == 404

    listing = publish(client, author).json()
    acquire(client, bob["headers"], listing["id"])
    client.put(
        f"{API}/marketplace/listings/{listing['id']}/review",
        json={"rating": 1, "comment": "Spam spam"},
        headers=bob["headers"],
    )
    review = client.get(
        f"{API}/marketplace/listings/{listing['id']}/reviews", headers=author["headers"]
    ).json()["items"][0]
    assert report(author["headers"], "review", review["id"], "È spam").status_code == 204

    # People who aren't administrators can't read reports.
    assert client.get(f"{API}/admin/reports", headers=ada["headers"]).status_code == 403
    assert client.get(f"{API}/admin/summary", headers=admin).json()["open_reports"] == 3
    reports = client.get(f"{API}/admin/reports", headers=admin).json()
    by_kind = {r["kind"]: r for r in reports}
    assert by_kind["user"]["excerpt"] == "Bob"
    assert by_kind["user"]["reason"] == "Nome falso"
    assert by_kind["user"]["reporter_email"] == "ada@example.com"
    assert by_kind["message"]["excerpt"] == "Testo offensivo"
    assert by_kind["message"]["subject_email"] == "bob@example.com"
    assert by_kind["message"]["subject_reports"] == 3
    assert "Spam spam" in by_kind["review"]["excerpt"]
    assert by_kind["review"]["excerpt"].startswith(f"[{PUBLISH['title']}] ★ ")

    # Reporting the same thing again updates it instead of piling up.
    assert report(ada["headers"], "user", bob_id, "Ancora").status_code == 204
    assert len(client.get(f"{API}/admin/reports", headers=admin).json()) == 3

    rid = by_kind["message"]["id"]
    assert client.post(f"{API}/admin/reports/{rid}/resolve", headers=admin).status_code == 204
    reports = client.get(f"{API}/admin/reports", headers=admin).json()
    assert reports[-1]["id"] == rid
    assert reports[-1]["status"] == "RESOLVED"
    assert client.get(f"{API}/admin/summary", headers=admin).json()["open_reports"] == 2
    assert client.post(f"{API}/admin/reports/{rid}/reopen", headers=admin).status_code == 204
    assert client.get(f"{API}/admin/summary", headers=admin).json()["open_reports"] == 3

    # The report outlives the reported account, without the person.
    client.delete(f"{API}/admin/users/{bob_id}", headers=admin)
    reports = client.get(f"{API}/admin/reports", headers=admin).json()
    assert len(reports) == 3
    assert all(r["subject"] is None for r in reports)


# --- Deleting your own account ---


def test_delete_my_account_needs_the_password_and_removes_everything(
    client, auth_headers, db_session
):
    ada = make_learner(client, auth_headers, db_session, "ada@example.com", "Ada")
    bob = make_learner(client, auth_headers, db_session, "bob@example.com", "Bob", xp=False)
    make_friends(client, ada, bob)
    wrong = client.post(
        f"{API}/auth/delete-account", json={"password": "not-this-one"}, headers=ada["headers"]
    )
    assert wrong.status_code == 422
    assert wrong.json()["details"]["reason"] == "wrong_password"
    done = client.post(
        f"{API}/auth/delete-account", json={"password": DEFAULT_PASSWORD}, headers=ada["headers"]
    )
    assert done.status_code == 204
    assert client.get(f"{API}/auth/me", headers=ada["headers"]).status_code == 401
    assert db_session.scalar(select(User).where(User.email == "ada@example.com")) is None
    assert client.get(f"{API}/community/friends", headers=bob["headers"]).json() == []
    again = client.post(
        f"{API}/auth/login", json={"email": "ada@example.com", "password": DEFAULT_PASSWORD}
    )
    assert again.status_code == 401


def test_the_only_administrator_cannot_delete_their_account(
    client, admin, auth_headers, db_session
):
    refused = client.post(
        f"{API}/auth/delete-account", json={"password": DEFAULT_PASSWORD}, headers=admin
    )
    assert refused.status_code == 409
    assert refused.json()["details"]["reason"] == "last_admin"
    auth_headers("second@example.com")
    db_session.scalar(select(User).where(User.email == "second@example.com")).is_admin = True
    db_session.commit()
    assert (
        client.post(
            f"{API}/auth/delete-account", json={"password": DEFAULT_PASSWORD}, headers=admin
        ).status_code
        == 204
    )


def test_export_my_data_has_my_things_and_no_secrets(client, auth_headers, db_session):
    ada = make_learner(client, auth_headers, db_session, "ada@example.com", "Ada")
    bob = make_learner(client, auth_headers, db_session, "bob@example.com", "Bob", xp=False)
    make_friends(client, ada, bob)
    client.post(
        f"{API}/chats/{uid(client, bob)}", json={"body": "Ciao Bob"}, headers=ada["headers"]
    )
    response = client.get(f"{API}/auth/export", headers=ada["headers"])
    assert response.status_code == 200
    assert "attachment" in response.headers["content-disposition"]
    data = response.json()
    assert data["account"]["email"] == "ada@example.com"
    assert "hashed_password" not in data["account"]
    assert [c["title"] for c in data["courses"]] == ["Corso Ada"]
    assert len(data["learning_items"]) == 1
    assert len(data["answers"]) == 3
    assert sum(row["xp"] for row in data["xp"]) == 30
    assert [m["body"] for m in data["messages"]] == ["Ciao Bob"]
    assert len(data["friendships"]) == 1
    assert "bob@example.com" not in response.text


def test_exam_date_gives_a_daily_pace(client, auth_headers, db_session):
    from datetime import timedelta

    from app.db.types import utc_now

    ada = make_learner(client, auth_headers, db_session, "ada@example.com", "Ada")
    course = ada["course"]
    assert (
        client.get(f"{API}/courses/{course}/progress", headers=ada["headers"]).json()["exam"]
        is None
    )
    day = (utc_now() + timedelta(days=10)).date().isoformat()
    saved = client.put(
        f"{API}/courses/{course}/exam-date", json={"date": day}, headers=ada["headers"]
    )
    assert saved.json()["exam_date"] == day
    exam = client.get(f"{API}/courses/{course}/progress", headers=ada["headers"]).json()["exam"]
    # The one question is already learned: nothing new is left.
    assert (exam["days_left"], exam["new_left"], exam["new_per_day"], exam["status"]) == (
        10,
        0,
        0,
        "done",
    )
    assert exam["pace"] == 0.1
    cleared = client.put(
        f"{API}/courses/{course}/exam-date", json={"date": None}, headers=ada["headers"]
    )
    assert cleared.json()["exam_date"] is None


class FakePush:
    def __init__(self):
        self.sent = []
        self.gone = set()

    def send(self, subscription, payload):
        if subscription.endpoint in self.gone:
            return False
        self.sent.append((subscription.endpoint, payload))
        return True


def test_review_reminder_once_a_day_when_questions_are_due(client, auth_headers, db_session):
    from datetime import timedelta

    from app.db.types import utc_now
    from app.main import app
    from app.models.learning import ReviewState
    from app.services import push

    fake = FakePush()
    app.dependency_overrides[push.get_push_sender] = lambda: fake
    try:
        ada = make_learner(client, auth_headers, db_session, "ada@example.com", "Ada")
        client.patch(f"{API}/auth/me", json={"language": "it"}, headers=ada["headers"])
        sub = {
            "endpoint": "https://push.example/abc",
            "keys": {"p256dh": "k" * 40, "auth": "a" * 16},
        }
        status = client.post(f"{API}/push/subscribe", json=sub, headers=ada["headers"]).json()
        assert (status["enabled"], status["devices"], status["reminder_hour"]) == (True, 1, 18)
        client.post(f"{API}/push/subscribe", json=sub, headers=ada["headers"])  # same browser
        assert client.get(f"{API}/push", headers=ada["headers"]).json()["devices"] == 1
        assert client.post(f"{API}/push/test", headers=ada["headers"]).json() == {"sent": 1}
        fake.sent.clear()

        noon = utc_now().replace(hour=12, minute=0)
        evening = noon.replace(hour=19)
        # Nothing due yet, then one question becomes due.
        assert push.send_reminders(db_session, fake, evening) == 0
        for state in db_session.scalars(select(ReviewState)):
            state.due_at = noon - timedelta(hours=1)
        db_session.commit()
        client.put(f"{API}/push/reminder", json={"hour": 18}, headers=ada["headers"])
        db_session.expire_all()
        assert push.send_reminders(db_session, fake, noon) == 0  # before the hour
        assert push.send_reminders(db_session, fake, evening) == 1
        assert fake.sent == [
            (
                "https://push.example/abc",
                {
                    "title": "È ora di ripassare",
                    "body": "Hai 1 domande da ripassare.",
                    "url": "/review",
                },
            )
        ]
        assert push.send_reminders(db_session, fake, evening) == 0  # once a day
        # A browser that unsubscribed is forgotten.
        fake.gone.add("https://push.example/abc")
        assert push.send_reminders(db_session, fake, evening + timedelta(days=1)) == 0
        assert client.get(f"{API}/push", headers=ada["headers"]).json()["devices"] == 0
        off = client.put(f"{API}/push/reminder", json={"hour": None}, headers=ada["headers"])
        assert off.json()["reminder_hour"] is None
    finally:
        app.dependency_overrides.pop(push.get_push_sender, None)
