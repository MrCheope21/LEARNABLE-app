"""The community: opt-in leaderboards over time windows, profiles, following, course boards."""

from datetime import timedelta

import pytest
from test_marketplace import INFO, PUBLISH  # noqa: F401
from test_review import FULL, answer, concept, item
from test_xp_consolidation import studied

from app.db.types import utc_now
from app.models.rewards import XpAward
from app.schemas.community import Period
from app.services.community import window_start

API = "/api/v1"


def make_learner(client, auth_headers, db_session, email, name, visible=True, xp=True):
    """A user with a course of one question, learned once (30 XP) when `xp`."""
    headers = auth_headers(email)
    if name:
        client.patch(f"{API}/auth/me", json={"display_name": name}, headers=headers)
    if visible:
        assert (
            client.patch(
                f"{API}/auth/me", json={"community_visible": True}, headers=headers
            ).status_code
            == 200
        )
    course = client.post(
        f"{API}/courses", json={"title": f"Corso {name}", "language": "it"}, headers=headers
    ).json()
    chapter = client.post(
        f"{API}/courses/{course['id']}/chapters", json={"title": "C"}, headers=headers
    ).json()
    topic = client.post(
        f"{API}/chapters/{chapter['id']}/topics", json={"title": "T"}, headers=headers
    ).json()
    made = concept(client, headers, topic["id"])
    item(client, headers, made["id"])
    if xp:
        earn(client, headers, made["id"])
    return {"headers": headers, "course": course["id"], "topic": topic["id"], "name": name}


def earn(client, headers, concept_id):
    """ "I have studied this concept" and three correct rounds: 30 XP for one question."""
    session = studied(client, headers, concept_id).json()
    for _ in range(3):
        answer(client, headers, session["id"], FULL)


def board(client, headers, **params):
    response = client.get(f"{API}/community/leaderboard", params=params, headers=headers)
    assert response.status_code == 200, response.text
    return response.json()


def test_nobody_is_on_the_leaderboard_until_they_opt_in(client, auth_headers, db_session):
    quiet = make_learner(
        client, auth_headers, db_session, "quiet@example.com", "Quiet", visible=False
    )
    assert board(client, quiet["headers"], period="all")["entries"] == []
    assert board(client, quiet["headers"], period="all")["me_hidden"] is True

    client.patch(f"{API}/auth/me", json={"community_visible": True}, headers=quiet["headers"])
    entries = board(client, quiet["headers"], period="all")["entries"]
    assert [(e["name"], e["xp"], e["is_me"]) for e in entries] == [("Quiet", 30, True)]


def test_being_visible_needs_a_display_name_and_losing_it_hides_you(client, auth_headers):
    headers = auth_headers("nameless@example.com")
    refused = client.patch(f"{API}/auth/me", json={"community_visible": True}, headers=headers)
    assert refused.status_code == 422
    client.patch(
        f"{API}/auth/me", json={"display_name": "Nina", "community_visible": True}, headers=headers
    )
    assert client.get(f"{API}/auth/me", headers=headers).json()["community_visible"] is True
    client.patch(f"{API}/auth/me", json={"display_name": ""}, headers=headers)
    assert client.get(f"{API}/auth/me", headers=headers).json()["community_visible"] is False


def test_the_leaderboard_ranks_by_xp_with_ties_sharing_a_place(client, auth_headers, db_session):
    leader = make_learner(client, auth_headers, db_session, "lead@example.com", "Leader")
    other = make_learner(client, auth_headers, db_session, "other@example.com", "Other")
    third = make_learner(client, auth_headers, db_session, "third@example.com", "Third")
    # Leader earns more: a second question learned.
    made = concept(client, leader["headers"], leader["topic"], title="Altro")
    item(client, leader["headers"], made["id"], title="Altro")
    earn(client, leader["headers"], made["id"])

    entries = board(client, third["headers"], period="all")["entries"]
    first = entries[0]
    assert (first["rank"], first["name"], first["xp"]) == (1, "Leader", 60)
    tied = [e for e in entries if e["xp"] == 30]
    assert sorted(e["name"] for e in tied) == ["Other", "Third"]
    assert {e["rank"] for e in tied} == {2}
    assert other["name"] in {e["name"] for e in tied}
    me = board(client, third["headers"], period="all")["me"]
    assert (me["name"], me["rank"]) == ("Third", 2)


