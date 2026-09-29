"""Consolidation rounds, progressive XP and hints (docs/XP_AND_ACTIVITY.md, SCHEDULING.md §4a).

The mock evaluator grades by overlap with the item's essential points: FULL → CORRECT (GOOD),
PARTIAL → PARTIALLY_CORRECT (HARD), WRONG → AGAIN.
"""

from datetime import timedelta

import pytest
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from test_review import (
    FULL,
    PARTIAL,
    WRONG,
    answer,
    card,
    concept,
    item,
    make_due,
    memory,
    start,
)

from app.ai.factory import get_ai_provider
from app.main import app
from app.models.enums import EvaluationClassification, ReviewOutcome, XpReason
from app.models.rewards import XpAward
from app.services.rewards import policy

# --- The XP rule (pure) ---


@pytest.mark.parametrize(
    ("ordinal", "plain", "hinted"),
    [
        (1, 10, 5),
        (2, 20, 10),
        (3, 30, 15),
        (4, 40, 20),
        (14, 140, 70),
        (15, 150, 75),
        (40, 150, 75),
    ],
)
def test_progressive_xp_and_hint_halving(ordinal, plain, hinted):
    assert policy.base_xp(ordinal) == plain
    assert policy.awarded_xp(ordinal, hint_used=False) == plain
    assert policy.awarded_xp(ordinal, hint_used=True) == hinted


@pytest.mark.parametrize(
    ("classification", "outcome", "correct"),
    [
        (EvaluationClassification.CORRECT, ReviewOutcome.GOOD, True),
        (EvaluationClassification.CORRECT, ReviewOutcome.HARD, True),
        # Partial credit is not correctness: no XP, the counter doesn't move.
        (EvaluationClassification.PARTIALLY_CORRECT, ReviewOutcome.HARD, False),
        (EvaluationClassification.WRONG, ReviewOutcome.AGAIN, False),
        (EvaluationClassification.CORRECT, None, False),
        (None, ReviewOutcome.GOOD, False),
    ],
)
def test_what_counts_as_correct(classification, outcome, correct):
    assert policy.is_correct(classification, outcome) is correct


# --- Helpers ---


@pytest.fixture
def course(client, auth_headers):
    headers = auth_headers("consolidator@example.com")
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


def studied(client, headers, concept_id):
    """ "I have studied this concept"."""
    return client.post(f"/api/v1/concepts/{concept_id}/consolidation", headers=headers)


def plan(client, headers, concept_id):
    return client.get(f"/api/v1/concepts/{concept_id}/consolidation", headers=headers).json()


def hint(client, headers, session_id):
    return client.post(f"/api/v1/review-sessions/{session_id}/hint", headers=headers)


def xp_of(result):
    return result["xp"]["xp"] if result["xp"] else None


def dashboard(client, headers):
    return client.get("/api/v1/dashboard", headers=headers).json()


# --- Consolidation ---


def test_three_correct_rounds_earn_60_xp_and_encode_once(client, course, db_session):
    headers, _, topic_id = course
    c = concept(client, headers, topic_id)
    it = item(client, headers, c["id"])

    before = plan(client, headers, c["id"])
    assert (before["new_items"], before["batch_items"], before["answers_in_batch"]) == (1, 1, 3)
    assert before["unfinished"] is None

    session = studied(client, headers, c["id"]).json()
    assert (session["intent"], session["total"]) == ("CONSOLIDATION", 3)

    awards = []
    for expected_round in (1, 2, 3):
        shown = card(client, headers, session["id"])["card"]
        assert (shown["round"], shown["rounds_total"]) == (expected_round, 3)
        assert shown["potential_xp"]["xp"] == 10 * expected_round
        assert shown["introduction"] is None  # studied already: straight to recall
        result = answer(client, headers, session["id"], FULL).json()
        assert result["consolidation_round"] == expected_round
        awards.append(xp_of(result))
        if expected_round < 3:
            # Rounds seconds apart aren't reviews: nothing is scheduled until the last one.
            assert result["schedule"] is None
            assert memory(db_session, it["id"]).state.value == "NEW"
        else:
            assert (result["schedule"]["previous_state"], result["schedule"]["next_level"]) == (
                "NEW",
                1,
            )

    assert awards == [10, 20, 30]
    assert card(client, headers, session["id"])["done"] is True
    assert card(client, headers, session["id"])["session"]["xp_earned"] == 60
    state = memory(db_session, it["id"])
    assert (state.state.value, state.level) == ("LEARNING", 1)  # not an inflated interval
    history = client.get(f"/api/v1/learning-items/{it['id']}/reviews", headers=headers).json()
    assert [(r["intent"], r["outcome"]) for r in history] == [("CONSOLIDATION", "GOOD")]
    assert dashboard(client, headers)["xp"] == {"total": 60, "today": 60}


