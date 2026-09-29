# Project Status

Verified state of the implementation, from running the code and tracing execution paths, not from
the existence of files. Update it with every change that moves a status.

**Current as of 2026-09-25**, branch `learning-dashboard` (PR into `claude/brave-hypatia-ykotk0`;
nothing merged into `main`).
Scope: backend, iOS client, desktop web client (`/web`).
The audit baseline this session started from (`bc1b56a`) is summarized in §7.

Status words: **COMPLETE** (works and reasonably tested) · **PARTIAL** · **SKELETON** (types or
screens exist, no working behavior) · **MISSING** · **BROKEN**. Acceptance results: **PASS** ·
**PARTIAL** · **FAIL** · **NOT IMPLEMENTED** · **BLOCKED**.

## 1. Validation

| Check | Result | Notes |
|---|---|---|
| `ruff check`, `ruff format --check`, `mypy` (strict) | PASS | 2026-09-24 |
| `pytest` on SQLite / on PostgreSQL 16 | PASS | 614 / 614 on SQLite and 614 / 614 on PostgreSQL (2026-09-25), including consolidation, XP, hints, dashboard, storage and the extended isolation matrix |
| Docker Compose (Postgres + backend) | PASS | full HTTP loop; the sandbox build needs its CA (environment, not project) |
| iOS build + unit tests (CI, macOS) | PASS | 89 tests, `ios.yml` runs #8–#10 on this branch |
| iOS simulator acceptance run (CI) | PASS | 21/21 in `ios.yml` runs #18 (9092c8c) and #22 (671e280, after the #8 merge); earlier runs exposed test assumptions (system Save Password sheet, rows below the fold, element type, keyboard focus), fixed without relaxing assertions |
| Web: `tsc`, ESLint, Vitest, production build, secrets check | PASS (locally) | 26 tests, incl. dashboard, library filters, goal editing, sign-out clearing, consolidation with hint and XP |
| Web: browser E2E (Playwright + real backend + mock AI) | PASS (locally, 2026-09-25) | consolidation loop with hint and XP, two-account isolation and cache switching, curriculum loop; screenshots at 1440/1024/768/390 px without horizontal scroll (`docs/screenshots/`) |
| Real AI provider | BLOCKED BY SECRET | free-first router (Groq, Mistral, Gemini, Cloudflare, OpenRouter, NVIDIA, Cohere; Alibaba Model Studio, Tencent TokenHub, SiliconFlow for Qwen/GLM/Kimi/DeepSeek, with billing guards) implemented and mock-tested. `real-ai.yml` + `scripts/ai_benchmark.py` are ready. No provider secret exists yet, no model ID is live-verified, no evaluator is approved, and the workflow must be on `main` to be dispatchable (docs/FREE_AI_ROUTING.md) |
| FREE_ONLY cost guarantee | PASS (mocks) | paid/unknown models placed first in a route with valid keys are never called; all free failing → `free_capacity_exhausted` (`tests/test_free_ai_routing.py`, mutation-checked) |
| Object storage (S3) | IMPLEMENTED, NOT PROVISIONED | `STORAGE_BACKEND=s3` tested with botocore's Stubber; no bucket exists yet (docs/DEPLOYMENT.md §5) |
| Hosted deployment | NOT PROVISIONED | no host, managed database or bucket yet; everything else is in GitHub (docs/DEPLOYMENT.md) |

## 2. Phase matrix