def test_windows_cover_the_day_week_month_and_all_time(client, auth_headers, db_session):
    user = make_learner(client, auth_headers, db_session, "win@example.com", "Win")

    # Everything so far happened just now. Move it back to see each window drop it.
    def move(days):
        for award in db_session.query(XpAward).all():
            award.awarded_at = utc_now() - timedelta(days=days)
        db_session.commit()

    def xp(period):
        entries = board(client, user["headers"], period=period)["entries"]
        return entries[0]["xp"] if entries else 0

    assert [xp(p) for p in ("day", "week", "month", "all")] == [30, 30, 30, 30]
    move(40)
    assert [xp(p) for p in ("day", "week", "month", "all")] == [0, 0, 0, 30]
    start = window_start(Period.WEEK)
    assert (start.weekday(), start.hour) == (0, 0)
    assert window_start(Period.ALL) is None


def uid(client, person):
    return client.get(f"{API}/auth/me", headers=person["headers"]).json()["id"]


def ask(client, who, whom_id):
    return client.put(f"{API}/community/users/{whom_id}/friend", headers=who["headers"])


def make_friends(client, a, b):
    assert ask(client, a, uid(client, b)).json()["relation"] == "request_sent"
    assert ask(client, b, uid(client, a)).json()["relation"] == "friends"


def inbox(client, person):
    return client.get(f"{API}/inbox", headers=person["headers"]).json()


def test_friends_scope_shows_only_you_and_your_friends(client, auth_headers, db_session):
    me = make_learner(client, auth_headers, db_session, "me@example.com", "Me")
    pal = make_learner(client, auth_headers, db_session, "pal@example.com", "Pal")
    asked = make_learner(client, auth_headers, db_session, "asked@example.com", "Asked")
    make_learner(client, auth_headers, db_session, "stranger@example.com", "Stranger")
    make_friends(client, me, pal)
    # A request that wasn't answered isn't a friendship.
    ask(client, me, uid(client, asked))
    entries = board(client, me["headers"], period="all", scope="friends")["entries"]
    assert sorted(e["name"] for e in entries) == ["Me", "Pal"]
    everyone = {
        e["name"]: e["relation"] for e in board(client, me["headers"], period="all")["entries"]
    }
    assert everyone == {
        "Me": "none",
        "Pal": "friends",
        "Asked": "request_sent",
        "Stranger": "none",
    }


def test_a_friend_request_is_seen_accepted_and_notified(client, auth_headers, db_session):
    ada = make_learner(client, auth_headers, db_session, "ada@example.com", "Ada")
    bob = make_learner(client, auth_headers, db_session, "bob@example.com", "Bob")
    ada_id, bob_id = uid(client, ada), uid(client, bob)

    profile = client.get(f"{API}/community/users/{ada_id}", headers=bob["headers"]).json()
    assert (profile["name"], profile["xp_total"], profile["relation"], profile["friends"]) == (
        "Ada",
        30,
        "none",
        0,
    )
    assert "email" not in profile

    sent = ask(client, bob, ada_id).json()
    assert sent["relation"] == "request_sent"
    # Asking twice changes nothing.
    assert ask(client, bob, ada_id).json()["relation"] == "request_sent"

    # Ada sees it: in her requests, on her badge and in her notifications.
    requests = client.get(f"{API}/community/friend-requests", headers=ada["headers"]).json()
    assert [(p["name"], p["relation"]) for p in requests["incoming"]] == [
        ("Bob", "request_received")
    ]
    assert requests["incoming"][0]["requested_at"] is not None
    assert requests["outgoing"] == []
    assert inbox(client, ada) == {"notifications": 1, "messages": 0, "friend_requests": 1}
    [note] = client.get(f"{API}/notifications", headers=ada["headers"]).json()["items"]
    assert (note["kind"], note["actor"], note["read"]) == ("friend_request", "Bob", False)
    # Bob sees it as sent.
    mine = client.get(f"{API}/community/friend-requests", headers=bob["headers"]).json()
    assert [p["name"] for p in mine["outgoing"]] == ["Ada"]
    assert client.get(f"{API}/community/friends", headers=bob["headers"]).json() == []

    # Accepting is asking back.
    assert ask(client, ada, bob_id).json()["relation"] == "friends"
    [friend] = client.get(f"{API}/community/friends", headers=bob["headers"]).json()
    assert (friend["name"], friend["xp_today"], friend["relation"]) == ("Ada", 30, "friends")
    assert client.get(f"{API}/community/friend-requests", headers=ada["headers"]).json() == {
        "incoming": [],
        "outgoing": [],
    }
    assert inbox(client, ada)["friend_requests"] == 0
    [accepted] = client.get(f"{API}/notifications", headers=bob["headers"]).json()["items"]
    assert (accepted["kind"], accepted["actor"]) == ("friend_accepted", "Ada")
    assert (
        client.get(f"{API}/community/users/{ada_id}", headers=bob["headers"]).json()["friends"] == 1
    )

    # Either can end it.
    assert (
        client.delete(f"{API}/community/users/{ada_id}/friend", headers=bob["headers"]).status_code
        == 204
    )
    assert client.get(f"{API}/community/friends", headers=ada["headers"]).json() == []


