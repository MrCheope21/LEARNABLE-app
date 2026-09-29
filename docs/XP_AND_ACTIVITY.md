# Consolidation, XP, hints and study activity

Status: **Implemented and tested** (2026-09-25). Backend: `app/services/review/consolidation.py`,
`app/services/rewards/` (policy, service, hints), `app/services/dashboard/service.py`, tables in
`app/models/rewards.py`. Tests: `tests/test_xp_consolidation.py`, `tests/test_dashboard.py`,
the isolation matrix, and the web/Playwright flows.

XP and activity sit **beside** the learning loop and never feed back into it: the scheduler,
the ReviewOutcomeResolver and mastery estimates never read them.

## 1. "I have studied this concept": three consolidation rounds

Opening or activating a Concept isn't studying it. Activation prepares Learning Items; the user
reads them; then **"I have studied this concept"** (`POST /concepts/{id}/consolidation`)
starts consolidation:

- The Concept's NEW, trainable, askable items are taken in course order, **5 per batch**
  (15 answers). The plan (`GET /concepts/{id}/consolidation`) shows the batch size, the rounds
  and the number of answers before starting, and how many items wait for later batches.
- A batch is a stored `CONSOLIDATION` review session whose pool holds each item **three times in
  a row**. Each round is a separate answer, evaluated, with corrective feedback; the card shows
  "Round n of 3". The same question (or an existing formulation of the same item) is asked
  again; no new AI generation is needed.
- Three **completed** rounds, not "until three correct": Correct → Wrong → Correct is 10 → 0 →
  20 XP.
- **Resume, never reset.** Leaving keeps the batch open; asking again (or "Resume" on the
  dashboard) continues at the same slot. A finished batch is never replayed; a new batch only
  takes items still NEW.
- **Scheduler:** three answers seconds apart are one act of encoding, not three reviews. Only an
  item's **last round** goes through the SchedulingPolicy (`process_learning` with that round's
  outcome), so a correct item starts at level 1 (4 hours) like any first success, and a failed
  last round leaves it NEW for a later batch. Every round is kept as an Answer with its
  Evaluation (`consolidation_round` 1-3); only the last one writes a Review history row
  (SCHEDULING.md §4a).
- Completing a batch isn't consolidating the whole Concept: the end screen says how many items
  still wait and links to the next batch.

The older `LEARN` session (introduction with the reference answer, then recall) still exists for
the iOS app. It shows the full answer before recall, so its attempts earn no XP (§3).

## 2. The XP rule

Per user **and** Learning Item, a counter of XP-counted correct answers (`item_success_counters`,
shared by all of the item's question formulations):

```
base XP of the nth correct answer = min(10 × n, 150)        (10, 20, 30 … 150 from the 15th)
awarded XP                        = base, halved if a hint was revealed first
                                                             (5, 10, 15 … 75)
```

- **Correct** means: the AI classified the answer `CORRECT` *and* the deterministic resolver
  turned it into a success (GOOD or HARD). The client never sends an amount or a correctness
  claim.
- **Partial credit:** `PARTIALLY_CORRECT` earns 0 XP and neither advances nor resets the counter,
  even when the resolver schedules it as HARD.
- **Incorrect** answers earn 0 and leave the counter unchanged.
- **Self-grades don't create XP.** When the AI can't decide (not configured, failed,
  inconclusive) and the user grades the answer, the attempt counts as study activity with 0 XP.
  A later "Disagree with the grade" override changes the schedule (replayed, as before) but
  never the XP already decided, in either direction.
- XP never changes scheduling, grading or mastery.

## 3. Which attempts can earn XP

| Attempt | Eligible | Unique occasion |
|---|---|---|
| Consolidation round | the item's first **three** consolidation rounds, ever | `initial:1..3` |
| Scheduled review | only when the item was **due** when answered | `review:<due date>` |
| LEARN (answer shown first) | no | — |
| Practice (any mode, even with `update_schedule`) | no | — |
| Exam | not built | — |

A later legitimate scheduled review (the next due date) earns again.

**Anti-farming**, enforced in the database, not only in code: one award row per answer
(`xp_awards.answer_id` unique), per occasion (`learning_item_id, occasion_key` unique), and per
success ordinal (`learning_item_id, ordinal` unique). So refreshing, replaying a finished
session, restarting consolidation, switching formulations, duplicate requests or answering again
before the next due date can't earn twice.

## 4. Hints

"Show hint" (`POST /review-sessions/{id}/hint`) before answering:

- The UI states **"Using a hint halves the XP for this answer."** before anything is revealed.
- The hint is the opening word(s) of the item's first key point (about a third of it, 1-6
  words), or of its reference answer: a retrieval cue from the stored, source-grounded
  reference, never the whole answer, never a new AI call (so it can't contradict the reference
  and costs nothing). It's cached on the question formulation. When the reference is too short
  to cut a cue from, there's honestly no hint (`hint_unavailable`), and nothing is recorded.
