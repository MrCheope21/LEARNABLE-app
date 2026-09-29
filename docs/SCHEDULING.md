# Scheduling

Status: **Implemented and tested** (Phase 11 core, 2026-09-24):
`backend/app/services/scheduling/` (policy, ladder, persistence), the ReviewOutcomeResolver in
`backend/app/services/evaluation/resolver.py`, and the session logic that drives them in
`backend/app/services/review/`. Tests: `test_scheduling_policy.py` (pure),
`test_outcome_resolver.py` (pure), `test_review.py` (through the API).

## 1. The non-negotiable rule: AI does not schedule

```
User Answer → AI Evaluation (evidence) → ReviewOutcomeResolver → Review Outcome
            → [user override] → SchedulingPolicy → next state / level / due date
```

The AI returns semantic evidence only (classification, scores, points, misconceptions,
context sufficiency, feedback). It has **no outcome field**: a deterministic, versioned
`ReviewOutcomeResolver` turns evidence into AGAIN / HARD / GOOD, and the `SchedulingPolicy` alone
computes every state, level, interval and date (spec §42, §104). This keeps the memory engine
deterministic, testable without any AI, auditable, and independent of which model is configured.

## 2. SchedulingPolicy abstraction

`app/services/scheduling/policy.py`. Pure: no database, no AI, no clock (callers pass `now` and a
`MemorySnapshot`, and persist the result through `store.py`).

```
process_learning(snapshot, outcome, now) -> Transition   # first retrieval of a NEW item (LEARN)
process_review(snapshot, outcome, now)   -> Transition   # an encoded item
pause(snapshot, now)  -> snapshot
resume(snapshot, now) -> snapshot
mastery_estimate(snapshot) -> float                       # progress displays only
```

The spec's `initialize` is `process_learning` with a success outcome, and `calculateNextReview`
happens inside each transition. A `Transition` carries `before`, `after`, `outcome`,
`reviewed_at` and `lateness`. Every Learning Item stores the policy name and version it started
with (`get_policy(name, version)`), so a later default never re-interprets existing items.

## 3. ChessableStyleSchedulingPolicy (MVP default, `chessable` v1)

The ladder lives only in `app/services/scheduling/config.py`. Changing a value means a new
policy version, because every history row records the version that produced it.

| Level | Interval |
|---|---|
| 1 | 4 hours |
| 2 | 1 day |
| 3 | 3 days |
| 4 | 1 week |
| 5 | 2 weeks |
| 6 | 1 month (30 days) |
| 7 | 3 months (91 days) |
| 8 | 6 months (182 days) |

Transitions (owner decisions, 2026-09-24):

| | Encoding (NEW item, LEARN) | Review (encoded item) |
|---|---|---|
| **AGAIN** | stays NEW, asked again in the session (≤3 times) | **back to level 1**; a lapse (+1 `lapse_count`, state RELEARNING) if the item was REVIEW/MASTERED; failing at level 1 or while relearning is not a new lapse |
| **HARD** | level 1 | **+1 level, like GOOD**, and the item is **marked hard** (+1 `hard_count`) |
| **GOOD** | level 1 | +1 level |
| **EASY** | level 2 | +2 levels |

- State after a success: LEARNING at level 1, REVIEW above it, MASTERED at the top level
  (reviews continue every 6 months).
- The next due date counts from the moment of the review, early or late (spec §47): lateness is
  recorded on the history row, and progress is never erased because a review was late.
- `marked_hard` stays set while the most recent answer was HARD; GOOD or EASY clear it, AGAIN
  doesn't (the item was reset and is still a problem). `hard_count` is kept forever. *(Decided
  by the coding agent; the owner can change it.)*
- Pause/resume (item level, spec §56): resume adds the paused time to the due date, so a paused
  item comes back with the interval it had left instead of overdue. Pausing a Concept or section
  only excludes items from pools; their schedule keeps running.
- `mastery_estimate`: level / 8, discounted per lapse (×1/(1 + 0.25·lapses)). An estimate for
  progress screens; never used to schedule.

## 3a. Marked-hard questions and the "hard only" review

The owner wants to review only the questions marked hard. This is a **PRACTICE** session with
selection mode `MARKED_HARD`. Like all practice, it **does not change the schedule by default**
(task §5.1), and the user can opt in with `update_schedule: true`.

*This replaces an earlier note in this file saying hard-only answers go through the
SchedulingPolicy. Practice that silently moved the schedule would let extra drilling of hard
items make them look better remembered than they are.*

