"""The review loop over the API (docs/PROJECT_SPEC.md §21, §26-27, §42, §46-51, §83-86).

answer → AI evaluation → ReviewOutcomeResolver → [override] → SchedulingPolicy → history.

The default MockAIProvider grades by overlap with the essential points ("consegna di denaro",
"obbligo di restituzione"): both → CORRECT → GOOD; one → PARTIALLY_CORRECT → HARD; none → AGAIN.
"""

import uuid
from datetime import timedelta

import pytest
from sqlalchemy import select

from app.ai.factory import get_ai_provider
from app.ai.mock import MockAIProvider
from app.ai.schemas import EvaluationOutput
from app.core.errors import AIInvalidOutputError, AIUnavailableError
from app.db.types import utc_now
from app.main import app
from app.models.enums import EvaluationClassification
from app.models.learning import ReviewState
from app.models.review import Answer, Evaluation, Review

FULL = "Il mutuo prevede la consegna di denaro e l'obbligo di restituzione."
PARTIAL = "Si ha la consegna di denaro."
WRONG = "Non lo so proprio."


@pytest.fixture
def course(client, auth_headers):
    headers = auth_headers("reviewer@example.com")
    course = client.post(
        "/api/v1/courses", json={"title": "Diritto", "language": "it"}, headers=headers
    ).json()
    chapter = client.post(
        f"/api/v1/courses/{course['id']}/chapters", json={"title": "Contratti"}, headers=headers
    ).json()
    topic = client.post(
        f"/api/v1/chapters/{chapter['id']}/topics", json={"title": "Prestiti"}, headers=headers
    ).json()
    return headers, course["id"], chapter["id"], topic["id"]


def concept(client, headers, topic_id, title="Mutuo", active=True):
    created = client.post(
        f"/api/v1/topics/{topic_id}/concepts", json={"title": title}, headers=headers
    ).json()
    if active:
        client.post(f"/api/v1/concepts/{created['id']}/activate", headers=headers)
    return created


def item(client, headers, concept_id, title="Mutuo: definizione", **extra):
    body = {
        "title": title,
        "expected_knowledge": "Consegna di denaro con obbligo di restituzione.",
        "essential_points": ["consegna di denaro", "obbligo di restituzione"],
        "questions": [
            {"question_type": "DEFINITION", "text": f"Che cos'e: {title}?"},
            {"question_type": "EXPLANATION", "text": f"Spiega: {title}"},
        ],
        **extra,
    }
    return client.post(
        f"/api/v1/concepts/{concept_id}/learning-items", json=body, headers=headers
    ).json()


def start(client, headers, course_id, intent="LEARN", **body):
    return client.post(
        f"/api/v1/courses/{course_id}/review-sessions",
        json={"intent": intent, **body},
        headers=headers,
    )


def card(client, headers, session_id):
    return client.get(f"/api/v1/review-sessions/{session_id}/next", headers=headers).json()


def answer(client, headers, session_id, text, question_id=None):
    current = card(client, headers, session_id)
    qid = question_id or current["card"]["question"]["id"]
    return client.post(
        f"/api/v1/review-sessions/{session_id}/answers",
        json={"question_formulation_id": qid, "text": text},
        headers=headers,
    )


def learn(client, headers, course_id, text=FULL):
    """Encodes every NEW item with the same answer."""
    session = start(client, headers, course_id).json()
    while not card(client, headers, session["id"])["done"]:
        answer(client, headers, session["id"], text)
    return session


def memory(db_session, item_id):
    db_session.expire_all()
    return db_session.scalar(
        select(ReviewState).where(ReviewState.learning_item_id == uuid.UUID(item_id))
    )


def make_due(db_session, item_id, ago=timedelta(minutes=1)):
    state = memory(db_session, item_id)
    state.due_at = utc_now() - ago
    db_session.commit()