def test_three_rounds_not_three_correct_answers(client, course):
    headers, _, topic_id = course
    c = concept(client, headers, topic_id)
    item(client, headers, c["id"])
    session = studied(client, headers, c["id"]).json()

    results = [answer(client, headers, session["id"], text).json() for text in (FULL, WRONG, FULL)]

    # Incorrect earns nothing and neither advances nor resets the success counter.
    assert [xp_of(r) for r in results] == [10, 0, 20]
    assert [r["xp"]["ordinal"] for r in results] == [1, None, 2]
    assert card(client, headers, session["id"])["done"] is True


def test_a_failed_last_round_leaves_the_item_new(client, course, db_session):
    headers, _, topic_id = course
    c = concept(client, headers, topic_id)
    it = item(client, headers, c["id"])
    session = studied(client, headers, c["id"]).json()
    for text in (FULL, FULL, WRONG):
        answer(client, headers, session["id"], text)

    assert memory(db_session, it["id"]).state.value == "NEW"
    # The next batch repeats the item, but its three XP-eligible rounds are spent.
    again = studied(client, headers, c["id"]).json()
    assert again["id"] != session["id"]
    shown = card(client, headers, again["id"])["card"]
    assert shown["potential_xp"]["eligible"] is False
    assert xp_of(answer(client, headers, again["id"], FULL).json()) is None


def test_partial_answers_earn_nothing(client, course):
    headers, _, topic_id = course
    c = concept(client, headers, topic_id)
    item(client, headers, c["id"])
    session = studied(client, headers, c["id"]).json()

    result = answer(client, headers, session["id"], PARTIAL).json()

    assert result["final_outcome"] == "HARD"
    assert (result["xp"]["correct"], result["xp"]["xp"], result["xp"]["ordinal"]) == (
        False,
        0,
        None,
    )


def test_an_interrupted_batch_resumes_without_replaying_rounds(client, course):
    headers, _, topic_id = course
    c = concept(client, headers, topic_id)
    item(client, headers, c["id"], title="Primo")
    item(client, headers, c["id"], title="Secondo")
    session = studied(client, headers, c["id"]).json()
    assert session["total"] == 6
    answer(client, headers, session["id"], FULL)  # round 1 of the first item

    # Clicking "I have studied this concept" again resumes; it never resets rewarded rounds.
    shown_plan = plan(client, headers, c["id"])
    assert shown_plan["unfinished"]["id"] == session["id"]
    resumed = studied(client, headers, c["id"]).json()
    assert (resumed["id"], resumed["position"]) == (session["id"], 1)
    next_card = card(client, headers, session["id"])["card"]
    assert (next_card["round"], next_card["potential_xp"]["xp"]) == (2, 20)

    # Leaving (end) and coming back also resumes nothing twice: an ended batch isn't reopened,
    # and a new batch only takes items still NEW, whose spent rounds earn nothing more.
    rest = [answer(client, headers, session["id"], FULL).json() for _ in range(5)]
    assert [xp_of(r) for r in rest] == [20, 30, 10, 20, 30]
    assert studied(client, headers, c["id"]).json()["details"]["reason"] == "nothing_to_consolidate"


def test_batches_split_large_concepts(client, course):
    headers, _, topic_id = course
    c = concept(client, headers, topic_id)
    for n in range(7):
        item(client, headers, c["id"], title=f"Voce {n}")

    shown = plan(client, headers, c["id"])
    assert (shown["new_items"], shown["batch_items"], shown["remaining_after_batch"]) == (7, 5, 2)
    session = studied(client, headers, c["id"]).json()
    assert session["total"] == 15