def test_a_request_can_be_declined_or_cancelled_and_asked_again(client, auth_headers, db_session):
    ada = make_learner(client, auth_headers, db_session, "ada@example.com", "Ada")
    bob = make_learner(client, auth_headers, db_session, "bob@example.com", "Bob")
    ada_id, bob_id = uid(client, ada), uid(client, bob)

    ask(client, bob, ada_id)
    # Declined by Ada: the request and its notification go, Bob isn't told.
    client.delete(f"{API}/community/users/{bob_id}/friend", headers=ada["headers"])
    assert inbox(client, ada) == {"notifications": 0, "messages": 0, "friend_requests": 0}
    assert client.get(f"{API}/notifications", headers=bob["headers"]).json()["items"] == []
    assert (
        client.get(f"{API}/community/users/{ada_id}", headers=bob["headers"]).json()["relation"]
        == "none"
    )

    # Asked again, then cancelled by Bob.
    ask(client, bob, ada_id)
    assert inbox(client, ada)["friend_requests"] == 1
    client.delete(f"{API}/community/users/{ada_id}/friend", headers=bob["headers"])
    assert inbox(client, ada) == {"notifications": 0, "messages": 0, "friend_requests": 0}


def test_notifications_can_be_marked_read(client, auth_headers, db_session):
    ada = make_learner(client, auth_headers, db_session, "ada@example.com", "Ada")
    bob = make_learner(client, auth_headers, db_session, "bob@example.com", "Bob")
    ask(client, bob, uid(client, ada))
    assert inbox(client, ada)["notifications"] == 1
    assert (
        client.post(f"{API}/notifications/read", json={}, headers=ada["headers"]).status_code == 204
    )
    listed = client.get(f"{API}/notifications", headers=ada["headers"]).json()
    assert (listed["unread"], listed["items"][0]["read"]) == (0, True)
    # Nobody reads someone else's.
    assert client.get(f"{API}/notifications", headers=bob["headers"]).json()["items"] == []


def test_hidden_people_cannot_be_seen_found_or_asked(client, auth_headers, db_session):
    seen = make_learner(client, auth_headers, db_session, "seen@example.com", "Seen")
    hidden = make_learner(
        client, auth_headers, db_session, "hidden@example.com", "Secret", visible=False
    )
    hidden_id = uid(client, hidden)
    assert (
        client.get(f"{API}/community/users/{hidden_id}", headers=seen["headers"]).status_code == 404
    )
    assert ask(client, seen, hidden_id).status_code == 404
    assert (
        client.get(
            f"{API}/community/people", params={"q": "Secret"}, headers=seen["headers"]
        ).json()
        == []
    )
    # Your own profile is always yours to see.
    assert (
        client.get(f"{API}/community/users/{hidden_id}", headers=hidden["headers"]).status_code
        == 200
    )
    # Someone who hasn't joined can't ask either: the other person couldn't see who it is.
    refused = ask(client, hidden, uid(client, seen))
    assert (refused.status_code, refused.json()["details"]["reason"]) == (409, "not_visible")


def test_cannot_befriend_yourself_and_search_needs_two_letters(client, auth_headers, db_session):
    me = make_learner(client, auth_headers, db_session, "solo@example.com", "Solo")
    assert ask(client, me, uid(client, me)).status_code == 409
    assert (
        client.get(f"{API}/community/people", params={"q": "S"}, headers=me["headers"]).status_code
        == 422
    )


