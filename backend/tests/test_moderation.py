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