def use_provider(provider):
    app.dependency_overrides[get_ai_provider] = lambda: provider
    return provider


def scripted(classification, score, **extra):
    return EvaluationOutput(
        classification=classification,
        correctness=score,
        completeness=score,
        conceptual_understanding=score,
        precision=score,
        confidence=0.9,
        context_sufficient=True,
        **extra,
    )


# --- LEARN: initial encoding (task §5.2) ---


def test_learn_introduces_then_encodes_and_initializes_the_schedule(client, course, db_session):
    headers, course_id, _, topic_id = course
    c = concept(client, headers, topic_id)
    it = item(client, headers, c["id"])

    session = start(client, headers, course_id).json()
    assert (session["intent"], session["selection_mode"]) == ("LEARN", "NEW")
    assert session["affects_schedule"] is True
    shown = card(client, headers, session["id"])["card"]
    assert shown["introduction"]["expected_knowledge"].startswith("Consegna di denaro")
    assert shown["learning_item_id"] == it["id"]

    result = answer(client, headers, session["id"], FULL).json()

    assert result["evaluation"]["classification"] == "CORRECT"
    assert (result["resolved_outcome"], result["final_outcome"]) == ("GOOD", "GOOD")
    assert result["needs_self_grade"] is False
    assert result["schedule"]["previous_state"] == "NEW"
    assert (result["schedule"]["next_state"], result["schedule"]["next_level"]) == ("LEARNING", 1)
    state = memory(db_session, it["id"])
    assert state.level == 1
    assert state.due_at - utc_now() > timedelta(hours=3, minutes=59)
    assert result["reference"]["essential_points"] == it["essential_points"]
    assert card(client, headers, session["id"])["done"] is True

    [review] = client.get(f"/api/v1/learning-items/{it['id']}/reviews", headers=headers).json()
    assert (review["intent"], review["outcome"], review["previous_state"]) == (
        "LEARN",
        "GOOD",
        "NEW",
    )
    assert (review["scheduling_policy"], review["scheduling_policy_version"]) == ("chessable", "2")


def test_failed_encoding_keeps_the_item_new_and_asks_it_again(client, course, db_session):
    headers, course_id, _, topic_id = course
    it = item(client, headers, concept(client, headers, topic_id)["id"])
    session = start(client, headers, course_id).json()

    first = answer(client, headers, session["id"], WRONG).json()
    assert first["final_outcome"] == "AGAIN"
    assert first["schedule"]["next_state"] == "NEW"
    assert memory(db_session, it["id"]).state.value == "NEW"

    again = card(client, headers, session["id"])
    assert again["card"]["learning_item_id"] == it["id"]  # re-queued in the same session
    second = answer(client, headers, session["id"], FULL).json()
    assert second["schedule"]["next_state"] == "LEARNING"


def test_learn_gives_up_after_three_attempts(client, course):
    headers, course_id, _, topic_id = course
    item(client, headers, concept(client, headers, topic_id)["id"])
    session = start(client, headers, course_id).json()
    for _ in range(3):
        assert answer(client, headers, session["id"], WRONG).status_code == 201
    assert card(client, headers, session["id"])["done"] is True


def test_encoded_items_leave_the_learn_pool(client, course):
    headers, course_id, _, topic_id = course
    item(client, headers, concept(client, headers, topic_id)["id"])
    learn(client, headers, course_id)
    response = start(client, headers, course_id)
    assert response.status_code == 409
    assert response.json()["details"]["reason"] == "empty_pool"


# --- Pool eligibility (spec §21, §50, §56) ---


