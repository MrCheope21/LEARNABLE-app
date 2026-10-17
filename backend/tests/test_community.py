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
    """A user with a course of one question, learned once (60 XP) when `xp`."""
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
    """ "I have studied this concept" and three correct rounds: 60 XP for one question."""
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
    assert [(e["name"], e["xp"], e["is_me"]) for e in entries] == [("Quiet", 60, True)]


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
    assert (first["rank"], first["name"], first["xp"]) == (1, "Leader", 120)
    tied = [e for e in entries if e["xp"] == 60]
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

    assert [xp(p) for p in ("day", "week", "month", "all")] == [60, 60, 60, 60]
    move(40)
    assert [xp(p) for p in ("day", "week", "month", "all")] == [0, 0, 0, 60]
    start = window_start(Period.WEEK)
    assert (start.weekday(), start.hour) == (0, 0)
    assert window_start(Period.ALL) is None


def test_friends_scope_shows_only_you_and_people_you_follow(client, auth_headers, db_session):
    me = make_learner(client, auth_headers, db_session, "me@example.com", "Me")
    pal = make_learner(client, auth_headers, db_session, "pal@example.com", "Pal")
    make_learner(client, auth_headers, db_session, "stranger@example.com", "Stranger")
    pal_id = board(client, me["headers"], period="all")["entries"]
    pal_id = next(e["user_id"] for e in pal_id if e["name"] == "Pal")
    assert (
        client.put(f"{API}/community/users/{pal_id}/follow", headers=me["headers"]).status_code
        == 200
    )
    names = [
        e["name"] for e in board(client, me["headers"], period="all", scope="friends")["entries"]
    ]
    assert sorted(names) == ["Me", "Pal"]
    assert pal["name"] == "Pal"


def test_profiles_following_and_friends(client, auth_headers, db_session):
    ada = make_learner(client, auth_headers, db_session, "ada@example.com", "Ada")
    bob = make_learner(client, auth_headers, db_session, "bob@example.com", "Bob")
    ada_id = client.get(f"{API}/auth/me", headers=ada["headers"]).json()["id"]
    bob_id = client.get(f"{API}/auth/me", headers=bob["headers"]).json()["id"]

    profile = client.get(f"{API}/community/users/{ada_id}", headers=bob["headers"]).json()
    assert (profile["name"], profile["xp_total"], profile["i_follow"], profile["follows_me"]) == (
        "Ada",
        60,
        False,
        False,
    )
    assert "email" not in profile

    followed = client.put(f"{API}/community/users/{ada_id}/follow", headers=bob["headers"]).json()
    assert (followed["i_follow"], followed["followers"]) == (True, 1)
    # Following twice changes nothing.
    assert (
        client.put(f"{API}/community/users/{ada_id}/follow", headers=bob["headers"]).json()[
            "followers"
        ]
        == 1
    )
    client.put(f"{API}/community/users/{bob_id}/follow", headers=ada["headers"])
    assert (
        client.get(f"{API}/community/users/{bob_id}", headers=ada["headers"]).json()["follows_me"]
        is True
    )

    [person] = client.get(f"{API}/community/following", headers=bob["headers"]).json()
    assert (person["name"], person["xp_today"], person["follows_me"]) == ("Ada", 60, True)
    [fan] = client.get(f"{API}/community/followers", headers=ada["headers"]).json()
    assert fan["name"] == "Bob"

    assert (
        client.delete(f"{API}/community/users/{ada_id}/follow", headers=bob["headers"]).status_code
        == 204
    )
    assert client.get(f"{API}/community/following", headers=bob["headers"]).json() == []


def test_hidden_people_cannot_be_seen_found_or_followed(client, auth_headers, db_session):
    seen = make_learner(client, auth_headers, db_session, "seen@example.com", "Seen")
    hidden = make_learner(
        client, auth_headers, db_session, "hidden@example.com", "Secret", visible=False
    )
    hidden_id = client.get(f"{API}/auth/me", headers=hidden["headers"]).json()["id"]
    assert (
        client.get(f"{API}/community/users/{hidden_id}", headers=seen["headers"]).status_code == 404
    )
    assert (
        client.put(f"{API}/community/users/{hidden_id}/follow", headers=seen["headers"]).status_code
        == 404
    )
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


def test_cannot_follow_yourself_and_search_needs_two_letters(client, auth_headers, db_session):
    me = make_learner(client, auth_headers, db_session, "solo@example.com", "Solo")
    my_id = client.get(f"{API}/auth/me", headers=me["headers"]).json()["id"]
    assert (
        client.put(f"{API}/community/users/{my_id}/follow", headers=me["headers"]).status_code
        == 409
    )
    assert (
        client.get(f"{API}/community/people", params={"q": "S"}, headers=me["headers"]).status_code
        == 422
    )


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
    assert [(e["name"], e["xp"]) for e in result["entries"]] == [("Priv", 60)]


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
    assert board(client, user["headers"], period="all")["entries"][0]["xp"] == shown == 60
