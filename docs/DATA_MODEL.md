# Data Model

Status: **User, Course, CourseSettings, Chapter, Topic, Concept implemented (Phase 3–4)**, with
the schema created by Alembic (`backend/migrations/`) and tested on both PostgreSQL and SQLite.
Everything else below is still a design reference for later phases. This document enumerates
the core entities from spec §8 and their fields as specified.

Do not collapse these into a generic "Card" table (spec §8, §104).

## Storage conventions (all implemented tables)

- **Primary keys**: UUID (`uuid` on Postgres).
- **Timestamps** (`created_at`, `updated_at`): timezone-aware UTC (`timestamptz` on Postgres);
  naive datetimes are rejected on write.
- **Foreign keys**: `ON DELETE CASCADE` down the hierarchy (User → Course → Chapter → Topic →
  Concept, and Course → CourseSettings), so deleting a Course or an account removes everything
  it owns in one database operation.
- **Enums** (`study_state`): VARCHAR + CHECK constraint, not native Postgres ENUMs.
- **Constraint names** are deterministic (`pk_users`, `fk_topics_course_id_courses`, ...).
- **Schema changes go through Alembic only**; `tests/test_migrations.py` fails if a model and the
  migrations disagree.

## Hierarchy entities

### User — implemented (`app/models/user.py`)
- id (UUID)
- email, hashed_password
- timezone (IANA name, default UTC: the user's calendar day for streaks, goal and activity)
- daily_goal (completed answers per day, default 20)
- token_version (carried by access tokens; a password change increments it and ends every
  session)

### PasswordResetToken — implemented (`app/models/auth.py`)
- user_id, token_hash (SHA-256 of the emailed token; unique), created_at, expires_at, used_at
- single use; a newer link or a password change retires older ones
- created_at

### Course — implemented (`app/models/course.py`)
- id, user_id (owner — the ownership boundary every isolation check is built around, spec §10)
- title, description, language
- paused (bool, default false — spec §56; also on Chapter and Topic, see below)
- settings (→ CourseSettings, 1:1, cascade-deleted with the Course)
- created_at, updated_at

### CourseSettings — implemented, not yet exposed via API
- id, course_id
- scheduling_policy (default `"chessable_v1"`)
- external_knowledge_mode (bool, default false — spec §19)
- audio_retention (default `"none"` — spec §84)

### Chapter — implemented
- id, course_id
- title, description, order, paused
- (topics, progress are derived/joined, not stored columns)

### Topic — implemented
- id, chapter_id, course_id (denormalized — see "Cross-cutting rules")
- title, description, order, paused

### Concept — implemented
- id, topic_id, chapter_id, course_id (denormalized chapter_id/course_id for scoping convenience)
- title, description, order (position in the Topic; ties fall back to created_at)
- needs_source_review (bool): set when deleting material left it with no source passage; cleared
  when revised material is linked to it, or by the user
- item_generation_status (NONE | GENERATING | READY | INSUFFICIENT_CONTEXT | FAILED),
  item_generation_error, item_generation_started_at: Learning Item generation (Phase 8)
- study_state (NOT_STUDIED | STUDIED | ACTIVE | PAUSED | COMPLETED — spec §22)
- is_reviewable (derived, not stored): ACTIVE and no paused Topic/Chapter/Course above it
- prerequisites (optional, guidance-only — spec §55) — **not yet implemented**, deferred until a
  concrete need arises

## Knowledge Repository entities

### Document — implemented (`app/models/document.py`)
- id, course_id
- chapter_id (nullable, ON DELETE SET NULL): the Chapter the material is filed under
- analyzed_at (nullable): when a curriculum covering the whole document was applied; unanalyzed
  documents are what the next generation for their scope sends by default
- filename (display only), mime_type (from content), kind (PDF | TEXT | MARKDOWN | DOCX | PPTX |
  IMAGE — the spec's "source type"), size_bytes, sha256 (the spec's "hash")
- source_created_at (the file's own creation date), created_at (import date), updated_at
- storage_key (the spec's "storage location": `courses/{course_id}/documents/{document_id}`)
- status (PROCESSING | READY | FAILED), error_message (user-safe), page_count, chunk_count
- unique (course_id, sha256): duplicates are detected per Course only

### DocumentChunk — implemented
- id, document_id, course_id (denormalized so retrieval is scoped with a single WHERE, spec §72)
- position (order in the document), text
- page_number (PDF page / PPTX slide), section (heading, PDF bookmark, or slide title),
  paragraph_start/paragraph_end (the spec's "paragraph" and "source position")
- A chunk never spans two pages or two sections.
- embedding (optional, pgvector — course-scoped retrieval only) — **not yet**, arrives with
  retrieval

### ConceptSource — implemented (`app/models/curriculum.py`)
- id, concept_id, chunk_id (→ DocumentChunk), course_id (denormalized), created_at
- unique (concept_id, chunk_id)
- Links a Concept to the passages it was derived from, for "View source" (spec §18, §66).
  Deleting the document cascades to these rows; the Concept stays.
- The spec's "SourceReference". Learning Items (Phase 8) get their own link table the same way.

## Curriculum generation entities

### CurriculumProposal — implemented (`app/models/curriculum.py`)
- id, course_id
- chapter_id (nullable, cascade): set = Chapter proposal (Topics → Concepts for that Chapter);
  null = Course proposal (Chapters → Topics → Concepts)
- document_ids (JSON): documents sent in full; marked analyzed on apply
- status (GENERATING | READY | INSUFFICIENT_CONTEXT | FAILED | APPLIED), error_message
- content (JSON: `{"chapters": [...]}` or `{"topics": [...]}`, each Concept with the ids of the
  chunks it cites and, for Chapter proposals, the existing Topic/Concept it merges into; null
  until READY)
- passages_used, passages_total, dropped_concepts
- ai_provider, ai_model, ai_model_version, prompt_version (spec §73, §74)
- created_at, updated_at, applied_at
- Held for review only: nothing here reaches the hierarchy until the user applies it (spec §20).

## Learning entities — implemented (`app/models/learning.py`)

### LearningItem
- id, concept_id, topic_id, chapter_id, course_id (all denormalized for single-WHERE scoping)
- title, objective, expected_knowledge (the reference answer), essential_points (JSON list)
- role: CORE_TRAINABLE | SUPPORTING_TRAINABLE | COMMON_TRAP | INFORMATIONAL | REFERENCE |
  OPTIONAL_EXTENSION (spec §24: what the content is)
- in_training (bool): whether it takes part in spaced repetition (the user's choice; starts on
  for the first three roles when there is a question). Turning it off deletes nothing.
- difficulty (1-5), order, paused (item-level pause, spec §56)
- ai_provider, ai_model, ai_model_version, prompt_version (null for hand-written items)
- created_at, updated_at
- Study state is the parent Concept's; memory state is its ReviewState.

### QuestionFormulation
- id, learning_item_id, course_id
- question_type (RECALL | DEFINITION | EXPLANATION | WHY_HOW | COMPARISON | CAUSE_EFFECT |
  APPLICATION | SCENARIO | CALCULATION | CLASSIFICATION | TEACH_BACK | ORAL_EXAM |
  COUNTEREXAMPLE | EDGE_CASE | CONCEPT_CONNECTION — spec §28)
- text, times_asked, last_asked_at (wording rotation), created_at
- All formulations of an item share its ONE ReviewState (spec §27).

### LearningItemSource
- id, learning_item_id, chunk_id, course_id, created_at; unique (learning_item_id, chunk_id)
- The passages the item was generated from and is evaluated against (the spec's
  "SourceReference", like ConceptSource for Concepts).

### ReviewState (1:1 with LearningItem)
- id, learning_item_id (unique), course_id
- state: NEW | LEARNING | REVIEW | RELEARNING | MASTERED (spec §23)
- level (0 = not encoded), interval_seconds, due_at (indexed), last_reviewed_at
- review_count, successful_review_count, failed_review_count, lapse_count
- hard_count, marked_hard (the most recent answer was HARD)
- paused_at (item pause; resume adds the paused time to due_at)
- scheduling_policy, scheduling_policy_version (the item keeps the version it started on)
- Written only through the SchedulingPolicy (`app/services/scheduling`).

## Review entities — implemented (`app/models/review.py`)

### ReviewSession
- id, user_id, course_id
- intent: LEARN | SCHEDULED_REVIEW | PRACTICE | EXAM | CONSOLIDATION
- selection_mode: NEW | DUE | COURSE_ORDER | RANDOM | WEAK | RECENTLY_FAILED | MARKED_HARD |
  SELECTED | CONSOLIDATION (each item in three consecutive slots)
- affects_schedule (LEARN/SCHEDULED_REVIEW: always; PRACTICE: only if opted in)
- chapter_id, topic_id, concept_ids (scope), item_ids (the pool, in order; LEARN appends an item
  again when it isn't encoded yet), position
- started_at, ended_at
- Keeps what's needed to reconstruct how the pool was chosen (spec §83).

### Answer
- id, user_id, course_id, session_id, learning_item_id, question_formulation_id
- intent (copied from the session), method (TEXT | VOICE — the transcript is the text; no
  audio is stored), text, created_at
- resolved_outcome + resolver_version (from the ReviewOutcomeResolver; null = inconclusive)
- override_outcome, override_note, overridden_at (the user's grade)
- final_outcome (override if any, else resolved)
- finalized_at (first final outcome: the completed attempt for activity; set once)
- consolidation_round (1-3 in CONSOLIDATION sessions), hint_used (set by the server from the
  stored hint reveal)

### Evaluation (one row per attempt; immutable)
- id, answer_id, course_id, status (COMPLETED | FAILED | NOT_CONFIGURED), error_message
- classification (CORRECT | PARTIALLY_CORRECT | MISCONCEPTION | WRONG | UNCERTAIN)
- correctness, completeness, conceptual_understanding, precision, confidence (0.0–1.0)
- correct_points, missing_points, misconceptions, source_corrections (JSON lists)
- context_sufficient, feedback
- ai_provider, ai_model, ai_model_version, prompt_version, created_at
- **No outcome**: the AI's evidence is kept separate from the outcome (spec §85 amended; see
  SCHEDULING.md §3b). Misconceptions reach the Concept through answer → item → concept.

### Review (history row; append-only)
- id, course_id, learning_item_id, answer_id, intent, outcome
- previous_state, previous_level, previous_due_at, next_state, next_level, next_due_at
- reviewed_at, lateness_seconds (spec §47)
- scheduling_policy, scheduling_policy_version (spec §86)
- previous_snapshot (JSON: the full memory state before, so an override can be replayed)
- supersedes_review_id, superseded (a user override adds a row; nothing is rewritten)

## Rewards and activity — implemented (`app/models/rewards.py`)

Beside the learning loop, never read by it (docs/XP_AND_ACTIVITY.md).

### ItemSuccessCounter
- user_id, course_id, learning_item_id (unique), successful_answers: the n in min(10n, 150),
  incremented atomically (INSERT … ON CONFLICT DO UPDATE … RETURNING)

### XpAward (the XP ledger; one row per eligible finalized attempt, 0 XP included)
- user_id, course_id, learning_item_id, answer_id (unique), session_id
- reason (INITIAL | SCHEDULED_REVIEW), occasion_key ("initial:2", "review:<due date>")
- correct, ordinal, base_xp, hint_used, xp, policy_version, awarded_at
- unique (learning_item_id, occasion_key) and (learning_item_id, ordinal): no duplicate awards
  even under concurrent requests

### DailyActivity
- user_id, day (local date), attempts, xp; unique (user_id, day). The single source for streak,
  daily goal, XP today, lifetime XP and the activity calendar.

### HintReveal
- user_id, course_id, session_id, slot (session position), learning_item_id,
  question_formulation_id, text, revealed_at; unique (session_id, slot)
- QuestionFormulation.hint caches the cue built from the item's reference.

### MasteryState — not stored
- Mastery and progress are computed on read from ReviewStates (`app/services/mastery`), so
  they can't drift from the schedule. Store a snapshot table only if history charts need it.

## Exam entities

### ExamSession
- id, user_id, course_id
- scope (chapter/topic/concept selection), question_count, difficulty, time_limit, question_types
- start_time, end_time

### ExamQuestion
- id, exam_session_id, learning_item_id, question_formulation_id
- answer_id (nullable until answered)
- (no immediate evaluation during the exam — spec §57)

## Traceability / versioning entities

### PromptVersion / ModelVersion — stored as columns, not tables
- Every AI-produced row carries `ai_provider`, `ai_model`, `ai_model_version` and
  `prompt_version` directly (CurriculumProposal today; Learning Items and Evaluations later).
  The prompt text itself lives in versioned files (`app/prompts/<name>_vN.py`) that are never
  edited once used, so the version string identifies it exactly (spec §73, §74).

## Future entities (not implemented in MVP; architecture must not preclude them)

- **CourseTemplate** — reusable educational content (structure, source, Concepts, Learning
  Items, question templates), decoupled from any single user's learning state (spec §62).
- **CourseInstance** — a user's personal activation/memory/progress against a CourseTemplate.
- **CoursePackage** — export/import container: Course metadata, Chapters, Topics, Concepts,
  Learning Items, Question Formulations, source references, curriculum order — explicitly
  **excludes** personal review history/mastery/notes unless requested (spec §91).
- **CourseImport / CourseExport** — job records for the above.

## Cross-cutting rules

- Every table that is Course-scoped carries (directly or via join) a `course_id`, and every
  service query filters on it server-side (spec §10).
- `Answer` rows are written before evaluation is attempted, so a network/AI failure never loses
  the user's response (spec §79, §80).
- `Review` history rows are append-only — scheduling state changes are never overwritten in
  place without a corresponding audit row (spec §86).
