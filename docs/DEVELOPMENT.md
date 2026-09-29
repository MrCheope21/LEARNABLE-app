# Development

## Current status

**The backend vertical slice works end to end** (`tests/test_acceptance.py`): Course → PDF →
chunks → curriculum → Concepts → activation → Learning Items + questions → LEARN session → text
answer → AI evaluation → ReviewOutcomeResolver → SchedulingPolicy → history → progress at every
level, with a second Course isolated. Verified status per phase and per acceptance item:
**[PROJECT_STATUS.md](PROJECT_STATUS.md)**.

- **Backend**: 410 tests pass on SQLite and real PostgreSQL; `ruff` and strict `mypy` are clean;
  migrations from empty verified; Docker stack verified.
- **No real AI model has been called yet.** Everything AI is tested against `MockAIProvider`,
  scripted transports and a fake OpenAI-compatible server. Prompt quality is unknown until
  someone runs a real `AI_PROVIDER` (BLOCKED BY CREDENTIAL).
- **iOS is behind the backend**: sign-in, Courses, material import and "View source" work
  against the API (48 unit tests in CI); there are no screens yet for chapters, curriculum,
  Learning Items, review sessions or progress (the Review tab still uses an honest "not
  available" stub). Nobody has launched the UI.

See "Known environment gaps" and "Local vs. cloud sessions" below.

| Phase | Description | Status |
|---|---|---|
| 1 | Repository inspection and documentation | **Done** |
| 2 | iOS foundation and navigation | **Done (builds + unit-tested in CI; UI never run)** |
| 3 | Backend foundation and authentication | **Done (tested)** |
| 4 | Database and Course hierarchy | **Done (tested on SQLite + Postgres)** |
| 5 | Document ingestion and source repository | **Done**: backend tested; iOS screens built + unit-tested in CI (UI never run) |
| 6 | AI curriculum generation | **Done (tested, mock AI only)**: per-Chapter material, proposals merged with existing Topics/Concepts, incremental re-analysis, grounding, apply, outline, Concept "View source". No iOS screens yet |
| 7 | Concept activation | **Done (tested)**: full study-state lifecycle + section pause |
| 8 | Learning Items and question generation | **Backend done (tested, mock AI)**: generation on activation, roles + in_training, formulations, item sources, pause. No iOS |
| 9 | Runtime AI provider abstraction | **Done (tested, no real model called yet)**: OpenAI-compatible transport, validation + retry, fallback providers, per-operation models, mock |
| 10 | AI answer evaluation | **Backend done (tested, mock AI)**: evidence-only evaluation, ReviewOutcomeResolver, retries, self-grade, audited overrides. No iOS |
| 11 | Chessable-style scheduling | **Done (tested)**: pure policy, centralized ladder, history |
| 12 | Review sessions | **Backend done (tested)**: LEARN / SCHEDULED_REVIEW / PRACTICE intents, 8 selection modes. No iOS |
| 13 | Concept mastery and analytics | **Partial**: progress (curriculum vs memory), mastery estimate, review load, misconceptions; no analytics/coverage model; no iOS |
| 14 | Voice answering | Not started |
| 15 | Exam Mode | Not started |
| 16 | Offline/resilience improvements | Not started |
| 17 | Course import/export foundations | Not started |

Phase Completion Rule (spec §100): at the end of every phase — build, run tests, fix compiler
errors, fix failing tests, review architecture, update documentation, leave the repository in a
working state.

## ⚠️ Known environment gaps

- **Git / Python**: installed (Python via `winget install Python.Python.3.12`). Resolved.
- **PostgreSQL**: not installed system-wide, and not needed — `pytest --postgres` starts a
  throwaway PostgreSQL 16 via the `pgserver` pip package (no Docker, no admin rights).
- **Docker**: not installed on the Windows machine. The stack **was tested in a cloud session**
  on 2026-09-24: it builds, migrates Postgres, and the full flow works (upload a PDF → READY →
  generate a curriculum with `AI_PROVIDER=mock` → apply → "View source" → activate). That run
  found and fixed a bug: every upload returned 500 because the non-root container user couldn't
  create the storage directory. Uploaded files now live in the `documents_data` volume. In a
  cloud sandbox the image build needs the sandbox's CA certificate to reach PyPI (a sandbox
  limitation, not a project bug; the project Dockerfile doesn't need it elsewhere).
- **Xcode / iOS toolchain**: this dev environment is Windows, where Xcode can't run. The iOS code
  is compiled and unit-tested **only in CI** (`.github/workflows/ios.yml`, macOS runner) — push
  and check the Actions tab. What CI can't do: nobody has launched the app or looked at a screen,
  so layout, navigation feel and accessibility are unverified until someone runs it on a
  Mac/iPhone.

## Local vs. cloud sessions

Agents work either locally (VS Code or a terminal on the Windows dev machine) or in a cloud
session (claude.ai/code or the Claude mobile app, on Anthropic's managed Linux sandbox). Any
agent switching between the two, or picking up work started in the other, follows these rules.
They are environment constraints, not suggestions: ignoring them wastes a session finding out
the hard way.

### 1. Cloud sessions cannot build or test iOS code

The sandbox is Linux. Xcode, XcodeGen and Swift compilation need macOS, which the Windows
machine doesn't have either, so this is not a regression. In a cloud session:

- Edit Swift/SwiftUI source, `project.yml`, etc. freely.
- Don't run `xcodebuild`, `xcodegen`, a simulator or an iOS test target. They fail because
  there is no macOS, not because of a bug in the code, so don't spend time debugging them.
- Push to a branch and let the `ios` workflow decide whether the code compiles and passes. It
  is the only place iOS code is ever compiled or tested. **A push to a feature branch alone
  does not run it**: both workflows trigger only on pushes to `main`, on pull requests, or
  manually ("Run workflow" on the Actions tab, choosing the branch). Open a PR or start the run
  manually, and don't call iOS work verified until that run is green.

Backend work (ruff, mypy, pytest on SQLite and Postgres) runs in a cloud session the same way it
runs in the `backend` workflow.

### 2. Cloud sessions start from a fresh GitHub clone

A cloud session clones the repo from GitHub. It can't see anything uncommitted on the local
machine.

- Before switching sessions to continue the same work, commit and push everything in progress
  to its feature branch.
- To move a running local session to the cloud, prefer `--remote` (keeps context) over starting
  a cloud session cold. To bring a cloud session back to the local terminal, prefer
  `--teleport`.
- When picking up a session you didn't start, read the latest commits on its branch and the
  relevant entries in the decision log below before continuing, as any agent joining mid-project
  would.

### 3. The cloud sandbox needs its own setup

Each cloud session is a fresh VM, not a copy of the local environment. These were verified in a
cloud session on 2026-09-24:

- **Call Python 3.12 by name.** The sandbox's default `python3` is 3.11, but ruff and mypy
  target 3.12. `python3.12` is installed.
- **pip and `pgserver` work through the sandbox's network proxy.** Installing
  `requirements-dev.txt` from PyPI and `pytest --postgres` both worked without extra network
  rules. The `pgserver` wheel ships its own PostgreSQL binaries.
- **GitHub**: the Claude GitHub App can clone the private `MrCheope21/LEARNABLE` repo.
- **Backend dependencies were not pre-installed.** Configure the environment's setup script
  (claude.ai: the cloud environment menu in the session's title bar → Edit → Setup script; it
  isn't stored in this repo) so each session doesn't redo this by hand. From the repository
  root:

  ```bash
  cd backend
  python3.12 -m venv .venv
  .venv/bin/python -m pip install -r requirements-dev.lock
  ```

Then, from `backend/` (the tests need no `.env`):

```bash
.venv/bin/python -m ruff check . && .venv/bin/python -m ruff format --check .
.venv/bin/python -m mypy
.venv/bin/python -m pytest              # SQLite
.venv/bin/python -m pytest --postgres   # real PostgreSQL via pgserver
```

## Decisions made autonomously (spec §5: document non-critical ambiguity resolutions)

### Database

- **Alembic owns the schema.** The app never calls `create_all`; run `alembic upgrade head`
  before starting the server. `tests/test_migrations.py` fails if models and migrations drift
  apart, and checks that downgrade to empty works. New migrations are auto-formatted by ruff (a
  post-write hook in `alembic.ini`).
- **SQLite for zero-setup local dev, Postgres as the real target.** `DATABASE_URL` defaults to
  `backend/dev.db`. Several bugs SQLite hides (unenforced VARCHAR lengths, no timezones, lax
  types) were found by running against Postgres, so **run `pytest --postgres` before trusting any
  schema change**. SQLite connections enable `PRAGMA foreign_keys=ON` so cascades and FK
  violations behave like Postgres.
- **Any standard Postgres URL works.** `postgresql://` and `postgres://` are rewritten to
  `postgresql+psycopg://` (the psycopg v3 driver we install); SQLAlchemy would otherwise look for
  psycopg2, which isn't a dependency.
- **Timestamps are timezone-aware UTC everywhere** (`app/db/types.py` `UTCDateTime`):
  `timestamptz` on Postgres, re-tagged as UTC when read back from SQLite, naive datetimes
  rejected on write. The API always serializes them as `2026-09-23T08:42:33.720Z` (see API.md).
- **Deletes cascade in the database** (`ON DELETE CASCADE` + `passive_deletes`), not by the ORM
  loading every descendant first — a Course will eventually own thousands of rows.
- **`study_state` is VARCHAR + CHECK, not a native Postgres ENUM**, so adding a state later is an
  ordinary migration (native enums need `ALTER TYPE`, which can't run inside a transaction).
- **Deterministic constraint names** (naming convention on `Base.metadata`), so migrations can
  reference constraints identically on SQLite and Postgres.
- **The engine is created lazily** on first use, so importing the app never opens or creates a
  database as a side effect.
- **Sync (not async) SQLAlchemy**: FastAPI runs sync route handlers in a threadpool, so this is
  correct without an async driver. Revisit only if request volume demands it.

### Auth

- **`AUTH_SECRET` is required, ≥32 characters, and known placeholders are rejected.** The server
  refuses to start otherwise (checked in the app's startup lifespan). There is no insecure
  default. Secrets are `SecretStr`, so they never appear in reprs or logs.
- **Argon2id password hashing (`argon2-cffi`) and PyJWT**, replacing `passlib` + `bcrypt` +
  `python-jose` (all effectively unmaintained; the old setup needed a `bcrypt<4.1` pin and
  silently truncated passwords at 72 bytes). Hashes are upgraded on login if parameters change.
- **JWT algorithm is pinned to HS256 in code**, not configurable, to rule out algorithm-confusion
  attacks. Tokens carry `sub`, `type: "access"`, `iat`, `exp`; all are required on decode.
- **Password policy: 12–128 characters** (OWASP ASVS 2.1.1) at registration only — login
  doesn't re-check the policy, so tightening it later can't lock out existing accounts.
  Passwords are never whitespace-trimmed.
- **Emails are normalized** (trimmed, lowercased) — `B@example.com` and `b@example.com` are one
  account.
- **Login is timing-equalized**: an unknown email still runs a full hash verification, so
  response time doesn't reveal which emails are registered. Unknown-email and wrong-password
  responses are byte-identical.
- **`HTTPBearer`, not `OAuth2PasswordBearer`**: login takes JSON, so there's no OAuth2 password
  form for Swagger to post to; the "Authorize" dialog asks for the token directly.
- **Registration still returns 409 for a taken email** — a deliberate UX-over-enumeration
  trade-off; revisit if abuse appears (e.g. switch to "check your inbox" email verification).
- **Auth scope**: `register`, `login`, `me`. `refresh` and `logout` are not yet implemented; add
  them alongside session/token-invalidation design work.

### API

- **One error envelope for everything** (`app/api/errors.py`): services raise domain errors
  (`app/core/errors.py`), mapped centrally — route handlers contain no try/except. Validation
  errors return only `loc`/`msg`/`type`, never the rejected input (which can be a password).
  Unhandled errors return a generic 500 and are logged by method + path only, never the body.
- **Request bodies reject unknown fields** (`extra="forbid"`), and string fields are trimmed.
  Length limits mirror column sizes, so an over-long value is a 422, not a Postgres error.
- **PATCH: omitted = unchanged, explicit `null` = 422.** Every patchable column is NOT NULL, so
  accepting `null` previously surfaced as a 500.
- **404, never 403, for cross-Course access.** `get_owned_course`/`_chapter`/`_topic`/`_concept`
  raise the same `NotFoundError` whether a resource doesn't exist or belongs to another user, so
  a response never confirms someone else's id exists (spec §10). Every hierarchy lookup ends in
  `get_owned_course`, so isolation is enforced in one place. `tests/test_isolation.py` tries
  every Course-scoped endpoint as an intruder — **add new endpoints to its `ENDPOINTS` list.**
- **Concept study-state machine** (one table, `CONCEPT_TRANSITIONS` in
  `app/services/courses/service.py`; matrix in API.md):
  - `mark-studied` never demotes a Concept already in training.
  - `activate` works from `COMPLETED`, so finished material can be revisited. It does not work
    from `PAUSED`, which must `resume` instead.
  - `deactivate` (spec §60) returns an active or paused Concept to `STUDIED`, keeping its history.
  - Invalid transitions return 409 with the current state, rather than silently no-opping.
  - Open question for the review engine: whether `COMPLETED` Concepts keep being reviewed. For
    now `is_reviewable` is false for them.
- **Section pause is a flag, not a cascade**: pausing a Topic/Chapter/Course sets `paused` on it
  instead of rewriting every Concept inside. Resuming only clears the flag, so a Concept paused
  on its own stays paused (spec §56: "unpause restores their previous state").
  `Concept.is_reviewable` combines the two.
- **`CourseSettings`** is created with defaults alongside every `Course` but not yet exposed
  through the API — nothing in the acceptance path (spec §102) needs it yet.

### Documents (Phase 5)

- **The pipeline runs as a FastAPI background task** (in-process). Upload returns `202` once the
  file is stored, and processing continues after the response. Verified on a real server: a
  40-page PDF is `READY` about 1.3s after the upload started. If the server restarts
  mid-processing, the recovery sweep (below) marks the document `FAILED` with "Processing was
  interrupted. Delete this document and upload it again." Move to a real job queue when
  documents get large or the backend runs several replicas.
- **Types are detected from content** (magic bytes, and ZIP contents for DOCX vs PPTX). The
  client's filename and Content-Type are ignored, except to tell `.txt` from `.md`. The stored
  filename is display metadata only; the file lives at `courses/{course}/documents/{document}`.
- **Chunks never span a page or a section**, so every passage has one page number and one
  heading to show under "View source". PDF sections come from the PDF's bookmarks. Target size is
  1200 characters: paragraphs are grouped up to that, and longer ones are split at sentence ends.
- **Cleaning keeps meaning**:
  - NUL and control characters are removed (Postgres rejects NUL).
  - Line-break hyphenation is rejoined only when the next line starts lowercase.
  - Ligatures are expanded explicitly. Deliberately not NFKC, which would turn "x²" into "x2".
- **Encrypted PDFs**: an owner password only (typical for textbooks) is read normally via
  `pypdf[crypto]`. An open password fails with a clear reason.
- **Images and scans are stored but `FAILED`.** OCR needs a vision model. The AI provider
  (Phase 9) has no vision operation yet, so this is still open. Failed documents are always
  kept; nothing the user uploads disappears.
- **Limits**:
  - `MAX_UPLOAD_MB` (default 50), checked from `Content-Length` before the body is read, and
    again in the handler.
  - DOCX/PPTX over 500 MB uncompressed, or with more than 20,000 archive entries, are refused
    (zip bombs).
  - PDFs are capped at 3,000 pages.
- **Deletion**: deleting a document or a Course removes the stored files as well as the rows
  (spec §70).
- **Storage** is local disk behind a `DocumentStorage` protocol. An S3-compatible backend
  (`STORAGE_ENDPOINT`/`STORAGE_BUCKET`) is not implemented yet.
- **Unique-constraint names now include every column** (`uq_documents_course_id_sha256`).
  Existing single-column constraint names are unchanged.

### AI provider (Phase 9)

- **Two layers**: `LLMAIProvider` (prompts, schema validation, retry) over a `ChatTransport`
  (HTTP). Swapping vendor is configuration only; swapping protocol would be a new transport.
- **Vendor names are labels, not integrations.** `qwen`/`deepseek`/`kimi`/`glm` all use the
  OpenAI-compatible transport, with no hard-coded URLs (vendor URLs change, and hard-coding them
  would be exactly the provider assumption spec §33 forbids). The name is recorded as
  `ai_provider`.
- **`AI_PROVIDER` empty means AI off, not mock.** Defaulting to the mock would quietly produce
  fake curricula in a deployment someone forgot to configure. Off returns 503
  `ai_not_configured`; `mock` must be chosen explicitly.
- **Misconfiguration stops startup** (unknown provider; missing `AI_BASE_URL`/`AI_MODEL`).
- **One constrained retry on invalid output, none on transport errors.** The retry adds what was
  wrong (locations only, no content); the rejected answer isn't resent (cost). An answer cut off
  at `AI_MAX_TOKENS` fails at once, since a retry would be cut off too.
- **Defaults raised**: `AI_MAX_TOKENS` 2048 → 8192 (a curriculum for ~15k tokens of material
  didn't fit in 2048) and `AI_TIMEOUT` 30 → 60 s.
- **`AI_JSON_MODE`** (default on) and **`AI_MAX_CONTEXT_CHARS`** (default 60,000 ≈ 15k tokens,
  so prompt + material + answer fit a 32k context) are configurable because providers differ.
- **Per-operation models** (spec §34) implemented as a fallback: `AI_MODEL_<GROUP>` or
  `AI_MODEL`. Curriculum generation is in the `generation` group.
- **`model_version`** is the model id the provider reports serving (often a dated snapshot),
  falling back to the requested model.
- **Prompt and model versions are columns on each AI-produced row**, not separate
  PromptVersion/ModelVersion tables: the prompt text lives in versioned files that are never
  edited once used, so the version string identifies it exactly.
- **Logging**: one content-free `ai_call` line per call. Found while testing: `LOG_LEVEL` was
  defined but never applied, so no `app.*` INFO line had ever been printed. It is now applied at
  startup (`app/core/logging.py`) and validated.

### Curriculum generation (Phase 6)

- **Proposal, then apply** (spec §20): generation stores a `CurriculumProposal`; the Course is
  untouched until the user applies the tree they reviewed. Every edit the spec lists (accept,
  reject, rename, merge, split, reorder, move, delete) is expressed by editing that tree, so
  there is one apply endpoint instead of one per edit.
- **Applied Concepts start NOT_STUDIED.** Nothing is activated (spec §21).
- **Grounding is enforced by code, not trusted to the prompt** (spec §19): every proposed
  Concept must cite a passage that was actually sent. Invalid citations are removed, uncited
  Concepts dropped and counted, and a proposal with nothing left is `INSUFFICIENT_CONTEXT`.
- **The model cites short refs (S1, S2…), not UUIDs**: cheaper, and nothing to garble. The
  service maps them back.
- **Passages are sent in document order until `AI_MAX_CONTEXT_CHARS`**, with
  `passages_used`/`passages_total` recorded so the UI can say when a proposal covers only the
  beginning. Generating per document (`document_ids`) covers large material. Map-reduce over a
  whole large Course is not built.
- **Background task, like document processing, but the AI call runs with no DB session open**,
  so a slow model can't hold a connection and transaction for a minute.
- **One generation per Course at a time** (409). A proposal still `GENERATING` after 15 minutes
  was interrupted (a restart kills in-process tasks); the recovery sweep marks it `FAILED`
  instead of blocking the Course forever, and a new request sweeps its Course first.
- **Apply appends after existing Chapters** and never merges into them. Merging into an
  existing Chapter can be added later with an explicit `existing_chapter_id`.
- **Foreign or deleted chunk ids in apply are silently left out**, identically, so the response
  reveals nothing about other Courses. The test checks the database directly, since the read
  endpoint's own Course filter would hide a bad link.
- **Concept gained an `order` column** (like Chapter/Topic). Applied curricula must keep the
  material's order, and creation timestamps within one transaction aren't a safe tiebreaker.
- **`GET /courses/{id}/outline`** was missing entirely: there was no way to read a Course's
  Chapters/Topics/Concepts back. Added, loaded in three queries.
- **Not proposed yet**: duplicates, prerequisites, relationships and suggested Learning Items
  (spec §20 says "may"). The prompt asks only for the hierarchy.
- **Chapter by chapter (owner's direction, 2026-09-24).** The user creates the Course and its
  Chapters and files material under each (`documents.chapter_id`). A Chapter proposal asks the AI
  only for Topics → Concepts of that Chapter, from that Chapter's material, so each call stays
  small. The Course-wide proposal remains for users who don't define Chapters, and only reads
  material not filed under a Chapter, so the two can't propose the same material twice.
- **Incremental analysis.** `documents.analyzed_at` is set when a proposal that sent the whole
  document is applied; a generation without `document_ids` sends only unanalyzed documents. The
  AI is shown the Chapter's existing Topics/Concepts (refs T1/C1, capped at 500 Concepts) and
  may place new Concepts into an existing Topic or link passages to an existing Concept. Those
  references are kept only if they were in the list shown, and apply re-checks that they belong
  to the proposal's Chapter (404 otherwise).
- **Deleted material never deletes Concepts.** A Concept left with no source passage gets
  `needs_source_review`; the user keeps, edits or deletes it. Revised material that re-links it
  clears the flag. There is no "replace document" endpoint: delete + upload + generate does it,
  and each step is visible to the user.
- **Generation is not triggered by upload.** Each run is an AI call; three uploads in a row
  should give one proposal. The client triggers it.
- **Deleting a Chapter keeps its documents**, unassigned and not analyzed (nothing the user
  uploaded disappears), and deletes its proposals. Moving a document to another Chapter marks it
  not analyzed.
- **Fallback providers** (`AI_FALLBACK1/2_*`): tried in order on unavailability or repeated
  invalid output, never on unexpected errors (a bug must surface, not be hidden by another
  vendor). Fallbacks use one model for everything; per-operation models tune the primary only.

### Review engine (Phases 8, 10-13)

- **Learning Items are generated on activation**, from the Concept's own passages only (spec
  §21): activation never fails because of AI; generation runs in the background and reports on
  the Concept. A Concept with no passages gets items by hand (no external knowledge mode yet).
  One generation per Concept; regenerating over existing items is refused, because replacing
  items would destroy their history.
- **Questions are generated with their item**, in the same call: they must test that item's
  objective, and one call per Concept is cheaper than one per item.
- **Role vs in_training** (amendment A6): the role describes content; training is the user's
  choice, and turning it off never deletes anything.
- **Memory state is one `review_states` row per item**, written only through the
  SchedulingPolicy. The policy is pure (no DB, no clock) and versioned per item.
- **Evaluation has no outcome** (amendment A3). The resolver's rules are in
  SCHEDULING.md §3b. EASY only comes from the user: an answer shows correctness, not ease of
  recall. Inconclusive evaluations are never guessed at; the user grades them.
- **Session intent is explicit** (amendment A4); the pool is stored with the session so it can be
  reconstructed. PRACTICE doesn't move the schedule unless opted in; EXAM is refused until
  Phase 15. The owner's "hard only" review is PRACTICE + MARKED_HARD (SCHEDULING.md §3a),
  which changes an earlier note that it would move the schedule.
- **LEARN re-asks an item answered AGAIN** at the end of the session, up to 3 times; it stays
  NEW (not scheduled) until encoded.
- **Evaluation runs inside the answer request**, after the answer is committed (never lost, no
  transaction held during the AI call). A failed or unconfigured evaluation leaves the answer
  pending: retry, self-grade or skip. Each attempt is its own immutable row.
- **Overrides replay, never rewrite**: an override of an already-scheduled answer re-runs the
  transition from the stored previous snapshot and adds a history row that supersedes the old
  one, only while it's the item's latest review.
- **Wording rotation**: the least asked formulation first; all share one memory state.
- **Progress is computed on read** from ReviewStates (no MasteryState table), curriculum and
  memory kept separate; the mastery estimate is the policy's (`mastery_estimate`). Review load
  uses the client's UTC offset for "today"/"tomorrow" (no timezone database needed, which
  Windows Python lacks).
- **Evaluation context**: the item's passages, capped at 12,000 characters.

### iOS

- **XcodeGen** (`ios/project.yml`) rather than a committed `.xcodeproj`: hand-writing Xcode's
  pbxproj format without Xcode to validate it risks a corrupt project file.
- **Custom date decoding** (`APIDateFormat` in `Networking/APIClient.swift`): Foundation's
  `.iso8601` strategy rejects fractional seconds, which the backend always sends.

## Known gaps in "done" phases

- **Moving a Topic/Concept** (spec §20) will need to rewrite the denormalized
  `course_id`/`chapter_id` columns on it and its descendants.
- **Pausing a single Learning Item** (spec §56) arrives with Learning Items (Phase 8).
- **`is_reviewable` walks Topic → Chapter → Course per Concept.** That's fine for single-Concept
  responses, but the review pool (Phase 12) must do it as one joined query, not per row.
- **In-process background tasks** (document processing, curriculum and Learning Item
  generation) die with the server. `app/services/recovery.py` marks any job older than 15
  minutes `FAILED` with a message saying what to do (re-upload, or Try Again). It runs at
  startup and then every `JOB_RECOVERY_INTERVAL_SECONDS` (default 60; 0 disables it). Age-based,
  so it's safe with several workers; idempotent; it never creates or deletes domain data. A job
  that was only slow and finishes after the sweep: generation results are discarded (the row is
  no longer `GENERATING`), a document becomes `READY` with its chunks once. Tested in
  `tests/test_recovery.py`, including recovery in the middle of a running job.
- **A revised edition is matched to existing Concepts only as well as the model can.** If it
  rewords a Concept beyond recognition, it's proposed as new and the old one keeps its
  `needs_source_review` flag; the user merges them by deleting one.
- **Two simultaneous generate requests** for one Course can both pass the "already running"
  check. Harmless (two proposals), not locked against.
- **iOS has no curriculum screens yet**: generate, review/edit, apply, outline, and Concept
  "View source" are backend-only so far.

## Repository layout

```
AdaptiveLearningPlatform/
├── docs/                          # PROJECT_SPEC, ARCHITECTURE, DATA_MODEL, API, AI, SCHEDULING, this
├── web/                           # desktop web client (React + TS + Vite), docs/WEB_ARCHITECTURE.md
├── ios/
│   ├── project.yml                # XcodeGen spec — run `xcodegen generate` on a Mac
│   ├── AdaptiveLearning/          # Swift source (unverified — see ios/README.md)
│   └── AdaptiveLearningTests/
├── backend/
│   ├── app/
│   │   ├── core/                  # settings, domain errors
│   │   ├── db/                    # Base, UTCDateTime, lazy engine/session
│   │   ├── api/                   # routers + error envelope
│   │   ├── auth/  models/  schemas/
│   │   ├── services/
│   │   │   ├── courses/           # implemented (Phase 4)
│   │   │   ├── documents/         # implemented (Phase 5): detect, extract, clean, chunk
│   │   │   ├── curriculum/        # implemented (Phase 6): proposals, grounding, apply, outline
│   │   │   ├── learning/          # Learning Items: generation, training, pause (Phase 8)
│   │   │   ├── scheduling/        # SchedulingPolicy + ladder config (Phase 11)
│   │   │   ├── evaluation/        # ReviewOutcomeResolver (Phase 10)
│   │   │   ├── review/            # sessions, pools, answers, overrides (Phases 10-12)
│   │   │   ├── mastery/           # progress, review load (Phase 13)
│   │   │   └── {retrieval,questions,analytics}/   # still empty
│   │   ├── storage/               # document file storage (local disk, Phase 5)
│   │   ├── ai/                    # AIProvider, OpenAI-compatible transport, mock (Phase 9)
│   │   ├── prompts/               # versioned prompt templates
│   │   └── main.py
│   ├── migrations/                # Alembic (env.py reads the app's settings)
│   ├── tests/
│   ├── alembic.ini  pyproject.toml  Dockerfile
│   └── requirements.txt / requirements-dev.txt
├── docker-compose.yml             # Postgres (+pgvector) + backend — untested, see gaps above
├── .env.example                   # copy to .env (repo root)
└── README.md
```

## Local development

**Backend** — verified end to end on SQLite and Postgres:

```powershell
# one-time
copy .env.example .env
python -c "import secrets; print(secrets.token_urlsafe(48))"   # paste as AUTH_SECRET in .env
cd backend
python -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r requirements-dev.lock

# every schema change / fresh DB
.\.venv\Scripts\python.exe -m alembic upgrade head

# run
.\.venv\Scripts\python.exe -m uvicorn app.main:app --reload   # http://localhost:8000/docs

# test
.\.venv\Scripts\python.exe -m pytest              # SQLite, fast
.\.venv\Scripts\python.exe -m pytest --postgres   # real PostgreSQL via pgserver
.\.venv\Scripts\python.exe -m ruff check .
.\.venv\Scripts\python.exe -m mypy
```

Adding a model change: edit the model, then
`.\.venv\Scripts\python.exe -m alembic revision --autogenerate -m "describe change"`, review the
generated file, and run `pytest --postgres` (the migration drift test will catch mismatches).

**Full stack in Docker** (tested in a cloud session, see "Known environment gaps"):
`docker compose up --build` from the repo root, after creating `.env`. Set `AI_PROVIDER=mock`
to try curriculum generation without an API key.

**iOS**: `xcodegen generate` in `ios/` on a Mac, then open and run in Xcode. Points at
`http://localhost:8000` by default (`Networking/APIConfiguration.swift`).

## Dependencies

- `backend/requirements.txt` / `requirements-dev.txt` list direct dependencies with minimum
  versions. **Install from the lock files**, which pin every package (including transitive ones)
  to the versions the test suite last passed with: `requirements.lock` (runtime: Dockerfile) and
  `requirements-dev.lock` (development and CI).
- To change a dependency: edit the `.txt`, then regenerate both locks and run the full suite on
  SQLite and Postgres before committing:

  ```bash
  uv pip compile requirements.txt --universal --python-version 3.12 -o requirements.lock
  uv pip compile requirements-dev.txt --universal --python-version 3.12 -o requirements-dev.lock
  ```

  Add `-c <file>` with a `pip freeze` of the tested environment to avoid upgrading anything
  else. `--universal` keeps Windows-only packages (e.g. `colorama`) in the lock.

## Demo data

`backend/scripts/seed_demo.py` (with `AI_PROVIDER=mock`) creates `demo@example.com` /
`learnable-demo-2026` with one Course, one Chapter, study material filed under it and its
curriculum applied, every Concept still NOT_STUDIED. It goes through the real API in-process and
is idempotent. Used for the iPhone end-to-end run.

## End-to-end acceptance run

The MVP loop on an iPhone simulator against a real backend:
`ios/AdaptiveLearningUITests/VerticalSliceAcceptanceTests.swift`, scheme `AdaptiveLearningE2E`.
It signs in as the demo user, then goes Course → Chapter → Topic → Concept, activates the
Concept, waits for its Learning Items, and runs a LEARN session. In the session it opens a
source, answers, reads the feedback and disputes the grade. It then checks Home, Progress and
Review, and relaunches the app.

- **CI**: dispatch the iOS workflow manually with `e2e: true` (Actions → iOS → Run workflow). The
  `acceptance` job migrates a fresh SQLite database and seeds it with `AI_PROVIDER=mock`, starts
  uvicorn on `127.0.0.1:8000`, then runs the scheme. It uploads the `.xcresult` and backend log on
  failure. It lives in `ios.yml` because GitHub only dispatches workflows that already exist on
  `main`.
- **On a Mac**: start the backend as above with the demo seed on port 8000, `xcodegen generate`,
  then run the `AdaptiveLearningE2E` scheme's tests.

## Configuration

See `.env.example` at the repo root for the full variable list (spec §95). No secrets are ever
committed to git.

## Testing strategy (spec §77, §78)

- **Database**: Course isolation, ownership, hierarchy, deletion, duplication.
- **Learning**: activation, pause, resume, Learning Item creation.
- **AI** (via `MockAIProvider`, no real API access): schema validation, malformed response
  handling, retries, evaluation, source insufficiency.
- **Scheduling** (pure, no AI/network): correct/incorrect/hard/easy answer, overdue review,
  independent item progression.
- **Review**: due, random, course order, weak, failed, selected pool construction.

Test fixtures to build once evaluation exists (spec §78): (A) fully correct, (B) correct but
incomplete, (C) incorrect, (D) semantically correct with different wording, (E) misconception,
(F) ambiguous, (G) correct by external knowledge but unsupported by Course source, (H) correct
with irrelevant extra information, (I) insufficient source context.

## CI (GitHub Actions — https://github.com/MrCheope21/LEARNABLE/actions)

- **`.github/workflows/backend.yml`** (Ubuntu): `ruff check`, `ruff format --check`,
  `mypy` (strict, with the pydantic plugin, over `app/` and `migrations/env.py`), `pytest`
  on SQLite, then `pytest` again against a PostgreSQL service container (`pgvector/pgvector:pg16`,
  the same image as `docker-compose.yml`) via `TEST_DATABASE_URL`.
- **`.github/workflows/ios.yml`** (macOS): installs XcodeGen, generates the project, picks an
  available iPhone simulator at runtime, and runs `xcodebuild test`. On failure the full build
  log is uploaded as an artifact. **This is the only place the iOS code gets compiled.** A
  manual run with `e2e: true` also runs the simulator acceptance test (see "End-to-end
  acceptance run").
- **`.github/workflows/web.yml`** (Ubuntu): the web client. `npm ci`, an API-types drift check
  against the backend's OpenAPI schema, `tsc`, ESLint, Vitest, production build, and a check that
  no AI credential can reach the browser bundle. A second job runs Playwright against a real
  backend with the mock AI and demo seed. Details: `docs/WEB_ARCHITECTURE.md` §8.
- **`.github/workflows/real-ai.yml`** (Ubuntu, **manual only**): lists models, or benchmarks a
  real free provider or the whole free chain (`provider: router`). The cost policy is pinned to
  FREE_ONLY, so it cannot reach a paid endpoint. Details: `docs/FREE_AI_ROUTING.md` §8.
- **Secrets:** runtime AI keys exist only as GitHub Actions secrets, entered by the owner in the
  GitHub web UI and read only by `real-ai.yml`:
  - `GROQ_API_KEY`, `MISTRAL_API_KEY`, `GEMINI_API_KEY`, `OPENROUTER_API_KEY`,
    `CLOUDFLARE_API_TOKEN`, `NVIDIA_API_KEY`;
  - gateways for Chinese model families: `DASHSCOPE_API_KEY`, `TENCENT_TOKENHUB_API_KEY`,
    `SILICONFLOW_API_KEY`;
  - optional: `COHERE_API_KEY`.

  Repository variables hold non-secret settings: `CLOUDFLARE_ACCOUNT_ID`, `ALIBABA_WORKSPACE_ID`,
  the billing-guard confirmations `ALIBABA_FREE_ONLY_CONFIRMED` / `TENCENT_FREE_ONLY_CONFIRMED`,
  per-provider
  `*_MODEL`, `AI_FREE_MODELS`, `AI_ROUTE_*`, `AI_EVALUATION_APPROVED_MODELS`. Never put a key in
  `.env`, code, docs, workflow YAML or chat. Ordinary CI uses only `MockAIProvider`.
- A workflow must exist on `main` before GitHub offers manual dispatch for it; until then, a
  pull request runs `web.yml`, and `real-ai.yml` can't be started.
- Each workflow runs only when its own directory changes (or via "Run workflow" manually),
  cancels superseded runs, and has a hard timeout — macOS minutes are expensive on private repos.
- Ruff rules beyond style: bugbear (`B`), bandit security checks (`S`), pyupgrade, pytest
  style — config in `backend/pyproject.toml`.
- No core branch should remain knowingly broken (spec §97).

## Acceptance test (MVP-complete definition, spec §102)

The full workflow must work end to end: create Course → create/import Chapters/Topics → import
PDF → extract source text → create source chunks → generate curriculum proposal → user
accepts/edits curriculum → Concepts exist → user activates selected Concepts → Learning Items
generated → Questions generated → user starts Review → answers by text → AI evaluates → feedback
shown → scheduling policy updates the Learning Item → next review stored → review history stored
→ Concept mastery updates → Topic/Chapter/Course progress updates → a second Course remains
isolated → the runtime AI provider can be changed through configuration → the application still
works without any dependency on the coding agent's model identity.

## Next step

See PROJECT_STATUS.md §6. In short:

1. **iOS review loop**: replace `PendingReviewService` with the real API (LEARN / review /
   practice sessions, answer, feedback with sources, self-grade), plus activation and review
   load on Home. iOS can't be built here: verify by running the `ios` workflow manually on the
   branch, or via a PR.
2. **iOS curriculum screens**: chapters with their material, proposal review/apply, outline.
3. **Try real models** on one real chapter (AI.md §3); the resolver thresholds may need tuning
   against what real evaluators return.
4. Exam Mode (Phase 15), question variations and follow-ups, coverage model, analytics.
