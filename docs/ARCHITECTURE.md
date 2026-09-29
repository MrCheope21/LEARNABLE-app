# Architecture

Status: **Phase 1 — documentation and scaffold only.** No functional code has been written yet.
See [DEVELOPMENT.md](./DEVELOPMENT.md) for phase status and [PROJECT_SPEC.md](./PROJECT_SPEC.md)
for the full product spec this document implements.

## 1. Layers

```
USER
 │
 ▼
iPHONE APP (SwiftUI)
 │  HTTPS (JSON)
 ▼
FASTAPI BACKEND
 │
 ▼
DOMAIN SERVICES
 ├── Course Service        (hierarchy CRUD, ownership, isolation enforcement)
 ├── Document Service       (upload, extract, clean, chunk, index)
 ├── Retrieval Service       (scoped RAG: course/chapter/topic/concept)
 ├── Learning Service        (activation, pause/resume, Learning Item lifecycle)
 ├── Question Service        (question formulation generation/selection)
 ├── Evaluation Service       (AI answer evaluation, schema validation)
 ├── Scheduling Service        (SchedulingPolicy — independent of AI)
 ├── Mastery Service            (Concept mastery, coverage model, progress rollups)
 ├── Analytics Service           (review load, retention trend, weak areas)
 └── AIProvider                   (abstraction over runtime LLM)
       │
       ▼
 RUNTIME AI PROVIDER (OpenAI-compatible HTTP client)
       │
       ▼
 MODEL API (Qwen / DeepSeek / Kimi / GLM / managed / self-hosted — configurable)
```

The iOS client **never** calls an LLM provider directly. All AI calls are proxied and mediated by
the backend's `AIProvider` abstraction. The backend is the trusted security boundary; the iOS
client is untrusted (see §81 of the spec).

## 2. iOS Client Architecture

MVVM with `@Observable` view models (iOS 17+), Swift Concurrency throughout. No business logic in
SwiftUI `View`s. Dependencies point inward: Presentation → Domain protocols ← Data/Networking.

```
ios/AdaptiveLearning/
  App/            @main + AppDependencies — the composition root, the only place concrete
                  implementations are chosen
  Presentation/   SwiftUI Views + @Observable ViewModels, per feature (Auth, Home, Courses, Review,
                  ProgressDashboard, Settings); RootView switches sign-in ↔ app
  Domain/         Entities, read models, and the repository/service protocols
                  (no SwiftUI/URLSession/persistence imports)
  Data/           Remote implementations of the Domain protocols; Pending/ holds explicit
                  stand-ins for features the backend doesn't have yet
  Networking/     APIClient (attaches the bearer token, maps the API error envelope), TokenStore
  Persistence/    KeychainTokenStore; offline cache + answer drafts later (Phase 16)
  Resources/      Localizable.xcstrings (English + Italian)
  Speech/         SpeechTranscriptionService abstraction + Apple Speech implementation
```

Rules:
- View models depend only on Domain protocols, injected via `AppDependencies`, so each is
  unit-tested with fakes (`AdaptiveLearningTests/ViewModelTests.swift`).
- Networking layer only talks to the backend API — never to an AI provider.
- The access token lives in the Keychain. A 401 on any authenticated request deletes it and
  returns the app to sign-in; signing out discards all view models, so one account's data never
  survives into another session.
- No hard-coded UI text: SwiftUI literals are String Catalog keys; user content uses
  `Text(verbatim:)`.
- `SpeechTranscriptionService` is a protocol; the Apple Speech implementation is swappable per
  §31 of the spec.

## 3. Backend Architecture

FastAPI, PostgreSQL, optional pgvector, object storage for documents, background jobs for
expensive processing (document ingestion, curriculum generation).

```
backend/app/
  core/         Settings (env-var config) and domain errors (NotFoundError, ConflictError, ...)
  db/           Base (+ constraint naming convention), UTCDateTime type, lazy engine/session
  api/          route handlers (thin — delegate to services) + the error envelope (errors.py)
  auth/         authentication: security (Argon2id/JWT), schemas, dependencies, router
  models/       SQLAlchemy ORM models — see DATA_MODEL.md; importing the package registers all
  schemas/      Pydantic request/response + AI I/O schemas (cross-cutting; auth's own schemas
                live in auth/schemas.py per module cohesion)
  services/     domain services, one package per bounded context (see layer diagram above)
  ai/           AIProvider interface + concrete provider implementations + MockAIProvider
  prompts/      versioned prompt templates (see AI.md)
  storage/      object storage adapter (documents, optional audio)
backend/migrations/   Alembic — the only thing that creates or changes the schema
backend/tests/
```

Route handlers must stay thin: validate input, verify Course ownership/scope, delegate to a
service, return a schema. Business logic lives in `services/`, never in `api/`.

**Error flow**: services raise domain errors from `app/core/errors.py` (never `HTTPException`,
so they stay framework-agnostic); `app/api/errors.py` maps every error — domain, validation,
routing, and unhandled — to the single envelope documented in API.md. Route handlers contain no
try/except.

## 4. Course Isolation (cross-cutting)