def test_only_active_trained_unpaused_items_are_eligible(client, course):
    headers, course_id, chapter_id, topic_id = course
    active = item(client, headers, concept(client, headers, topic_id, "Attivo")["id"], "A")
    item(client, headers, concept(client, headers, topic_id, "Inattivo", active=False)["id"], "B")
    untrained = item(client, headers, concept(client, headers, topic_id, "C")["id"], "C")
    client.post(f"/api/v1/learning-items/{untrained['id']}/untrain", headers=headers)
    paused = item(client, headers, concept(client, headers, topic_id, "D")["id"], "D")
    client.post(f"/api/v1/learning-items/{paused['id']}/pause", headers=headers)

    session = start(client, headers, course_id).json()
    assert session["total"] == 1
    assert card(client, headers, session["id"])["card"]["learning_item_id"] == active["id"]

    client.post(f"/api/v1/chapters/{chapter_id}/pause", headers=headers)
    assert start(client, headers, course_id).status_code == 409


def test_pool_follows_course_order_and_scope(client, course):
    headers, course_id, _, topic_id = course
    c = concept(client, headers, topic_id)
    second = item(client, headers, c["id"], "Secondo")
    first = item(client, headers, c["id"], "Primo")
    client.patch(f"/api/v1/learning-items/{first['id']}", json={"order": 0}, headers=headers)
    client.patch(f"/api/v1/learning-items/{second['id']}", json={"order": 1}, headers=headers)

    session = start(client, headers, course_id, concept_ids=[c["id"]], limit=1).json()
    assert session["total"] == 1
    assert card(client, headers, session["id"])["card"]["learning_item_id"] == first["id"]


# --- SCHEDULED_REVIEW ---


def test_scheduled_review_takes_only_due_items_and_advances_them(client, course, db_session):
    headers, course_id, _, topic_id = course
    it = item(client, headers, concept(client, headers, topic_id)["id"])
    learn(client, headers, course_id)

    not_due = start(client, headers, course_id, "SCHEDULED_REVIEW")
    assert not_due.status_code == 409

    make_due(db_session, it["id"], ago=timedelta(days=2))
    session = start(client, headers, course_id, "SCHEDULED_REVIEW").json()
    assert (session["selection_mode"], session["affects_schedule"]) == ("DUE", True)
    assert card(client, headers, session["id"])["card"]["introduction"] is None
    result = answer(client, headers, session["id"], FULL).json()

    assert (result["schedule"]["previous_level"], result["schedule"]["next_level"]) == (1, 2)
    assert result["schedule"]["lateness_seconds"] >= 2 * 86400 - 5  # overdue, recorded
    assert memory(db_session, it["id"]).level == 2


def test_hard_keeps_the_level_and_marks_the_item(client, course, db_session):
    headers, course_id, _, topic_id = course
    it = item(client, headers, concept(client, headers, topic_id)["id"])
    learn(client, headers, course_id)
    make_due(db_session, it["id"])
    session = start(client, headers, course_id, "SCHEDULED_REVIEW").json()

    result = answer(client, headers, session["id"], PARTIAL).json()

    assert result["evaluation"]["classification"] == "PARTIALLY_CORRECT"
    assert result["final_outcome"] == "HARD"
    # Scheduling v2: HARD repeats the same interval instead of advancing.
    assert result["schedule"]["next_level"] == 1
    state = memory(db_session, it["id"])
    assert (state.marked_hard, state.hard_count) == (True, 1)


def test_again_drops_one_item_and_never_its_siblings(client, course, db_session):
    headers, course_id, _, topic_id = course
    c = concept(client, headers, topic_id)
    definition = item(client, headers, c["id"], "Definizione")
    scenario = item(client, headers, c["id"], "Caso pratico")
    learn(client, headers, course_id)
    for it in (definition, scenario):
        state = memory(db_session, it["id"])
        state.level = 5
        state.state = state.state.REVIEW
        db_session.commit()
    make_due(db_session, scenario["id"])

    session = start(client, headers, course_id, "SCHEDULED_REVIEW").json()
    assert session["total"] == 1
    result = answer(client, headers, session["id"], WRONG).json()

    # Scheduling v2: a first slip drops two levels (a second slip in a row would go to 1).
    assert (result["final_outcome"], result["schedule"]["next_level"]) == ("AGAIN", 3)
    assert memory(db_session, scenario["id"]).lapse_count == 1
    assert memory(db_session, definition["id"]).level == 5


