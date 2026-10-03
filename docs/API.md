# API

Status: Auth, the Course hierarchy, Concept activation, documents, AI curriculum generation,
Learning Items, review sessions with AI evaluation and scheduling, and progress are
**implemented and tested**. Exam Mode and cross-course endpoints are design reference. FastAPI backend, versioned under `/api/v1`.
Interactive docs at `/docs` when the server is running. All endpoints except register/login
require authentication; all Course-scoped endpoints verify server-side ownership before touching
data (spec §10, §81).

## Conventions (implemented)

- JSON in, JSON out. UUID path/body identifiers.
- **Auth**: `Authorization: Bearer <access_token>` from `POST /api/v1/auth/login`. Missing,
  malformed, expired or tampered tokens → 401 with `WWW-Authenticate: Bearer`.
- **Every error uses one envelope** — including 404 for unknown routes, 405, 422 and 500:

  ```json
  {"error_type": "not_found", "message": "Course not found", "details": {}}
  ```

  | Status | `error_type` | When |
  |---|---|---|
  | 401 | `authentication_failed` | bad/missing token, wrong credentials |
  | 404 | `not_found` | resource missing **or owned by someone else** (never 403 — see below) |
  | 405 | `method_not_allowed` | wrong HTTP method |
  | 409 | `conflict` | e.g. email already registered |
  | 409 | `invalid_state_transition` | e.g. pausing a Concept that isn't ACTIVE |
  | 422 | `validation_error` | `details.errors` = `[{"loc": [...], "msg": "...", "type": "..."}]` |
  | 500 | `internal_error` | generic message only; details are logged server-side |
  | 503 | `ai_not_configured` | an AI endpoint was called while `AI_PROVIDER` is empty |
  | 503 | `ai_unavailable` | a synchronous AI call failed on every candidate; `details.attempts` = `[{provider, model, failure}]` |
  | 503 | `free_capacity_exhausted` | `AI_COST_POLICY=FREE_ONLY` and no free provider could answer; a paid one is never tried instead (docs/FREE_AI_ROUTING.md) |

  AI failures during background work (`ai_unavailable`, `ai_invalid_output`) are not HTTP
  responses: they end the job `FAILED` with a user-safe `error_message` (see below).

  Validation errors never echo the rejected input back (it can be a password).
- **Cross-Course access returns 404, identical to a nonexistent id**, so a response never
  confirms that another user's resource exists (spec §10).
- **Request bodies**: unknown fields are rejected (422); string fields are trimmed (except
  passwords); lengths are capped (titles 1–200, descriptions ≤2000).
- **PATCH**: omitted fields are left unchanged; an explicit `null` is a 422.
- **Timestamps**: UTC, ISO-8601, millisecond precision, `Z` suffix —
  `"2026-09-23T08:42:33.720Z"`. The iOS decoder (`APIDateFormat`) depends on this exact shape.
- AI output is always schema-validated; malformed output is retried once, then reported as a
  failure, never guessed around (spec §36, §80).
- List endpoints are paginated once volume warrants it (not required for MVP scaffolding).

## Curriculum

All endpoints below are **implemented and tested** (`backend/tests/test_courses.py`,
`backend/tests/test_isolation.py`).

```
POST   /api/v1/courses
GET    /api/v1/courses
GET    /api/v1/courses/{course_id}
PATCH  /api/v1/courses/{course_id}
DELETE /api/v1/courses/{course_id}          # cascades to chapters/topics/concepts

POST   /api/v1/courses/{course_id}/chapters
PATCH  /api/v1/chapters/{chapter_id}
DELETE /api/v1/chapters/{chapter_id}

POST   /api/v1/chapters/{chapter_id}/topics
PATCH  /api/v1/topics/{topic_id}
DELETE /api/v1/topics/{topic_id}

POST   /api/v1/topics/{topic_id}/concepts
GET    /api/v1/concepts/{concept_id}
PATCH  /api/v1/concepts/{concept_id}
DELETE /api/v1/concepts/{concept_id}

GET    /api/v1/courses/{course_id}/outline   # the whole tree: chapters → topics → concepts

PUT    /api/v1/courses/{course_id}/chapter-order          # {"ids": [...]} → 204
PUT    /api/v1/chapters/{chapter_id}/topic-order          # {"ids": [...]} → 204
PUT    /api/v1/topics/{topic_id}/concept-order            # {"ids": [...]} → 204
PUT    /api/v1/concepts/{concept_id}/learning-item-order  # {"ids": [...]} → 204
```