def test_consolidation_needs_waiting_items(client, course):
    headers, course_id, topic_id = course
    inactive = concept(client, headers, topic_id, title="Spento", active=False)
    response = studied(client, headers, inactive["id"])
    assert response.status_code == 409
    assert response.json()["details"] == {
        "reason": "nothing_to_consolidate",
        "concept_active": False,
    }
    # Not through the generic endpoint either.
    generic = start(client, headers, course_id, intent="CONSOLIDATION")
    assert generic.status_code == 422
    assert generic.json()["details"]["reason"] == "use_concept_consolidation"


# --- Hints ---


def test_a_hint_halves_xp_and_survives_a_reload(client, course):
    headers, _, topic_id = course
    c = concept(client, headers, topic_id)
    item(
        client,
        headers,
        c["id"],
        expected_knowledge=(
            "Il mutuo e il contratto con cui una parte consegna all'altra una somma di denaro, "
            "e l'altra si obbliga a restituire altrettante cose della stessa specie."
        ),
        essential_points=["consegna di denaro", "obbligo di restituzione"],
    )
    session = studied(client, headers, c["id"]).json()
    shown = card(client, headers, session["id"])["card"]
    assert shown["hint"] == {"available": True, "revealed": False, "text": None}
    assert shown["potential_xp"]["xp_with_hint"] == 5

    revealed = hint(client, headers, session["id"]).json()
    assert revealed["revealed"] is True
    assert revealed["text"].endswith("…")
    assert "restituzione" not in revealed["text"]  # a cue, not the answer
    # Reloading shows it again; asking again returns the same hint, still one halving.
    assert card(client, headers, session["id"])["card"]["hint"] == revealed
    assert hint(client, headers, session["id"]).json() == revealed

    first = answer(client, headers, session["id"], FULL).json()
    assert (first["hint_used"], first["xp"]["xp"], first["xp"]["base_xp"]) == (True, 5, 10)
    # The penalty is for that attempt only; the counter advanced.
    second = answer(client, headers, session["id"], FULL).json()
    assert (second["hint_used"], xp_of(second)) == (False, 20)


def test_no_hint_when_the_reference_is_too_short(client, course, db_session):
    headers, _, topic_id = course
    c = concept(client, headers, topic_id)
    item(client, headers, c["id"], expected_knowledge="Sì.", essential_points=[])
    session = studied(client, headers, c["id"]).json()

    assert card(client, headers, session["id"])["card"]["hint"]["available"] is False
    response = hint(client, headers, session["id"])
    assert response.status_code == 409
    assert response.json()["details"]["reason"] == "hint_unavailable"
    # A failed hint request costs nothing.
    assert xp_of(answer(client, headers, session["id"], "Sì.").json()) in (0, 10)
    result = client.get(f"/api/v1/review-sessions/{session['id']}", headers=headers).json()
    assert result["id"] == session["id"]


def test_hint_after_answering_is_refused(client, course, ai_provider):
    headers, _, topic_id = course
    c = concept(client, headers, topic_id)
    item(client, headers, c["id"])
    session = studied(client, headers, c["id"]).json()
    app.dependency_overrides[get_ai_provider] = lambda: None
    answer(client, headers, session["id"], FULL)  # pending: no evaluation available

    response = hint(client, headers, session["id"])
    assert response.status_code == 409
    assert response.json()["details"]["reason"] == "answer_pending"


# --- Eligibility and anti-farming ---


def test_self_graded_answers_earn_no_correctness_xp(client, course):
    headers, _, topic_id = course
    c = concept(client, headers, topic_id)
    item(client, headers, c["id"])
    session = studied(client, headers, c["id"]).json()
    app.dependency_overrides[get_ai_provider] = lambda: None

    pending = answer(client, headers, session["id"], FULL).json()
    assert pending["xp"] is None  # not finalized yet
    graded = client.post(
        f"/api/v1/answers/{pending['answer_id']}/override",
        json={"outcome": "EASY"},
        headers=headers,
    ).json()

    assert graded["final_outcome"] == "EASY"
    assert (graded["xp"]["correct"], graded["xp"]["xp"]) == (False, 0)
    # The attempt still counts as study activity.
    assert dashboard(client, headers)["goal"]["done"] == 1