- The reveal is stored (`hint_reveals`, one per session slot) **before** it's returned. The
  answer to that slot is marked `hint_used` by the server; reloading, leaving or a
  client-side change can't remove it. Asking again returns the same hint: several hints still
  halve once. A failed hint request records nothing.
- The penalty applies to that attempt only; an assisted correct answer still advances the
  counter.
- Hints aren't offered in LEARN (the answer is already on screen).

## 5. Study activity, streak, daily goal and timezone

A **completed attempt** is an answer that received its first final outcome (`finalized_at`,
set once): right or wrong, AI- or self-graded. Opening a page or starting a session doesn't
count. Each completed attempt adds +1 attempt (and its XP) to `daily_activity` for the user's
**local day** in the same transaction as the outcome, so retries and overrides never count
twice.

`daily_activity` is the single source for:

- **Streak:** consecutive local days with ≥1 completed attempt, ending today, or ending
  yesterday when today has none yet (yesterday's streak can still be kept today).
- **Daily goal:** completed attempts today vs `users.daily_goal` (default 20, 1-500, editable).
  The count may exceed the goal; the gauge caps at 100%.
- **XP today** and lifetime XP.
- **Activity calendar:** 12 weeks on the dashboard, 52 on "See more".

**Timezone policy.** Each user has an IANA zone (`users.timezone`). The web client sends the
device's zone at registration; otherwise it's UTC (existing accounts, the iOS app for now). The
dashboard offers to switch when the device's zone differs; the account menu changes it. Days
are computed with `zoneinfo`, so daylight-saving changes are handled (tested for Europe/Rome in
March and October). A new timezone applies from then on: days already recorded keep the date
they were recorded under (no history is rewritten).

## 6. Dashboard aggregation

`GET /dashboard` returns everything in one read, against one `as_of` timestamp, with a fixed
number of queries (tested: 1 course and 6 courses cost the same):

- **Course cards**
  - `concepts_studied / concepts_total`: a Concept counts as studied when it has trained items
    and none is still NEW. Activating it doesn't count.
  - `items_introduced / items_trained`: trained items no longer NEW.
  - `due_now`: exactly what a SCHEDULED_REVIEW session would ask (same eligibility query).
  - `learn`: `resume` (unfinished batch), `study` (the next concept with items waiting),
    `activate` (next concept to set up), `setup` (no concepts yet: add material) or `none`.
  - None of these is mastery or XP.
- **Next step** (one recommendation, fixed priority):
  1. resume an unfinished consolidation batch;
  2. review due items (the course with most due);
  3. continue learning (most recently studied course with something to learn);
  4. add material to an empty course;
  5. create a first course, or "all caught up".
- **Planner:** cumulative counts of reviewable items due by now, +1 h, +4 h, +1 day, +3 days and
  +7 days (rolling windows from `as_of`; overdue items are in every row). No time estimate is
  shown: nothing measured would support one yet.
- **Streak, goal, XP, activity:** §5. They're account-wide even when the course list is
  filtered.

## 7. History and migration policy

Migration `52ab3371f372` adds the tables and columns; it awards nothing retroactively and
backfills no activity. Answers from before it have no `finalized_at` and no award, so totals
start at zero on upgrade instead of inventing history the old data can't support (hint use,
due-ness at answer time and the counter order weren't recorded).