def test_formulations_rotate_and_share_one_memory_state(client, course, db_session):
    headers, course_id, _, topic_id = course
    it = item(client, headers, concept(client, headers, topic_id)["id"])
    learn(client, headers, course_id)
    asked_first = client.get(f"/api/v1/learning-items/{it['id']}", headers=headers).json()
    used = {q["id"] for q in asked_first["questions"] if q["times_asked"]}

    make_due(db_session, it["id"])
    session = start(client, headers, course_id, "SCHEDULED_REVIEW").json()
    second_question = card(client, headers, session["id"])["card"]["question"]["id"]
    assert second_question not in used  # the other wording
    answer(client, headers, session["id"], FULL)

    assert memory(db_session, it["id"]).level == 2  # same state carried on


# --- PRACTICE never touches the schedule by default (task §5.1) ---


def test_practice_is_evaluated_and_kept_but_leaves_memory_state_alone(client, course, db_session):
    headers, course_id, _, topic_id = course
    it = item(client, headers, concept(client, headers, topic_id)["id"])
    learn(client, headers, course_id)
    before = memory(db_session, it["id"])
    snapshot = (before.level, before.due_at, before.review_count, before.marked_hard)
    reviews_before = len(db_session.scalars(select(Review)).all())

    session = start(client, headers, course_id, "PRACTICE").json()
    assert (session["selection_mode"], session["affects_schedule"]) == ("COURSE_ORDER", False)
    result = answer(client, headers, session["id"], WRONG).json()

    assert result["final_outcome"] == "AGAIN"
    assert result["schedule"] is None
    after = memory(db_session, it["id"])
    assert (after.level, after.due_at, after.review_count, after.marked_hard) == snapshot
    assert len(db_session.scalars(select(Review)).all()) == reviews_before
    assert db_session.scalar(select(Answer).where(Answer.id == uuid.UUID(result["answer_id"])))


def test_practice_can_opt_in_to_update_the_schedule(client, course, db_session):
    headers, course_id, _, topic_id = course
    it = item(client, headers, concept(client, headers, topic_id)["id"])
    learn(client, headers, course_id)
    session = start(client, headers, course_id, "PRACTICE", update_schedule=True).json()
    assert session["affects_schedule"] is True
    result = answer(client, headers, session["id"], FULL).json()
    assert result["schedule"]["next_level"] == 2
    assert memory(db_session, it["id"]).level == 2


def test_practice_selection_modes(client, course, db_session):
    headers, course_id, _, topic_id = course
    c = concept(client, headers, topic_id)
    hard = item(client, headers, c["id"], "Difficile")
    weak = item(client, headers, c["id"], "Debole")
    fine = item(client, headers, c["id"], "Solido")
    learn(client, headers, course_id)
    memory(db_session, hard["id"]).marked_hard = True
    db_session.commit()
    memory(db_session, weak["id"]).lapse_count = 2
    db_session.commit()

    def pool(mode, **extra):
        session = start(client, headers, course_id, "PRACTICE", selection_mode=mode, **extra)
        if session.status_code != 201:
            return session.status_code
        ids = []
        sid = session.json()["id"]
        while not (current := card(client, headers, sid))["done"]:
            ids.append(current["card"]["learning_item_id"])
            client.post(f"/api/v1/review-sessions/{sid}/skip", headers=headers)
        return ids

    assert pool("MARKED_HARD") == [hard["id"]]
    assert pool("WEAK")[0] == weak["id"]
    assert pool("SELECTED", learning_item_ids=[fine["id"]]) == [fine["id"]]
    assert sorted(pool("RANDOM")) == sorted([hard["id"], weak["id"], fine["id"]])
    assert pool("RECENTLY_FAILED") == 409

    failing = start(client, headers, course_id, "PRACTICE", selection_mode="SELECTED",
                    learning_item_ids=[fine["id"]]).json()  # fmt: skip
    answer(client, headers, failing["id"], WRONG)
    assert pool("RECENTLY_FAILED") == [fine["id"]]