def test_a_later_regrade_never_changes_the_award(client, course):
    headers, _, topic_id = course
    c = concept(client, headers, topic_id)
    item(client, headers, c["id"])
    session = studied(client, headers, c["id"]).json()
    wrong = answer(client, headers, session["id"], WRONG).json()
    assert xp_of(wrong) == 0

    upgraded = client.post(
        f"/api/v1/answers/{wrong['answer_id']}/override",
        json={"outcome": "EASY"},
        headers=headers,
    ).json()
    assert upgraded["final_outcome"] == "EASY"
    assert xp_of(upgraded) == 0
    assert dashboard(client, headers)["xp"]["total"] == 0


def test_scheduled_reviews_earn_once_per_due_date(client, course, db_session):
    headers, course_id, topic_id = course
    c = concept(client, headers, topic_id)
    it = item(client, headers, c["id"])
    session = studied(client, headers, c["id"]).json()
    for _ in range(3):
        answer(client, headers, session["id"], FULL)

    # Not due: no review pool at all; practice earns nothing.
    assert start(client, headers, course_id, intent="SCHEDULED_REVIEW").status_code == 409
    practice = start(client, headers, course_id, intent="PRACTICE").json()
    assert answer(client, headers, practice["id"], FULL).json()["xp"] is None

    make_due(db_session, it["id"])
    review = start(client, headers, course_id, intent="SCHEDULED_REVIEW").json()
    shown = card(client, headers, review["id"])["card"]
    assert shown["potential_xp"] == {"eligible": True, "ordinal": 4, "xp": 40, "xp_with_hint": 20}
    result = answer(client, headers, review["id"], FULL).json()
    assert (result["xp"]["reason"], result["xp"]["ordinal"], xp_of(result)) == (
        "SCHEDULED_REVIEW",
        4,
        40,
    )
    # Answering the same item again before its next due date (practice with schedule updates)
    # moves the schedule but can't earn again.
    early = start(client, headers, course_id, intent="PRACTICE", update_schedule=True).json()
    assert answer(client, headers, early["id"], FULL).json()["xp"] is None

    # The next legitimate review earns again.
    make_due(db_session, it["id"])
    later = start(client, headers, course_id, intent="SCHEDULED_REVIEW").json()
    assert xp_of(answer(client, headers, later["id"], FULL).json()) == 50


def test_learning_with_the_answer_shown_earns_nothing(client, course):
    headers, course_id, topic_id = course
    item(client, headers, concept(client, headers, topic_id)["id"])
    session = start(client, headers, course_id, intent="LEARN").json()
    assert card(client, headers, session["id"])["card"]["potential_xp"]["eligible"] is False

    result = answer(client, headers, session["id"], FULL).json()
    assert result["xp"] is None
    # But it is study activity.
    assert dashboard(client, headers)["goal"]["done"] == 1


def test_counters_are_independent_per_user_and_item(client, course, auth_headers):
    headers, _, topic_id = course
    c = concept(client, headers, topic_id)
    item(client, headers, c["id"], title="Primo")
    item(client, headers, c["id"], title="Secondo")
    session = studied(client, headers, c["id"]).json()
    first_item = [xp_of(answer(client, headers, session["id"], FULL).json()) for _ in range(3)]
    second_item = [xp_of(answer(client, headers, session["id"], FULL).json()) for _ in range(3)]
    assert first_item == second_item == [10, 20, 30]

    other = auth_headers("other-learner@example.com")
    course2 = client.post("/api/v1/courses", json={"title": "Altro"}, headers=other).json()
    chapter = client.post(
        f"/api/v1/courses/{course2['id']}/chapters", json={"title": "C"}, headers=other
    ).json()
    topic = client.post(
        f"/api/v1/chapters/{chapter['id']}/topics", json={"title": "T"}, headers=other
    ).json()
    c2 = concept(client, other, topic["id"])
    item(client, other, c2["id"])
    s2 = studied(client, other, c2["id"]).json()
    assert xp_of(answer(client, other, s2["id"], FULL).json()) == 10
    assert dashboard(client, other)["xp"]["total"] == 10
    assert dashboard(client, headers)["xp"]["total"] == 120