## 3b. ReviewOutcomeResolver (`outcome_resolver_v1`)

`app/services/evaluation/resolver.py`, pure. The thresholds are in one `ResolverThresholds`
dataclass.

| Evidence | Outcome |
|---|---|
| `context_sufficient: false` | none → the user grades it |
| `UNCERTAIN`, or `confidence` < 0.5 | none |
| `WRONG` / `MISCONCEPTION` | AGAIN (none if `correctness` > 0.6: self-contradicting) |
| `PARTIALLY_CORRECT` with `correctness` ≥ 0.6 and `completeness` ≥ 0.5 | HARD |
| other `PARTIALLY_CORRECT` | AGAIN |
| `CORRECT` with `completeness` < 0.7 or `conceptual_understanding` < 0.6 | HARD |
| `CORRECT` otherwise | GOOD (none if `correctness` < 0.6: self-contradicting) |

- **EASY never comes from an evaluation.** An answer shows correctness, not how easy recall
  was; the user can grade EASY themselves.
- "None" never guesses: the answer waits for the user's grade (or a retried evaluation).
- **Overrides** (the user's grade) never erase the AI evaluation or the resolved outcome. If the
  answer already moved the schedule, the transition is replayed from the stored previous state
  as a new history row that supersedes the old one, and only while it is the item's latest
  review. Later history is never rewritten.

## 4. Session intents (what may move the schedule)

| Intent | Items | Schedule |
|---|---|---|
| LEARN | NEW (not encoded) | encoding success initializes it |
| SCHEDULED_REVIEW | encoded and due | every final outcome goes through the policy |
| PRACTICE | encoded, chosen by mode | unchanged unless `update_schedule` |
| CONSOLIDATION | NEW items of one Concept, each three times in a row | only the item's last round (§4a) |
| EXAM | — | not available yet; must never move the schedule by accident |

## 4a. Consolidation: three rounds, one encoding

"I have studied this concept" starts a `CONSOLIDATION` session (`POST /concepts/{id}/consolidation`,
`app/services/review/consolidation.py`): a batch of up to 5 NEW items, each in three consecutive
slots, so its question is asked three times in immediate succession with feedback after each
round.

- Rounds 1 and 2 are stored (Answer + Evaluation, `consolidation_round`) but **don't** go through
  the policy: they happen seconds apart and prove nothing about long-term retention.
- The item's **last** round goes through `process_learning` with that round's final outcome,
  exactly like a first retrieval in LEARN: GOOD/HARD → level 1 (4 hours), EASY → level 2,
  AGAIN → stays NEW (it comes back in a later batch). One Review history row, intent
  `CONSOLIDATION`; overrides replay it like any other.
- So consolidation can never produce an interval longer than a single successful encoding, and a
  wrong final round is handled by the normal learning policy.
- The session is stored and resumable; asking again resumes the unfinished batch. XP for rounds
  is separate and never read here (docs/XP_AND_ACTIVITY.md).

## 5. Future scheduling policies

The protocol supports additional implementations without changing callers (spec §45):
`FSRSPolicy`, `AdaptiveSchedulingPolicy`, `CustomSchedulingPolicy`. A new policy gets a name and
version in the registry (`_POLICIES`), and its own interpretation of `mastery_estimate`. Per-Course
selection (`CourseSettings.scheduling_policy`) is not wired yet.

## 6. Independent item-level scheduling

Two Learning Items under the same Concept can be at completely different levels (spec §26).
The policy only ever sees one item's snapshot, so an AGAIN on one item can't touch a sibling
(tested).

## 7. Question Formulations share one state

All formulations of a Learning Item share its single ReviewState (spec §27). Sessions rotate
wording: the least asked formulation first, then the least recently asked.

## 8. Auditability

Every transition writes an append-only `reviews` row: previous/next state, level and due date,
outcome, intent, `reviewed_at`, lateness, policy name + version, the full previous snapshot, and
`supersedes_review_id` / `superseded` for overrides (spec §86). The answer keeps the resolved
outcome, the resolver version, the override and the final outcome; evaluations are kept as
written.

## 9. Testing (spec §77)

Pure tests cover: correct / incorrect / hard / easy answers, encoding, lapses, relearning,
mastered, overdue reviews, early reviews, pause/resume, independent items, and the resolver's
fixtures A–I (spec §78). API tests cover: practice not modifying state, scheduled review
modifying it, overrides with replay, formulation sharing, and pool eligibility.