- Chapters, Topics and Concepts all have an `order` (≥ 0, default 0), settable on create and
  PATCH. Lists and the outline sort by `order`, then creation time.
- **Reordering (drag and drop)** sends a parent's children in their new order; the server
  numbers them 0..n-1 in one transaction. `ids` must name every current child exactly once, so a
  stale list (a child added, deleted or moved elsewhere since it was loaded) or an id from another
  parent is a 422 `order_mismatch` and nothing changes (`backend/tests/test_reorder.py`).
- **`GET /courses/{id}/outline`** returns `ChapterRead` + `topics: [TopicRead + concepts:
  [ConceptRead]]`, loaded in three queries regardless of size.

Every one of these requires `Authorization: Bearer <token>` and enforces ownership server-side —
a request for a Course/Chapter/Topic/Concept that exists but belongs to another user gets `404`,
same as one that doesn't exist at all (spec §10; see `docs/DEVELOPMENT.md` "Decisions made
autonomously").

## Knowledge Repository / documents (spec §16-18, §66) — implemented and tested

```
POST   /api/v1/courses/{course_id}/documents            # multipart "file" [+ "chapter_id", "purpose"] → 202
GET    /api/v1/courses/{course_id}/documents            # ?chapter_id= to list one Chapter's
GET    /api/v1/documents/{document_id}
GET    /api/v1/documents/{document_id}/file             # the original file, owner only (attachment)
PATCH  /api/v1/documents/{document_id}                  # {"chapter_id": uuid | null}
DELETE /api/v1/documents/{document_id}                  # also deletes the stored file
GET    /api/v1/documents/{document_id}/chunks           # ?offset=0&limit=50 (max 200), by position
GET    /api/v1/documents/{document_id}/chunks/{chunk_id}   # "View source" passage (spec §66)
```

**Material is filed under Chapters.** The optional form field `chapter_id` files an upload
under a Chapter of the same Course (404 otherwise). `PATCH` moves it to another Chapter, or
unassigns it with `null`; a move marks it not analyzed. Deleting a Chapter keeps its documents,
unassigned and not analyzed.

**Upload is asynchronous.** The response is `202` with `status: "PROCESSING"`. Poll
`GET /documents/{id}` until the status is `READY`, or `FAILED` with a user-safe `error_message`.
Failed documents are kept in the repository, not dropped.

| Upload response | When |
|---|---|
| 202 | stored; processing started |
| 409 `conflict` | this exact file is already in this Course; `details.document_id` is the existing one |
| 413 `payload_too_large` | over `MAX_UPLOAD_MB` (default 50) |
| 415 `unsupported_media_type` | empty, or not a supported type |

- **Supported types**: PDF, DOCX, PPTX, TXT, Markdown, and images (PNG/JPEG/TIFF/HEIC).
  - The type is detected from the file's **content**; the filename and Content-Type the client
    sends are ignored for this, apart from telling `.txt` and `.md` apart.
  - Images are stored but `FAILED` ("text extraction from images and scans isn't supported yet").
  - Scanned PDFs with no text layer also end `FAILED`.
  - PDFs protected with an open password fail. PDFs with only an owner password (common for
    textbooks) are read normally.
- **Duplicates** are checked per Course only. The same file in another Course, or another user's
  account, is never reported as a duplicate, since that would leak what they contain.
- **`DocumentRead`**: `id, course_id, chapter_id, filename, mime_type, kind, purpose, size_bytes,
  sha256, status, error_message, import_notice, page_count, chunk_count, analyzed_at,
  source_created_at, created_at, updated_at`.
  - `purpose`: `MATERIAL` (default; feeds curriculum generation) or `QUESTION_BANK` (the user's
    own "Domanda:"/"Risposta:" pairs, imported without AI as NOT_STUDIED Concepts with one
    Learning Item each).
- **Download** (`GET /documents/{id}/file`): the original bytes as `application/octet-stream`
  with `Content-Disposition: attachment`, `X-Content-Type-Options: nosniff` and
  `Cache-Control: private, no-store`, after the ownership check (404 otherwise). 404
  `file_missing` if the stored file is gone. No public or pre-signed URLs
  (docs/DEPLOYMENT.md §3).
  - `analyzed_at`: when a curriculum covering the whole document was applied; `null` means the
    next generation for its scope will include it.
- **Deleting a document** removes its passages. A Concept left with no source passage at all is
  kept but gets `needs_source_review: true` (see below).
  - `filename` is display-only; the file is stored under a server-generated key.
  - `source_created_at` is the file's own creation date, when it has one.
  - `created_at` is the import date.