def test_blocking_ends_everything_and_hides_both_ways(client, auth_headers, db_session):
    ada = make_learner(client, auth_headers, db_session, "ada@example.com", "Ada")
    bob = make_learner(client, auth_headers, db_session, "bob@example.com", "Bob")
    ada_id, bob_id = uid(client, ada), uid(client, bob)
    make_friends(client, ada, bob)

    assert (
        client.put(f"{API}/community/users/{bob_id}/block", headers=ada["headers"]).status_code
        == 204
    )
    assert client.get(f"{API}/community/friends", headers=bob["headers"]).json() == []
    # Bob can't find, see or ask Ada any more; Ada doesn't find Bob either.
    for person, name in ((bob, "Ada"), (ada, "Bob")):
        found = client.get(
            f"{API}/community/people", params={"q": name}, headers=person["headers"]
        ).json()
        assert found == []
    assert client.get(f"{API}/community/users/{ada_id}", headers=bob["headers"]).status_code == 404
    assert ask(client, bob, ada_id).status_code == 404
    assert ask(client, ada, bob_id).status_code == 404
    # Ada still reaches Bob's page, to unblock.
    assert client.get(f"{API}/community/users/{bob_id}", headers=ada["headers"]).json()["blocked"]
    assert [
        p["name"] for p in client.get(f"{API}/community/blocked", headers=ada["headers"]).json()
    ] == ["Bob"]
    client.delete(f"{API}/community/users/{bob_id}/block", headers=ada["headers"])
    assert ask(client, bob, ada_id).json()["relation"] == "request_sent"


def test_people_are_found_by_exact_username_too(client, auth_headers, db_session):
    me = make_learner(client, auth_headers, db_session, "finder@example.com", "Finder")
    maria = make_learner(client, auth_headers, db_session, "maria@example.com", "Maria Rossi")
    client.patch(f"{API}/auth/me", json={"username": "mrossi.99"}, headers=maria["headers"])

    def find(q):
        found = client.get(f"{API}/community/people", params={"q": q}, headers=me["headers"])
        return [p["name"] for p in found.json()]

    assert find("mrossi.99") == ["Maria Rossi"]
    assert find("@MRossi.99") == ["Maria Rossi"]
    # Only the whole username: part of it finds nobody (usernames are sign-in names).
    assert find("mross") == []


# --- Messages ---


def send(client, who, whom_id, body="Ciao!"):
    return client.post(f"{API}/chats/{whom_id}", json={"body": body}, headers=who["headers"])


def test_friends_write_to_each_other_and_unread_counts_follow(client, auth_headers, db_session):
    ada = make_learner(client, auth_headers, db_session, "ada@example.com", "Ada", xp=False)
    bob = make_learner(client, auth_headers, db_session, "bob@example.com", "Bob", xp=False)
    ada_id, bob_id = uid(client, ada), uid(client, bob)
    make_friends(client, ada, bob)

    first = send(client, ada, bob_id, "  Come va lo studio?  ")
    assert first.status_code == 201, first.text
    assert (first.json()["body"], first.json()["mine"]) == ("Come va lo studio?", True)
    send(client, ada, bob_id, "Domani ripassiamo insieme?")

    assert inbox(client, bob)["messages"] == 2
    [chat] = client.get(f"{API}/chats", headers=bob["headers"]).json()
    assert (chat["name"], chat["unread"], chat["last_message"], chat["last_mine"]) == (
        "Ada",
        2,
        "Domani ripassiamo insieme?",
        False,
    )
    thread = client.get(f"{API}/chats/{ada_id}", headers=bob["headers"]).json()
    assert [(m["body"], m["mine"]) for m in thread["messages"]] == [
        ("Come va lo studio?", False),
        ("Domani ripassiamo insieme?", False),
    ]
    assert (thread["can_send"], thread["has_more"]) == (True, False)
    # Opening the chat read them.
    assert inbox(client, bob)["messages"] == 0
    assert client.get(f"{API}/chats", headers=bob["headers"]).json()[0]["unread"] == 0
    seen = client.get(f"{API}/chats/{bob_id}", headers=ada["headers"]).json()
    assert all(m["read"] for m in seen["messages"])

    assert send(client, bob, ada_id, "Sì!").status_code == 201
    assert client.get(f"{API}/chats", headers=ada["headers"]).json()[0]["last_message"] == "Sì!"