def test_awards_are_unique_in_the_database(client, course, db_session):
    headers, _, topic_id = course
    c = concept(client, headers, topic_id)
    item(client, headers, c["id"])
    session = studied(client, headers, c["id"]).json()
    result = answer(client, headers, session["id"], FULL).json()
    award = db_session.scalar(select(XpAward))
    assert award.reason is XpReason.INITIAL

    for field in ("answer_id", "occasion_key", "ordinal"):
        duplicate = XpAward(
            user_id=award.user_id,
            course_id=award.course_id,
            learning_item_id=award.learning_item_id,
            answer_id=award.answer_id if field == "answer_id" else _other_answer(db_session),
            session_id=award.session_id,
            reason=award.reason,
            occasion_key=award.occasion_key if field == "occasion_key" else f"x:{field}",
            correct=True,
            ordinal=award.ordinal if field == "ordinal" else 99,
            base_xp=10,
            xp=10,
            policy_version="xp_v1",
        )
        db_session.add(duplicate)
        with pytest.raises(IntegrityError):
            db_session.flush()
        db_session.rollback()
    assert result["xp"]["xp"] == 10


def _other_answer(db_session):
    from app.models.review import Answer

    answers = db_session.scalars(select(Answer)).all()
    return answers[-1].id if len(answers) > 1 else _clone_answer(db_session, answers[0])


def _clone_answer(db_session, original):
    from app.models.review import Answer

    clone = Answer(
        user_id=original.user_id,
        course_id=original.course_id,
        session_id=original.session_id,
        learning_item_id=original.learning_item_id,
        question_formulation_id=original.question_formulation_id,
        intent=original.intent,
        method=original.method,
        text="clone",
    )
    db_session.add(clone)
    db_session.flush()
    return clone.id


def test_duplicate_finalization_is_rolled_back(client, course, db_session, monkeypatch):
    """A retried evaluation that races the first one loses on the unique constraints and is
    rolled back whole; the answer keeps the first result."""
    headers, _, topic_id = course
    c = concept(client, headers, topic_id)
    item(client, headers, c["id"])
    session = studied(client, headers, c["id"]).json()
    app.dependency_overrides[get_ai_provider] = lambda: None
    pending = answer(client, headers, session["id"], FULL).json()

    # Simulate the winner: an award for this answer already exists when this request commits.
    from app.models.review import Answer

    stored = db_session.get(Answer, __import__("uuid").UUID(pending["answer_id"]))
    db_session.add(
        XpAward(
            user_id=stored.user_id,
            course_id=stored.course_id,
            learning_item_id=stored.learning_item_id,
            answer_id=stored.id,
            session_id=stored.session_id,
            reason=XpReason.INITIAL,
            occasion_key="initial:1",
            correct=False,
            base_xp=0,
            xp=0,
            policy_version="xp_v1",
        )
    )
    db_session.commit()
    from app.ai.mock import MockAIProvider

    app.dependency_overrides[get_ai_provider] = lambda: MockAIProvider()
    retried = client.post(f"/api/v1/answers/{pending['answer_id']}/evaluate", headers=headers)
    assert retried.status_code == 200
    db_session.expire_all()
    awards = db_session.scalars(select(XpAward)).all()
    assert len(awards) == 1


def test_time_between_rounds_is_not_needed(client, course, db_session):
    """Three rounds seconds apart produce one encoding, whatever the timing."""
    headers, _, topic_id = course
    c = concept(client, headers, topic_id)
    it = item(client, headers, c["id"])
    session = studied(client, headers, c["id"]).json()
    for _ in range(3):
        answer(client, headers, session["id"], FULL)
    state = memory(db_session, it["id"])
    assert state.review_count == 1
    assert timedelta(hours=3, minutes=59) < state.interval_seconds * timedelta(seconds=1)