- **`ChunkRead`**: `id, document_id, position, page_number, section, paragraph_start,
  paragraph_end, text`.
  - A passage never spans two pages or two sections. `page_number` is the PDF page or PPTX slide.
  - `section` is the nearest heading, PDF bookmark, or slide title.

## AI curriculum generation (spec §19-21) — implemented and tested

```
POST   /api/v1/courses/{course_id}/curriculum-proposals   # body optional → 202 GENERATING
GET    /api/v1/courses/{course_id}/curriculum-proposals   # newest first
GET    /api/v1/curriculum-proposals/{proposal_id}
DELETE /api/v1/curriculum-proposals/{proposal_id}         # reject / discard
POST   /api/v1/curriculum-proposals/{proposal_id}/apply   # body: the reviewed tree → 201 outline
GET    /api/v1/concepts/{concept_id}/sources              # "View source" for a Concept
```

**The AI proposes, the user decides.** A proposal never changes the Course. Applying creates
what the user sends, and every new Concept starts `NOT_STUDIED`: nothing is activated (§21).

### Two scopes

- **Chapter** (`{"chapter_id": ...}`), the main flow. The user creates the Course and its
  Chapters and files material under each. The AI proposes **Topics → Concepts for that
  Chapter**, seeing the Topics and Concepts the Chapter already has, so it can put new Concepts
  into existing Topics and recognize Concepts that already exist.
- **Course** (no `chapter_id`), for users who don't define Chapters. The AI proposes
  **Chapters → Topics → Concepts** from material **not filed under any Chapter**.

### Only new material, by default

Without `document_ids`, a generation sends the scope's `READY` documents whose `analyzed_at` is
`null`: what was added or moved since the last applied proposal. Applying marks the documents
that were sent in full as analyzed. So the AI never re-reads the whole Chapter:

| Change by the user | What happens |
|---|---|
| Adds material to a Chapter | Generate for the Chapter: only the new document is analyzed and merged into the existing Topics/Concepts |
| Replaces material with a revised edition | Delete the old document (its Concepts get `needs_source_review` if nothing else supports them), upload the new one, generate: Concepts it still teaches are re-linked and the flag clears; what is new is proposed as new |
| Deletes material | Its passages go; Concepts left with no source are flagged `needs_source_review`, never deleted automatically |
| Wants a document analyzed again | Pass it in `document_ids` |

Generation is not started automatically on upload: each run costs an AI call, and a user
uploading three PDFs in a row should get one proposal, not three. The app starts it when the
user asks (or right after uploads finish, if the iOS flow chooses to).

### Request and statuses

Body, all optional: `{"chapter_id": uuid, "document_ids": [uuid, ...]}`. Explicit documents
must be in this Course (404), `READY` (409 `documents_not_ready`), and in the Chapter when one
is given (409 `documents_not_in_chapter`); `details.document_ids` lists the offenders.

| Generate response | When |
|---|---|
| 202 | accepted, `status: "GENERATING"` |
| 404 | the Chapter or a document isn't this Course's |
| 409 `details.reason: "no_source_material"` | no `READY` material with text in scope |
| 409 `details.reason: "no_new_material"` | everything in scope is already analyzed |
| 409 `details.proposal_id` | a generation is already running for this Course |
| 503 `ai_not_configured` | `AI_PROVIDER` is empty |

Poll `GET /curriculum-proposals/{id}` until the status is one of:

| Status | Meaning |
|---|---|
| `READY` | the proposal is in `topics` (Chapter scope) or `chapters` (Course scope) |
| `INSUFFICIENT_CONTEXT` | the material had nothing to build from, or nothing the AI proposed could be tied to it (§19). Not an error. |
| `FAILED` | every configured AI provider was unreachable or kept answering invalid output; `error_message` says why |
| `APPLIED` | the user applied it |

**`CurriculumProposalRead`**: `id, course_id, chapter_id, status, error_message, chapters,
topics, document_ids, passages_used, passages_total, dropped_concepts, ai_provider, ai_model,
ai_model_version, prompt_version, created_at, updated_at, applied_at`.

- A topic is `{title, description, existing_topic_id, concepts}`; a concept is `{title,
  description, existing_concept_id, sources: [{chunk_id, document_id, document_name,
  page_number, section}]}`. The same source shape is used everywhere (Learning Item reference,
  LEARN introduction).
  Open a source with `GET /documents/{document_id}/chunks/{chunk_id}`.
- `existing_topic_id` / `existing_concept_id` (Chapter scope only) mean "goes into this existing
  Topic" / "the new passages also teach this existing Concept". They are shown with the current
  title, and become `null` if the Topic/Concept was deleted since.