Every service function that reads or writes Course-scoped data must:
1. Accept an authenticated `user_id` and a `course_id`.
2. Verify server-side that the user owns/has access to that Course before doing anything else.
3. Scope every DB query, retrieval call, and AI prompt construction to that `course_id` (and
   chapter/topic/concept where applicable).

This is enforced at the service layer, not trusted from client input (spec §10, §81). Explicit
cross-course features (spec §11) are a distinct, clearly-labeled future code path — never the
default.

## 5. AI vs Scheduler Separation

```
User Answer → AI Evaluation (evidence) → ReviewOutcomeResolver → Review Outcome
            → [user override] → SchedulingPolicy → next state / interval / due date
```

`AIProvider.evaluate_answer` returns semantic evidence only (classification, scores, points,
misconceptions, context sufficiency, feedback) — no outcome and no date. The deterministic,
versioned `ReviewOutcomeResolver` (`app/services/evaluation/resolver.py`) turns evidence into
an outcome or "undecided" (the user grades it). `SchedulingPolicy`
(`app/services/scheduling/`, pure) owns every state, level, interval and date. Neither the model
nor its quirks can move the schedule directly (spec §42, §104). The user can override an
outcome; the AI evaluation and the resolved outcome are kept for audit and benchmarking.

### Session intent

Sessions carry an explicit `SessionIntent` in domain code, independent of how their pool is
selected: **LEARN** (encode NEW items: introduction → first retrieval → feedback → success
initializes the schedule), **SCHEDULED_REVIEW** (due items; drives the policy), **PRACTICE**
(deliberate practice by scope and mode; never changes memory state unless opted in), **EXAM**
(Phase 15; must never affect the schedule by accident). See SCHEDULING.md §4.

## 6. AI Provider Replaceability

`AIProvider` is an interface with one required method set (§32). Concrete implementations talk to
an OpenAI-compatible (or equivalent) HTTP API, configured entirely through environment variables
(§33) — no provider-specific code paths in business logic. `MockAIProvider` (§76) is the
deterministic test double; no test may require real API access.

## 7. Data Flow — Curriculum and Learning Items

```
Document upload (filed under a Chapter) → Document Service (detect/extract/clean/chunk)
  → course- and chapter-scoped passages (only material not analyzed yet)
    → AIProvider.generate_chapter_curriculum (validated JSON, grounded: every Concept cites
      passages that were sent)
      → CurriculumProposal (nothing changes in the Course yet)
        → user edits and applies → Topics/Concepts (NOT_STUDIED) + concept_sources
          → user activates a Concept → AIProvider.generate_learning_items from its passages
            → Learning Items (+ questions, NEW memory state, item sources)
```

## 8. Data Flow — Review

```
Review Service builds and stores a pool (course scope, intent, selection mode; only trained,
unpaused items of ACTIVE Concepts under unpaused sections)
  → next card: the item's least-asked Question Formulation (LEARN adds the introduction)
    → iOS shows it and sends a text/voice answer
      → Answer committed before the AI call (never lost)
        → AIProvider.evaluate_answer, grounded in the item's own passages (validated, retried,
          fallback providers)
          → ReviewOutcomeResolver → final outcome (or the user grades it)
            → SchedulingPolicy transition (if the intent allows) → Review history row
              → progress/mastery are computed on read from ReviewStates
```

## 9. Why Not a Single "Card" Table

Per spec §8 and §104, Concept, Learning Item, and Question Formulation are distinct entities with
distinct lifecycles:
- A **Concept** groups multiple Learning Items and has a derived mastery estimate — it has no SRS
  state of its own.
- A **Learning Item** is the atomic SRS unit — each has independent scheduling state (§26).
- A **Question Formulation** is one of several phrasings of the same Learning Item and shares that
  item's single SRS state (§27).

Collapsing these into one generic flashcard table would make independent-item scheduling and
wording-invariant review (§26, §27) impossible to express correctly.

## 10. Open Architectural Decisions (documented per spec §5 ambiguity rule)

These are non-critical choices made autonomously; revisit if requirements sharpen:
- **Auth**: JWT bearer tokens (PyJWT, HS256 pinned in code), Argon2id password hashing
  (`argon2-cffi`), own DB (no third-party IdP). See `docs/DEVELOPMENT.md` "Decisions made
  autonomously → Auth".
- **Schema management**: Alembic migrations, verified against the models by a test; Postgres is
  the target, SQLite is supported for zero-setup local dev.
- **iOS local persistence**: not yet built (Phase 16); SwiftData is the likely choice over
  CoreData for new code, to be confirmed when that phase starts.
- **Background jobs**: in-process FastAPI background tasks (document processing, curriculum and
  Learning Item generation); interrupted jobs are detected by age. A dedicated queue only when
  volume or multiple replicas require it.
- **Answer evaluation is synchronous** in the answer request (the user waits for feedback
  anyway); the answer is committed first, and a failed evaluation leaves it pending for a
  retry or a self-grade.
- **pgvector**: enabled from the start given the spec lists it as part of the initial stack, used
  only for course-scoped retrieval, never global.