def test_only_friends_can_write_and_the_history_survives(client, auth_headers, db_session):
    ada = make_learner(client, auth_headers, db_session, "ada@example.com", "Ada", xp=False)
    bob = make_learner(client, auth_headers, db_session, "bob@example.com", "Bob", xp=False)
    eve = make_learner(client, auth_headers, db_session, "eve@example.com", "Eve", xp=False)
    ada_id, bob_id = uid(client, ada), uid(client, bob)

    # Not friends: no writing, and no chat to open.
    assert send(client, eve, ada_id).status_code == 403
    assert client.get(f"{API}/chats/{ada_id}", headers=eve["headers"]).status_code == 404
    # A pending request isn't enough.
    ask(client, bob, ada_id)
    assert send(client, bob, ada_id).status_code == 403

    ask(client, ada, bob_id)
    assert send(client, bob, ada_id, "Ciao Ada").status_code == 201
    assert send(client, bob, ada_id, "").status_code == 422
    assert send(client, bob, ada_id, "x" * 2001).status_code == 422

    # No longer friends: the history stays, nothing new goes.
    client.delete(f"{API}/community/users/{bob_id}/friend", headers=ada["headers"])
    assert send(client, bob, ada_id).status_code == 403
    thread = client.get(f"{API}/chats/{bob_id}", headers=ada["headers"]).json()
    assert (thread["can_send"], [m["body"] for m in thread["messages"]]) == (False, ["Ciao Ada"])
    assert client.get(f"{API}/chats", headers=ada["headers"]).json()[0]["can_send"] is False
    # A third person never reads it.
    assert client.get(f"{API}/chats/{bob_id}", headers=eve["headers"]).status_code == 404
    assert client.get(f"{API}/chats", headers=eve["headers"]).json() == []


def test_older_messages_come_in_pages(client, auth_headers, db_session):
    ada = make_learner(client, auth_headers, db_session, "ada@example.com", "Ada", xp=False)
    bob = make_learner(client, auth_headers, db_session, "bob@example.com", "Bob", xp=False)
    ada_id, bob_id = uid(client, ada), uid(client, bob)
    make_friends(client, ada, bob)
    import uuid as _uuid

    from app.models.community import Message, pair_key

    start = utc_now() - timedelta(hours=1)
    a, b = _uuid.UUID(ada_id), _uuid.UUID(bob_id)
    for n in range(60):
        db_session.add(
            Message(
                pair_key=pair_key(a, b),
                sender_id=a,
                recipient_id=b,
                body=f"m{n}",
                created_at=start + timedelta(seconds=n),
            )
        )
    db_session.commit()
    latest = client.get(f"{API}/chats/{ada_id}", headers=bob["headers"]).json()
    assert (len(latest["messages"]), latest["has_more"]) == (50, True)
    assert (latest["messages"][0]["body"], latest["messages"][-1]["body"]) == ("m10", "m59")
    older = client.get(
        f"{API}/chats/{ada_id}",
        params={"before": latest["messages"][0]["id"]},
        headers=bob["headers"],
    ).json()
    assert ([m["body"] for m in older["messages"]][-1], older["has_more"]) == ("m9", False)
    assert len(older["messages"]) == 10


def test_search_finds_visible_people_by_name_and_never_shows_emails(
    client, auth_headers, db_session
):
    me = make_learner(client, auth_headers, db_session, "finder@example.com", "Finder")
    make_learner(client, auth_headers, db_session, "maria@example.com", "Maria Rossi")
    response = client.get(f"{API}/community/people", params={"q": "rossi"}, headers=me["headers"])
    assert [p["name"] for p in response.json()] == ["Maria Rossi"]
    assert "maria@example.com" not in response.text
    # % and _ are not wildcards.
    assert (
        client.get(f"{API}/community/people", params={"q": "%%"}, headers=me["headers"]).json()
        == []
    )


def test_a_private_course_board_is_just_you(client, auth_headers, db_session):
    me = make_learner(client, auth_headers, db_session, "priv@example.com", "Priv")
    result = client.get(
        f"{API}/courses/{me['course']}/leaderboard", params={"period": "all"}, headers=me["headers"]
    ).json()
    assert result["participants"] == 1
    assert [(e["name"], e["xp"]) for e in result["entries"]] == [("Priv", 30)]