- **Every proposed Concept cites at least one passage that was actually sent.** Other citations
  are removed; Concepts left with none are dropped and counted in `dropped_concepts`. References
  to existing Topics/Concepts the AI wasn't shown are treated as new.
- `passages_used < passages_total`: the material exceeded `AI_MAX_CONTEXT_CHARS`; only the
  documents in `document_ids` were sent in full and get marked analyzed on apply.
- `ai_provider` is the provider that actually answered, which is a fallback when the primary
  was down (see AI.md).

### Apply

Chapter proposal: send `topics`. Course proposal: send `chapters`. Exactly one (422 otherwise).

```json
{"topics": [{"title": "...", "description": "", "existing_topic_id": null,
  "concepts": [{"title": "...", "description": "", "existing_concept_id": null,
                "source_chunk_ids": ["<chunk uuid>"]}]}]}
```

- Rename, reject, reorder, merge, split, move and delete (spec §20) are expressed by editing this
  tree before sending it. Concepts the user adds by hand can have no sources.
- `existing_topic_id`: the concepts are added to that Topic, after its current ones; its
  title/description are unchanged. `existing_concept_id`: the sources are linked to that
  Concept, and its `needs_source_review` clears; no new Concept is created. Both must belong to
  the proposal's Chapter (404 otherwise, whether they belong elsewhere or don't exist).
- New Topics go after the Chapter's existing ones; new Chapters after the Course's.
- At least 1 item; at most 2000 concepts per apply; titles 1–200, descriptions ≤2000.
- Only a `READY` proposal can be applied (409, `details.status`), and only once.
- A `source_chunk_id` that isn't a passage of this Course is left out silently, so the answer
  reveals nothing about other Courses.
- Returns `201` with the Course's full outline (as `GET /courses/{id}/outline`).

**`GET /concepts/{id}/sources`** returns `[ChunkRead]`, the passages the Concept was derived
from.

## Concept study state (spec §21, §22, §60) — implemented and tested

```
POST   /api/v1/concepts/{concept_id}/mark-studied   # NOT_STUDIED/STUDIED → STUDIED
POST   /api/v1/concepts/{concept_id}/activate       # NOT_STUDIED/STUDIED/ACTIVE/COMPLETED → ACTIVE
POST   /api/v1/concepts/{concept_id}/pause          # ACTIVE → PAUSED
POST   /api/v1/concepts/{concept_id}/resume         # PAUSED → ACTIVE
POST   /api/v1/concepts/{concept_id}/deactivate     # ACTIVE/PAUSED → STUDIED
POST   /api/v1/concepts/{concept_id}/complete       # any → COMPLETED
```

Any other starting state returns 409 `invalid_state_transition` with
`details: {"current_state": ..., "action": ...}`. Repeating a transition into the state you're
already in succeeds (idempotent) where the table allows it. The full matrix is pinned by
`backend/tests/test_study_state.py`.

`ConceptRead.item_generation_status` / `item_generation_error` report Learning Item
generation (see below).

`ConceptRead.needs_source_review` is true when the material a Concept came from was deleted and
no passage supports it any more. The user keeps it (`PATCH {"needs_source_review": false}`),
edits it, or deletes it; re-linking revised material clears it.

`ConceptRead.is_reviewable` is true only when the Concept is `ACTIVE` **and** no Topic, Chapter
or Course above it is paused. This is what normal review will use (spec §50).

## Pausing whole sections (spec §56) — implemented and tested

```
POST   /api/v1/courses/{course_id}/pause      POST   /api/v1/courses/{course_id}/resume
POST   /api/v1/chapters/{chapter_id}/pause    POST   /api/v1/chapters/{chapter_id}/resume
POST   /api/v1/topics/{topic_id}/pause        POST   /api/v1/topics/{topic_id}/resume
```