@pytest.mark.parametrize(
    ("body", "reason"),
    [
        ({"intent": "EXAM"}, "exam_not_available"),
        ({"intent": "SCHEDULED_REVIEW", "update_schedule": True}, "update_schedule_not_allowed"),
        ({"intent": "LEARN", "selection_mode": "RANDOM"}, "mode_not_allowed"),
        ({"intent": "PRACTICE", "selection_mode": "SELECTED"}, "no_items_selected"),
    ],
)
def test_invalid_session_requests(client, course, body, reason):
    headers, course_id, _, topic_id = course
    item(client, headers, concept(client, headers, topic_id)["id"])
    learn(client, headers, course_id)
    response = client.post(
        f"/api/v1/courses/{course_id}/review-sessions", json=body, headers=headers
    )
    assert response.status_code == 422
    assert response.json()["details"]["reason"] == reason


# --- When evaluation can't decide (resilience, spec §36, §79) ---


def test_failed_evaluation_keeps_the_answer_and_can_be_retried(client, course, db_session):
    headers, course_id, _, topic_id = course
    it = item(client, headers, concept(client, headers, topic_id)["id"])
    session = start(client, headers, course_id).json()
    use_provider(MockAIProvider(error=AIUnavailableError("The AI provider is down.")))

    result = answer(client, headers, session["id"], FULL)

    assert result.status_code == 201
    body = result.json()
    assert body["evaluation"]["status"] == "FAILED"
    assert body["needs_self_grade"] is True
    assert body["schedule"] is None
    assert memory(db_session, it["id"]).state.value == "NEW"
    pending = card(client, headers, session["id"])["card"]
    assert pending["pending_answer_id"] == body["answer_id"]
    blocked = answer(client, headers, session["id"], FULL)
    assert blocked.status_code == 409
    assert blocked.json()["details"]["reason"] == "answer_pending"

    use_provider(MockAIProvider())
    retried = client.post(f"/api/v1/answers/{body['answer_id']}/evaluate", headers=headers).json()
    assert retried["final_outcome"] == "GOOD"
    assert retried["schedule"]["next_state"] == "LEARNING"
    detail = client.get(f"/api/v1/answers/{body['answer_id']}", headers=headers).json()
    assert [e["status"] for e in detail["evaluations"]] == ["FAILED", "COMPLETED"]


def test_malformed_ai_output_fails_safely(client, course):
    headers, course_id, _, topic_id = course
    item(client, headers, concept(client, headers, topic_id)["id"])
    session = start(client, headers, course_id).json()
    use_provider(MockAIProvider(error=AIInvalidOutputError("The AI answer wasn't valid.")))
    result = answer(client, headers, session["id"], FULL).json()
    assert (result["evaluation"]["status"], result["needs_self_grade"]) == ("FAILED", True)


def test_without_ai_the_user_grades_themselves(client, course, db_session):
    headers, course_id, _, topic_id = course
    it = item(client, headers, concept(client, headers, topic_id)["id"])
    session = start(client, headers, course_id).json()
    app.dependency_overrides[get_ai_provider] = lambda: None

    result = answer(client, headers, session["id"], FULL).json()
    assert result["evaluation"]["status"] == "NOT_CONFIGURED"
    graded = client.post(
        f"/api/v1/answers/{result['answer_id']}/override", json={"outcome": "EASY"}, headers=headers
    ).json()

    assert (graded["final_outcome"], graded["override_outcome"]) == ("EASY", "EASY")
    assert graded["resolved_outcome"] is None
    assert memory(db_session, it["id"]).level == 2  # EASY encoding → level 2
    assert card(client, headers, session["id"])["done"] is True