| # | Phase | Status | Evidence / what works | Incomplete / missing |
|---|---|---|---|---|
| 1 | Repository & docs | COMPLETE | `/docs` synchronized, incl. WEB_ARCHITECTURE.md | — |
| 2 | Clients: iOS + web | PARTIAL | iOS: real API layer, every MVP screen, 89 CI tests. Web: every MVP screen, 17 tests, browser E2E | iOS acceptance run fails at step 3; no human has used either client |
| 3 | Backend foundation & auth | COMPLETE | `test_auth.py`, `test_errors.py`, `test_config.py` | refresh/logout (not MVP) |
| 4 | Database & Course hierarchy | COMPLETE | backend CRUD/outline/isolation; iOS and web create chapters and browse the tree | topic/concept manual creation in the clients |
| 5 | Document ingestion & sources | COMPLETE | backend pipeline; upload, status, delete and "View source" in both clients; interrupted processing becomes a retryable failure | OCR |
| 6 | AI curriculum generation | PARTIAL | backend with mock AI; proposal review/edit/apply in both clients (web adds move and merge) | real model never run |
| 7 | Concept activation | COMPLETE | backend; both clients activate and follow item generation | — |
| 8 | Learning Items & questions | PARTIAL | backend with mock AI; items, questions, sources, in-training toggle in both clients; AI question generation per item (`questions/generate`, backend only) | real model never run; no client UI for generating questions yet |
| 9 | Runtime AI provider abstraction | COMPLETE | generic transport with strict/non-strict JSON Schema, Cloudflare adapter, capability catalog, per-operation routing, FREE_ONLY/FREE_FIRST/ANY_CONFIGURED, data policy, normalized failures | real-model behavior unverified; route order not yet benchmark-driven |
| 10 | AI answer evaluation | PARTIAL | backend + resolver + overrides; feedback, self-grade and dispute in both clients | real grading quality unknown |
| 11 | Chessable-style scheduling | COMPLETE | pure policy + history | per-Course policy selection |
| 12 | Review sessions | COMPLETE | LEARN / SCHEDULED_REVIEW / PRACTICE in backend and both clients | EXAM refused (Phase 15) |
| 13 | Mastery & analytics | PARTIAL | progress, review load, weak concepts in backend and both clients | coverage model, analytics |
| 14 | Voice answering | SKELETON | unwired iOS service; backend accepts `method: VOICE` | wiring |
| 15 | Exam Mode | MISSING | — | everything |
| 16 | Offline / resilience | PARTIAL | answers committed before evaluation; answer drafts kept locally in both clients; interrupted background jobs recovered (`app/services/recovery.py`) | caching, job queue |
| 17 | Course import/export | MISSING | — | everything |
| — | Consolidation, XP, hints, activity | COMPLETE (backend + web) | "I have studied this concept" → 3 rounds per item, one encoding; XP ledger with DB-level uniqueness; server-side hints; streak/goal/activity by user timezone | iOS screens for these; AI-written hints |
| — | Study dashboard and identity | COMPLETE (web) | next step, course library cards, streak, XP, goal, planner, activity; concept 5 logo (concept 3 alternative) | human review of the design; iOS app icon |

## 3. MVP acceptance flow (spec §102)

**BACKEND** = the API, by automated tests (`tests/test_acceptance.py` is the whole chain).
**IOS** = the app, by unit tests in CI (mocked API). **WEB** = the browser client, by unit tests
(mocked API). **END-TO-END** = a real client driving the real backend (mock AI): the web
Playwright run and the iOS simulator run (21 steps).

| # | Capability | BACKEND | IOS | WEB | END-TO-END |
|---|---|---|---|---|---|
| 1 | Create Course | PASS | PASS | PASS | PASS (web) |
| 2 | Create Chapters | PASS | PASS | PASS | PASS (web) |
| 3 | Topics (from applied proposals) | PASS | PASS | PASS | PASS (web) |
| 4 | Import material (PDF, Markdown, …) | PASS | PASS | PASS | PASS (web, Markdown) |
| 5 | Extract source text | PASS | — | — | PASS (web) |
| 6 | Source chunks / "View source" | PASS | PASS | PASS | PASS (web) |
| 7 | Generate curriculum proposal | PASS (mock AI) | PASS | PASS | PASS (web, mock AI) |
| 8 | Accept/edit curriculum | PASS | PASS | PASS | PASS (web) |
| 9 | Concepts exist | PASS | PASS | PASS | PASS (web) |
| 10 | Activate selected Concepts | PASS | PASS | PASS | PASS (web) |
| 11 | Learning Items generated | PASS (mock AI) | PASS | PASS | PASS (web, mock AI) |
| 12 | Questions generated | PASS (mock AI) | PASS | PASS | PASS (web, mock AI) |
| 13 | Start a session | PASS | PASS | PASS | PASS (web) |
| 14 | Answer by text | PASS | PASS | PASS | PASS (web) |
| 15 | AI evaluates answer | PASS (mock AI) | PASS | PASS | PASS (web, mock AI) |
| 16 | Feedback shown (reference, sources, next review) | PASS | PASS | PASS | PASS (web) |
| 17 | Scheduling processes review | PASS | — | — | PASS (web: next review shown) |
| 18 | Next review stored | PASS | — | — | PASS (web) |
| 19 | Review history stored | PASS | — | — | PASS (web: API read by the signed-in browser session after reload; no history screen exists) |
| 20 | Concept mastery updates | PASS | PASS | PASS | PASS (web) |
| 21 | Topic progress | PASS | PASS | PASS | PASS (web) |
| 22 | Chapter progress | PASS | PASS | PASS | PASS (web) |
| 23 | Course progress | PASS | PASS | PASS | PASS (web) |
| 24 | Second Course isolated | PASS (65-case matrix) | — | — | — |
| 25 | AI provider changed by configuration | PASS (mock, fake server) | — | — | BLOCKED BY SECRET (real vendor) |
| 26 | Independent of the coding agent/model | PASS | — | — | — |