These set a `paused` flag on the section (returned in `CourseRead`/`ChapterRead`/`TopicRead`)
and are idempotent. They do **not** rewrite the study state of the Concepts inside. Resuming a
section therefore leaves a Concept the user paused individually still paused ("unpause restores
their previous state").

## Learning Items and questions (spec §24-29) — implemented and tested

```
POST   /api/v1/concepts/{concept_id}/learning-items/generate   # 202; background
GET    /api/v1/concepts/{concept_id}/learning-items
POST   /api/v1/concepts/{concept_id}/learning-items            # write one by hand → 201
GET    /api/v1/learning-items/{item_id}
PATCH  /api/v1/learning-items/{item_id}                        # content only
DELETE /api/v1/learning-items/{item_id}                        # deletes history too
POST   /api/v1/learning-items/{item_id}/train                  # into spaced repetition
POST   /api/v1/learning-items/{item_id}/untrain                # out of it; keeps everything
POST   /api/v1/learning-items/{item_id}/pause | /resume
POST   /api/v1/learning-items/{item_id}/questions              # another formulation → 201
POST   /api/v1/learning-items/{item_id}/questions/generate     # AI formulations → 201 [QuestionRead]
GET    /api/v1/learning-items/{item_id}/sources                # "View source"
GET    /api/v1/learning-items/{item_id}/reviews                # scheduling history
```

- **Generation starts on activation.** `POST /concepts/{id}/activate` on a Concept that has
  source passages and no Learning Items starts generating them in the background:
  `ConceptRead.item_generation_status` goes `GENERATING` → `READY` | `INSUFFICIENT_CONTEXT` |
  `FAILED` (with `item_generation_error`). Activation never fails because of AI.
- **AI question generation** (`questions/generate`, body `{count: 1-5 = 3, question_types?:
  [QuestionType]}`, default types EXPLANATION, APPLICATION, SCENARIO): synchronous. The AI gets
  the item's objective, reference answer, essential points, existing questions and the item's
  own passages only, and writes new formulations of the same knowledge. They share the item's
  memory state, duplicates of existing wording are skipped, and provider/model/prompt version
  are stored on each. Returns only the new ones (possibly `[]`). 409 `no_sources` /
  `insufficient_context`; 503 `ai_not_configured` / `ai_unavailable` /
  `free_capacity_exhausted`; 502 `ai_invalid_output`.
- Explicit `generate`: 409 `items_exist`, `no_source_material` (a hand-made Concept with no
  passages: write items by hand), `generation_running`; 503 `ai_not_configured`.
- **`LearningItemRead`**: `id, concept_id, topic_id, chapter_id, course_id, title, objective,
  expected_knowledge, essential_points, role, in_training, difficulty, order, paused,
  review_state, questions, ai_provider, ai_model, prompt_version, created_at, updated_at`.
  - `role` (what the content is, suggested by the AI): `CORE_TRAINABLE`,
    `SUPPORTING_TRAINABLE`, `COMMON_TRAP`, `INFORMATIONAL`, `REFERENCE`, `OPTIONAL_EXTENSION`.
  - `in_training` (whether it's drilled, the user's choice): starts true for the first three
    roles when the item has a question. `train` needs at least one question (409
    `no_questions`). `untrain` keeps sources, questions, memory state and history.
  - `review_state` (read-only, owned by the SchedulingPolicy): `state` (NEW, LEARNING, REVIEW,
    RELEARNING, MASTERED), `level`, `due_at`, `last_reviewed_at`, `review_count`,
    `successful_review_count`, `failed_review_count`, `lapse_count`, `hard_count`,
    `marked_hard`. Items start `NEW`: a LEARN session encodes them.
  - `questions`: `[{id, question_type, text, times_asked, last_asked_at}]`. All formulations of
    an item share its one memory state.
- Generated items each cite at least one of the Concept's passages (otherwise dropped).

## Managing questions — implemented and tested

```
GET    /api/v1/courses/{course_id}/learning-items        # every item + questions, course order
POST   /api/v1/courses/{course_id}/learning-items/bulk   # many items at once (all or nothing)
PATCH  /api/v1/questions/{question_id}                   # {"text"?, "question_type"?}
DELETE /api/v1/questions/{question_id}                   # 409 last_question for the only one
```

Bulk body: `{item_ids (1-500), action: delete | pause | resume | move, target_concept_id? |
target_topic_id?, delete_emptied_concepts (default true)}` → `{affected, created_concepts,
deleted_concepts}`.

- Every id must be one of this Course's items, and a destination must be in the Course: 404
  otherwise, and nothing changes.
- `move` needs exactly one destination (422 `move_target`):
  - **into a concept**: the items join it, after its own; the concept gains their source
    passages;
  - **into a topic**: each item keeps a concept of its own. A concept whose items are all
    selected moves as a whole; from a partly selected one, the selected items move into a new
    concept with the same title and study state.
- Moving never changes an item's memory state or history. In a concept that isn't ACTIVE the
  item isn't reviewed until the concept is.
- `delete_emptied_concepts`: concepts left with no item by the request are deleted too.
- `pause` / `resume` go through the SchedulingPolicy, like the single-item endpoints.
- Titles and descriptions of courses, chapters, topics and concepts are edited with their
  existing `PATCH` endpoints ("Rename" on each page of the web client).

## Review sessions (spec §42, §49-51, §83-86) — implemented and tested

```
POST   /api/v1/courses/{course_id}/review-sessions    # builds and stores the pool → 201
GET    /api/v1/review-sessions/{session_id}
GET    /api/v1/review-sessions/{session_id}/next      # the current card
POST   /api/v1/review-sessions/{session_id}/answers   # answer → evaluation → outcome → schedule
POST   /api/v1/review-sessions/{session_id}/skip
POST   /api/v1/review-sessions/{session_id}/end
GET    /api/v1/answers/{answer_id}                    # with every evaluation attempt
POST   /api/v1/answers/{answer_id}/evaluate           # retry after a failed attempt
POST   /api/v1/answers/{answer_id}/override           # the user's own grade
POST   /api/v1/review-sessions/{session_id}/hint      # reveal the current question's hint
GET    /api/v1/concepts/{concept_id}/consolidation    # what "I have studied this concept" would do
POST   /api/v1/concepts/{concept_id}/consolidation    # start or resume a consolidation batch
```

### Intent decides what an answer may change

| `intent` | Pool | Selection modes (first = default) | Moves the schedule |
|---|---|---|---|
| `LEARN` | NEW items: introduce, then first retrieval | `NEW`, `SELECTED` | yes: success initializes it; AGAIN keeps the item NEW and asks it again at the end (≤3 times) |
| `SCHEDULED_REVIEW` | encoded items due now, most overdue first | `DUE` | yes |
| `PRACTICE` | encoded items | `COURSE_ORDER`, `RANDOM`, `WEAK`, `RECENTLY_FAILED` (7 days), `MARKED_HARD`, `SELECTED` | **no**, unless created with `update_schedule: true` |
| `CONSOLIDATION` | NEW items of one Concept, each three times in a row; created only by `POST /concepts/{id}/consolidation` (the generic endpoint answers 422 `use_concept_consolidation`) | `CONSOLIDATION` | only each item's last round, as an encoding (SCHEDULING.md §4a) |
| `EXAM` | — | — | 422 `exam_not_available` (Phase 15) |

Create body: `{intent, selection_mode?, chapter_id?, topic_id?, concept_ids?,
learning_item_ids? (SELECTED), limit? (1-100, default 20), update_schedule? (PRACTICE only)}`.
Only items that are in training, with a question, not paused, whose Concept is ACTIVE and whose
Topic/Chapter/Course aren't paused, in this Course. Nothing qualifies → 409 `empty_pool`. Scope
ids of another Course → 404; selected items of another Course are simply not there.

**`SessionRead`**: `id, course_id, intent, selection_mode, affects_schedule, chapter_id,
topic_id, concept_ids, total, position, xp_earned, started_at, ended_at`.

**`GET /next`** → `{session, done, card}`. `card`: `learning_item_id, concept_id,
concept_title, question {id, question_type, text}, introduction (LEARN only: title,
objective, expected_knowledge, essential_points, sources), pending_answer_id, round,
rounds_total (CONSOLIDATION: "Round 2 of 3"), potential_xp {eligible, ordinal, xp,
xp_with_hint}, hint {available, revealed, text}`. The same card comes back until it has an
outcome or is skipped. Wording rotates across sessions (least asked formulation first).

### Consolidation ("I have studied this concept")

- `GET /concepts/{id}/consolidation` → `{concept_id, concept_active, unfinished (SessionRead |
  null), unfinished_items, new_items, batch_items, rounds_per_item, answers_in_batch,
  remaining_after_batch}`: shown before starting.
- `POST /concepts/{id}/consolidation` → `SessionRead`: resumes this Concept's unfinished batch,
  or starts the next one (≤5 NEW items × 3 rounds). 409 `nothing_to_consolidate` (with
  `concept_active`) when nothing is waiting. The session is then answered with the usual
  endpoints; `POST /end` is optional (leaving without it keeps the batch resumable).

### Hints

`POST /review-sessions/{id}/hint` → `{available, revealed, text}`. Stored before it is returned:
the answer to that question is `hint_used` and earns half XP, whatever the client does next.
Asking again returns the same hint. 409 `hint_unavailable` (no cue can be cut from the reference,
or a LEARN session) and 409 `answer_pending` (already answered) record nothing.

### Answering

`POST /answers` body: `{question_formulation_id, text (1-10000), method: TEXT|VOICE}`. The
question must be the current card's (409 `not_current_question`); an earlier answer to it
without an outcome must be resolved first (409 `answer_pending`); a finished session → 409.

The answer is stored before the AI is called, then:

1. **AI evaluation** (evidence only: `classification` CORRECT / PARTIALLY_CORRECT /
   MISCONCEPTION / WRONG / UNCERTAIN, `correctness`, `completeness`,
   `conceptual_understanding`, `precision`, `confidence`, `correct_points`, `missing_points`,
   `misconceptions`, `source_corrections`, `context_sufficient`, `feedback`), grounded in the
   item's own passages. **It has no outcome field** (see SCHEDULING.md §3b).
2. **ReviewOutcomeResolver** (deterministic, versioned) → `resolved_outcome` AGAIN / HARD /
   GOOD, or `null` when it can't decide.
3. `final_outcome` = override if any, else resolved → **SchedulingPolicy** if the session may
   move the schedule → a Review history row.

Always **201** once stored. **`AnswerResult`**: `answer_id, learning_item_id,
question_formulation_id, intent, text, evaluation (latest attempt), resolved_outcome,
resolver_version, override_outcome, final_outcome, needs_self_grade, schedule, reference,
session, consolidation_round, hint_used, xp`.

- `xp` (null when the attempt isn't XP-eligible or has no outcome yet): `reason (INITIAL |
  SCHEDULED_REVIEW), correct, ordinal, base_xp, hint_used, xp`. Decided once, when the answer is
  first finalized, from the AI classification and the resolver's outcome; a self-grade or a
  later override never creates or removes XP (docs/XP_AND_ACTIVITY.md).

- `schedule` (null if nothing moved): `previous_state, previous_level, previous_due_at,
  next_state, next_level, next_due_at, lateness_seconds`.
- `reference`: `expected_knowledge, essential_points, sources` for the feedback screen.
- `needs_self_grade: true` when there's no outcome: evaluation `FAILED` (provider down or
  invalid output), `NOT_CONFIGURED` (AI off), or completed but inconclusive (insufficient
  context, UNCERTAIN, low confidence, self-contradicting). Then: retry
  (`POST /answers/{id}/evaluate`, only after FAILED/NOT_CONFIGURED; else 409
  `evaluation_inconclusive`), grade it yourself (`override`), or `skip`.

### Overrides (audit trail)

`POST /answers/{id}/override` `{outcome: AGAIN|HARD|GOOD|EASY, note?}`:

- The AI evaluation and `resolved_outcome` are never changed; `override_outcome`,
  `override_note`, `overridden_at` and `final_outcome` record the user's grade.
- No outcome yet: the override is applied like a resolved outcome.
- Already scheduled: the transition is **replayed** from the stored previous state, at the
  original review time, with the new outcome; the old history row is marked `superseded` and the
  new one points to it (`supersedes_review_id`). Only while it's the item's latest review:
  otherwise 409 `later_reviews_exist`.
- In a practice session (schedule untouched) it only records the grade.

**`ReviewRead`** (history): `id, learning_item_id, answer_id, intent, outcome, previous_state,
previous_level, previous_due_at, next_state, next_level, next_due_at, reviewed_at,
lateness_seconds, scheduling_policy, scheduling_policy_version, supersedes_review_id,
superseded`.

## Exam Mode (spec §57)

```
POST   /api/v1/courses/{course_id}/exams
GET    /api/v1/exams/{exam_id}
POST   /api/v1/exams/{exam_id}/answers
POST   /api/v1/exams/{exam_id}/submit         # triggers end-of-exam evaluation
```

## Progress and review load (spec §52-54, §67-68) — implemented and tested

```
GET    /api/v1/courses/{course_id}/progress?utc_offset_minutes=120
GET    /api/v1/courses/{course_id}/review-load?utc_offset_minutes=120
GET    /api/v1/home?utc_offset_minutes=120
```

- **Progress**: `{course_id, curriculum, memory, review_load, chapters: [{id, title,
  curriculum, memory, topics: [{…, concepts: [{id, title, study_state, memory,
  misconceptions}]}]}]}`.
  - `curriculum` (how far through the material): `concepts, not_studied, studied, active,
    paused, completed`.
  - `memory` (how well it's retained, trained items only): `items_trained, new, learning,
    review, relearning, mastered, marked_hard, mastery`. `mastery` is an **estimate** (0-1, from
    the SchedulingPolicy; null when nothing is trained), never a measurement.
  - The two are never merged into one score.
- **Review load**: `due_now, overdue, later_today, tomorrow, next_7_days, later, new_to_learn`,
  by the user's calendar day (`utc_offset_minutes`, default 0), counting only items that can be
  reviewed now. `overdue` is the part of `due_now` that was due before the start of today.
- **Home** (`GET /home`): `{totals: ReviewLoad, courses: [{course_id, title, review_load,
  active_concepts, mastery, weak_concepts: [{id, title, lapses, marked_hard}] (≤3)}]}` for the
  signed-in user's own Courses. `totals` sums the review loads; nothing else is combined across
  Courses.
- Analytics beyond this (spec §13 phase) are not built.

## Dashboard, activity and course summaries — implemented and tested

```
GET    /api/v1/dashboard?weeks=12           # everything the dashboard shows, one as_of
GET    /api/v1/activity?weeks=52            # the longer activity calendar
GET    /api/v1/courses/{course_id}/summary  # one course card (course header)
```

- **`Dashboard`**: `as_of, timezone, today, next_step, courses, xp {total, today},
  streak {current, today_complete, last_7_days [{date, active}]}, goal {target, done, unit},
  planner {as_of, horizons [{key: now|1h|4h|1d|3d|7d, due_by, items}]}, activity`.
- **`CourseCard`**: `id, title, description, language, paused, created_at, last_studied_at,
  concepts_total, concepts_studied, items_trained, items_introduced, due_now, new_ready,
  learn {kind: resume|study|activate|setup|none, concept, session_id}`.
- **`NextStep`**: `kind` (`resume_consolidation`, `review`, `learn`, `activate`,
  `setup_course`, `create_course`, `all_caught_up`), plus the course, concept, session and counts
  it refers to. Priority in docs/XP_AND_ACTIVITY.md §6.
- **`Activity`**: `start` (a Monday), `end` (Sunday of this week), `today`, `days [{date,
  attempts, xp}]` (only days with activity).
- Days are the user's local calendar days (`users.timezone`); due counts use the same
  eligibility as review sessions. All of it is the signed-in user's own data only.

## Explicit cross-course endpoints (future, spec §11)

Must be a distinct, clearly-named path — never implied by omitting `course_id` from a normal
endpoint.

```
POST   /api/v1/analysis/cross-course     # body explicitly lists course_ids; response is labeled
                                          # as cross-course
```

## Auth

```
POST   /api/v1/auth/register    # {"email", "password", "timezone"?} → 201 UserRead; 409 if taken
POST   /api/v1/auth/login       # {"email", "password"} (JSON) → {"access_token", "token_type"}
GET    /api/v1/auth/me          # current user: {"id", "email", "timezone", "daily_goal"}
PATCH  /api/v1/auth/me          # {"timezone"?, "daily_goal"? (1-500)}
POST   /api/v1/auth/password-reset/request   # {"email"} → 202, same answer for any email
POST   /api/v1/auth/password-reset/confirm   # {"token", "new_password"} → 204
POST   /api/v1/auth/change-password          # {"current_password", "new_password"} → Token
POST   /api/v1/auth/refresh     # not yet implemented
POST   /api/v1/auth/logout      # not yet implemented (sign-out is client-side)
```

- Emails are case- and whitespace-insensitive (stored lowercased).
- Passwords: 12–128 characters at registration; whitespace is significant.
- Wrong password and unknown email return the identical 401, in equal time.
- Access tokens: HS256 JWT, 60-minute expiry by default (`AUTH_ACCESS_TOKEN_EXPIRE_MINUTES`).
- **Forgot password.** `request` always answers 202 with the same message, so it can't reveal
  who is registered. For a real account it emails a link (`PUBLIC_APP_URL/reset-password?token=`)
  that works once, for `PASSWORD_RESET_TTL_MINUTES` (30); a newer link retires older ones; at
  most 3 per account per hour. Only a SHA-256 of the token is stored. `confirm` with a used,
  expired or unknown token → 422 `invalid_reset_token`.
- **Every password change** (reset, change, or the admin script `scripts/set_password.py`)
  increments `users.token_version`, which every access token carries: all existing sessions on
  every device end. `change-password` (422 `wrong_password` if the current one is wrong) returns
  a fresh token for the device that asked.
- Passwords are never stored or readable: only an Argon2id hash. An administrator can set a new
  one (`scripts/set_password.py --email …`), never read the old one.
- `timezone` is an IANA name ("Europe/Rome"; 422 otherwise), UTC when omitted. It decides the
  user's calendar day for streaks, goal, XP today and activity; changing it applies from then on.

See DEVELOPMENT.md "Decisions made autonomously → Auth" for the reasoning behind each rule.