def test_insufficient_context_is_not_guessed_and_is_kept(client, course):
    headers, course_id, _, topic_id = course
    item(client, headers, concept(client, headers, topic_id)["id"])
    session = start(client, headers, course_id).json()
    use_provider(
        MockAIProvider(
            evaluation=EvaluationOutput(
                classification=EvaluationClassification.UNCERTAIN,
                correctness=0.5,
                completeness=0.5,
                conceptual_understanding=0.5,
                precision=0.5,
                confidence=0.4,
                context_sufficient=False,
                feedback="The material doesn't cover this.",
            )
        )
    )
    result = answer(client, headers, session["id"], FULL).json()
    assert result["evaluation"]["context_sufficient"] is False
    assert (result["resolved_outcome"], result["needs_self_grade"]) == (None, True)
    retry = client.post(f"/api/v1/answers/{result['answer_id']}/evaluate", headers=headers)
    assert retry.json()["details"]["reason"] == "evaluation_inconclusive"


# --- Overrides and audit (task §5.6) ---


def test_override_replays_the_transition_and_keeps_the_ai_evaluation(client, course, db_session):
    headers, course_id, _, topic_id = course
    it = item(client, headers, concept(client, headers, topic_id)["id"])
    learn(client, headers, course_id)
    make_due(db_session, it["id"])
    session = start(client, headers, course_id, "SCHEDULED_REVIEW").json()
    graded = answer(client, headers, session["id"], FULL).json()
    assert (graded["final_outcome"], graded["schedule"]["next_level"]) == ("GOOD", 2)

    overridden = client.post(
        f"/api/v1/answers/{graded['answer_id']}/override",
        json={"outcome": "AGAIN", "note": "I guessed"},
        headers=headers,
    ).json()

    assert overridden["resolved_outcome"] == "GOOD"  # what the rules said is kept
    assert (overridden["override_outcome"], overridden["final_outcome"]) == ("AGAIN", "AGAIN")
    assert overridden["evaluation"] == graded["evaluation"]  # never overwritten
    assert overridden["schedule"]["previous_level"] == 1  # replayed from the stored state
    assert overridden["schedule"]["next_level"] == 1
    state = memory(db_session, it["id"])
    assert (state.level, state.state.value) == (1, "LEARNING")

    history = client.get(f"/api/v1/learning-items/{it['id']}/reviews", headers=headers).json()
    original, replay = history[-2], history[-1]
    assert (original["outcome"], original["superseded"]) == ("GOOD", True)
    assert (replay["outcome"], replay["supersedes_review_id"]) == ("AGAIN", original["id"])
    assert db_session.scalar(
        select(Evaluation).where(Evaluation.answer_id == uuid.UUID(graded["answer_id"]))
    )


def test_override_is_refused_once_the_item_was_reviewed_again(client, course, db_session):
    headers, course_id, _, topic_id = course
    it = item(client, headers, concept(client, headers, topic_id)["id"])
    session = start(client, headers, course_id).json()
    first = answer(client, headers, session["id"], FULL).json()
    make_due(db_session, it["id"])
    review = start(client, headers, course_id, "SCHEDULED_REVIEW").json()
    answer(client, headers, review["id"], FULL)

    response = client.post(
        f"/api/v1/answers/{first['answer_id']}/override", json={"outcome": "AGAIN"}, headers=headers
    )
    assert response.status_code == 409
    assert response.json()["details"]["reason"] == "later_reviews_exist"