def test_a_marketplace_course_board_ranks_everyone_who_has_it_by_that_course_only(
    client, auth_headers, db_session
):
    author = make_learner(client, auth_headers, db_session, "auth@example.com", "Author", xp=False)
    client.post(
        f"{API}/courses/{author['course']}/marketplace/publish",
        json=PUBLISH,
        headers=author["headers"],
    )
    listing = client.get(
        f"{API}/courses/{author['course']}/marketplace", headers=author["headers"]
    ).json()["listing"]

    buyer = make_learner(client, auth_headers, db_session, "buy@example.com", "Buyer", xp=False)
    course_id = client.post(
        f"{API}/marketplace/listings/{listing['id']}/acquire", headers=buyer["headers"]
    ).json()["course_id"]
    # Buyer earns XP in the shared course, and some in their own unrelated course.
    outline = client.get(f"{API}/courses/{course_id}/outline", headers=buyer["headers"]).json()
    [shared] = outline[0]["topics"][0]["concepts"]
    client.post(f"{API}/concepts/{shared['id']}/activate", headers=buyer["headers"])
    earn(client, buyer["headers"], shared["id"])
    own_outline = client.get(
        f"{API}/courses/{buyer['course']}/outline", headers=buyer["headers"]
    ).json()
    own = own_outline[0]["topics"][0]["concepts"][0]
    item(client, buyer["headers"], own["id"], title="Mio")
    earn(client, buyer["headers"], own["id"])

    result = client.get(
        f"{API}/courses/{course_id}/leaderboard", params={"period": "all"}, headers=buyer["headers"]
    ).json()
    assert result["participants"] == 2
    [entry] = result["entries"]
    assert entry["name"] == "Buyer"
    shared_xp = entry["xp"]
    everywhere = board(client, buyer["headers"], period="all")["entries"][0]["xp"]
    assert everywhere > shared_xp > 0
    # The author sees the same board from their own course.
    seen = client.get(
        f"{API}/courses/{author['course']}/leaderboard",
        params={"period": "all"},
        headers=author["headers"],
    ).json()
    assert [e["name"] for e in seen["entries"]] == ["Buyer"]


def test_others_cannot_read_a_course_board(client, auth_headers, db_session):
    owner = make_learner(client, auth_headers, db_session, "own@example.com", "Own")
    stranger = auth_headers("nosy@example.com")
    assert (
        client.get(f"{API}/courses/{owner['course']}/leaderboard", headers=stranger).status_code
        == 404
    )


@pytest.mark.parametrize("period", ["hour", "forever"])
def test_unknown_periods_are_refused(client, auth_headers, period):
    headers = auth_headers("p@example.com")
    assert (
        client.get(
            f"{API}/community/leaderboard", params={"period": period}, headers=headers
        ).status_code
        == 422
    )


def test_leaderboard_xp_matches_the_dashboard_total(client, auth_headers, db_session):
    user = make_learner(client, auth_headers, db_session, "same@example.com", "Same")
    shown = client.get(f"{API}/dashboard", headers=user["headers"]).json()["xp"]["total"]
    assert board(client, user["headers"], period="all")["entries"][0]["xp"] == shown == 30


def test_a_username_makes_you_findable_and_addable_without_joining(
    client, auth_headers, db_session
):
    """Someone outside the community is found by their exact username only, shown as
    @username, and can be friends and exchange messages; leaderboards stay opt-in."""
    seen = make_learner(client, auth_headers, db_session, "seen@example.com", "Seen")
    quiet = make_learner(client, auth_headers, db_session, "quiet@example.com", "", visible=False)
    client.patch(f"{API}/auth/me", json={"username": "quiet_one"}, headers=quiet["headers"])

    def find(q):
        return client.get(
            f"{API}/community/people", params={"q": q}, headers=seen["headers"]
        ).json()

    assert find("quiet") == []  # part of a username finds nobody
    found = find("@Quiet_One")
    assert [p["name"] for p in found] == ["@quiet_one"]
    quiet_id = found[0]["user_id"]
    assert ask(client, seen, quiet_id).json()["relation"] == "request_sent"
    assert inbox(client, quiet)["friend_requests"] == 1
    assert ask(client, quiet, uid(client, seen)).json()["relation"] == "friends"
    names = [
        p["name"] for p in client.get(f"{API}/community/friends", headers=seen["headers"]).json()
    ]
    assert names == ["@quiet_one"]
    sent = client.post(f"{API}/chats/{quiet_id}", json={"body": "Ciao"}, headers=seen["headers"])
    assert sent.status_code == 201
    board = client.get(
        f"{API}/community/leaderboard", params={"period": "all"}, headers=seen["headers"]
    ).json()
    assert [e["name"] for e in board["entries"]] == ["Seen"]