Also verified end to end in the web run: dispute of the AI grade ("Disagree"), answer from the
keyboard, reload keeps the session. In web unit tests: an answer draft survives a failed submit
and a page reload.

## 4. Architectural requirements (engineering brief §5)

| Requirement | Status | Where |
|---|---|---|
| 5.1 Session intent (LEARN, SCHEDULED_REVIEW, PRACTICE, EXAM) explicit in domain code | Done (EXAM refused until Phase 15) | `SessionIntent`, `app/services/review/pool.py` |
| 5.2 Initial learning / encoding before scheduled review | Done | LEARN sessions; `process_learning` |
| 5.3 Concept vs Learning Item; one memory state per item shared by its formulations | Done, tested | `app/models/learning.py` |
| 5.4 Content roles; promote/remove from training without deleting | Done | `role` + `in_training` |
| 5.5 AI evaluation separate from review outcome (ReviewOutcomeResolver) | Done; spec §37 amended (A3) | `app/services/evaluation/resolver.py` |
| 5.6 Evaluation override / audit trail | Done | `Answer` override fields, immutable `Evaluation`, superseding `Review` rows |
| 5.7 SchedulingPolicy owns all transitions; centralized ladder; future policies possible | Done | `app/services/scheduling/` |
| 5.8 Course isolation of every new operation | Done, tested | isolation matrix + per-module tests |
| 5.9 Source grounding of items and evaluation; insufficient context → structured result | Done | item sources; evaluation gets the item's passages; `context_sufficient` → self-grade |
| 5.10 Curriculum vs memory progress; review-load horizons | Done (computed on read) | `app/services/mastery/` |

## 5. Known gaps and risks

1. **No real AI model has run.** Grading quality and the resolver thresholds are unvalidated.
   The tooling is ready (`real-ai.yml`, `ai_benchmark.py`). It needs provider secrets and the
   workflow on `main`. The model IDs in the catalog come from the owner's research and are
   unverified (this sandbox can't reach vendor APIs). The default route order is provisional.
2. **The iOS simulator acceptance run has passed twice in a row** (21/21, runs #18 and #22).
   An earlier keyboard-focus failure is fixed; keep watching for flakiness. UX note from it: on the course dashboard the chapter list is
   below the Today/Curriculum/Memory sections, off the first screen on an iPhone.
3. **No human has used either client.** Automated runs prove the flow works, not that it's
   pleasant; layout, copy and accessibility beyond what the tests touch are unreviewed.
4. **The web client is English-only** (iOS has Italian). Strings are in components, not yet a
   catalog.
5. In-process background jobs: a restart fails the running job. The recovery sweep marks it
   failed with a retry path within 15 minutes (plus up to a minute); nothing is duplicated.
6. External knowledge mode, coverage model, question variations, follow-ups: not built.
7. The iOS app doesn't show XP, hints, consolidation or the dashboard yet. Its LEARN sessions
   still work but earn no XP (the answer is shown before recall), and its accounts start in UTC
   until the timezone is set.
8. No hosted deployment: see docs/DEPLOYMENT.md §5 for what must be provisioned.

## 6. Next recommended unit

No new features until these gates close (docs/RELEASE_SCOPE.md):

1. **Real free-AI validation.** Merge the bootstrap PR that adds `real-ai.yml` to `main`, then
   dispatch it on this branch:
   - `verify` per provider whose secret exists (Groq, Gemini, OpenRouter, Cloudflare, NVIDIA,
     TokenHub, SiliconFlow; Mistral, DashScope and Cohere have no secret yet);
   - fix catalog IDs from the results;
   - `evaluation` with `repeat: 2` per evaluator candidate;
   - approve the models that pass, and set `AI_ROUTE_ANSWER_EVALUATION`.
2. **iOS simulator acceptance run** green: done (2 consecutive runs).
3. **Draft PR CI green** (backend, web including Playwright, iOS).
4. **Human smoke test** (docs/HUMAN_SMOKE_TEST.md) once per client.

## 7. Audit baseline (session start, `bc1b56a`)

At the start of the session: backend 280 tests passing on both databases; phases 1, 3, 5, 9
COMPLETE; 2, 4, 6, 7 PARTIAL; 8, 12, 13, 14 SKELETON; 10, 11, 15, 16, 17 MISSING. Acceptance items
1-10 and 24-26 passed on the backend; 11-23 were NOT IMPLEMENTED. Key findings: no Learning
Item table; no session intent; the documented evaluation schema let the AI choose the review
outcome (contradicting spec §42); no scheduler. First missing dependency: Learning Items.

Work since, in dependency order: SchedulingPolicy (pure) → Learning Items + questions →
evaluation + ReviewOutcomeResolver + review sessions + history + overrides → progress and review
load → end-to-end acceptance test → documentation and spec amendments.