def test_override_in_practice_changes_nothing_in_the_schedule(client, course, db_session):
    headers, course_id, _, topic_id = course
    it = item(client, headers, concept(client, headers, topic_id)["id"])
    learn(client, headers, course_id)
    level = memory(db_session, it["id"]).level
    session = start(client, headers, course_id, "PRACTICE").json()
    result = answer(client, headers, session["id"], WRONG).json()
    overridden = client.post(
        f"/api/v1/answers/{result['answer_id']}/override", json={"outcome": "GOOD"}, headers=headers
    ).json()
    assert (overridden["final_outcome"], overridden["schedule"]) == ("GOOD", None)
    assert memory(db_session, it["id"]).level == level


# --- Source grounding (spec §19, task §5.9) ---


def test_evaluation_is_grounded_in_the_items_own_sources(client, course, ai_provider):
    headers, course_id, _, topic_id = course
    it = item(client, headers, concept(client, headers, topic_id)["id"])
    session = start(client, headers, course_id).json()
    answer(client, headers, session["id"], FULL)

    [request] = ai_provider.evaluation_requests
    assert request.expected_knowledge == it["expected_knowledge"]
    assert request.essential_points == it["essential_points"]
    assert request.passages == []  # a hand-written item: no source passages to send
    assert request.language == "it"


# --- Session control ---


def test_skip_leaves_memory_untouched(client, course, db_session):
    headers, course_id, _, topic_id = course
    it = item(client, headers, concept(client, headers, topic_id)["id"])
    session = start(client, headers, course_id).json()
    skipped = client.post(f"/api/v1/review-sessions/{session['id']}/skip", headers=headers).json()
    assert skipped["done"] is True
    assert memory(db_session, it["id"]).review_count == 0


def test_answering_a_question_that_isnt_current_is_refused(client, course):
    headers, course_id, _, topic_id = course
    c = concept(client, headers, topic_id)
    item(client, headers, c["id"], "Uno")
    other = item(client, headers, c["id"], "Due")
    session = start(client, headers, course_id).json()
    response = answer(client, headers, session["id"], FULL, other["questions"][0]["id"])
    assert response.status_code == 409
    assert response.json()["details"]["reason"] == "not_current_question"


def test_finished_session_refuses_answers(client, course):
    headers, course_id, _, topic_id = course
    it = item(client, headers, concept(client, headers, topic_id)["id"])
    session = learn(client, headers, course_id)
    response = client.post(
        f"/api/v1/review-sessions/{session['id']}/answers",
        json={"question_formulation_id": it["questions"][0]["id"], "text": FULL},
        headers=headers,
    )
    assert response.status_code == 409


def test_item_deleted_mid_session_is_skipped(client, course):
    headers, course_id, _, topic_id = course
    c = concept(client, headers, topic_id)
    first = item(client, headers, c["id"], "Uno")
    second = item(client, headers, c["id"], "Due")
    session = start(client, headers, course_id).json()
    client.delete(f"/api/v1/learning-items/{first['id']}", headers=headers)
    assert card(client, headers, session["id"])["card"]["learning_item_id"] == second["id"]


# --- Course isolation (task §5.8) ---


def test_sessions_never_reach_another_course(client, course, auth_headers):
    headers, course_id, chapter_id, topic_id = course
    it = item(client, headers, concept(client, headers, topic_id)["id"])
    stranger = auth_headers("stranger@example.com")
    theirs = client.post("/api/v1/courses", json={"title": "X"}, headers=stranger).json()

    assert start(client, stranger, theirs["id"], chapter_id=chapter_id).status_code == 404
    stolen = start(client, stranger, theirs["id"], "LEARN", selection_mode="SELECTED",
                   learning_item_ids=[it["id"]])  # fmt: skip
    assert stolen.status_code == 409  # empty pool: the foreign item simply isn't there
    session = start(client, headers, course_id).json()
    for method, url in [
        ("GET", f"/api/v1/review-sessions/{session['id']}"),
        ("GET", f"/api/v1/review-sessions/{session['id']}/next"),
        ("GET", f"/api/v1/learning-items/{it['id']}/reviews"),
    ]:
        assert client.request(method, url, headers=stranger).status_code == 404
