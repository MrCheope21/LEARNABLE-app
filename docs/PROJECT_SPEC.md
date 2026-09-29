# PROJECT SPECIFICATION — Adaptive AI Learning Platform for iPhone

> Model-Agnostic Coding Agent Version. This document is the authoritative, verbatim-organized
> product specification. It is the source of truth for architecture and product decisions,
> independent of which coding agent (Claude, Kimi, DeepSeek, GLM, Codex, OpenCode, etc.) is used
> to implement it, and independent of which runtime AI model (Qwen, DeepSeek, Kimi, GLM, managed
> or self-hosted) powers the finished application.

## 0. Product

Build a production-quality iPhone application for adaptive learning. The application transforms
a user's study material into a structured learning curriculum and then uses active recall, AI
evaluation and spaced repetition to help the user retain knowledge over time. Inspired by useful
learning principles found in structured learning products such as Chessable, but must be an
original product with original code, architecture, branding and UI.

The application is **NOT**:
- a generic chatbot
- a simple PDF summarizer
- a simple flashcard generator
- a flat flashcard database
- an AI chat application

The application **IS**: a structured knowledge curriculum combined with an adaptive memory engine.

## 1. Core Product Idea

The user creates or imports a Course. Each Course is isolated from every other Course.

Course hierarchy:

```
COURSE → CHAPTER → TOPIC → CONCEPT → LEARNING ITEM → QUESTION FORMULATION
```

Each Course also has its own source repository:

```
COURSE → KNOWLEDGE REPOSITORY → DOCUMENT → DOCUMENT CHUNK → SOURCE PASSAGE
```

The user controls which Concepts become active for study. The application then:

1. Creates or imports the curriculum.
2. Extracts Concepts from source material.
3. Lets the user decide what they have studied.
4. Activates selected Concepts.
5. Generates Learning Items.
6. Generates multiple ways to test those Learning Items.
7. Asks the user questions.
8. Accepts written or spoken answers.
9. Uses an AI model to evaluate the response.
10. Provides feedback.
11. Updates the Learning Item's memory state.
12. Calculates the next review through a scheduling engine.
13. Builds Concept-level mastery estimates.
14. Repeats this process over days, weeks and months.

## 2. Fundamental Principle

The system must separate these concerns in both code and data models:

| Concern | Concept |
|---|---|
| What the user wants to learn | Curriculum |
| Where the knowledge comes from | Source Repository |
| What the underlying knowledge unit is | Concept |
| What is actually tested | Learning Item |
| How it is asked | Question Formulation |
| Whether it is currently eligible for review | Study / Activation State |
| How well the user answered | AI Evaluation |
| When it should be reviewed again | Scheduling Policy |
| How well the broader concept appears to be mastered | Mastery Estimate |

## 3. Coding Agent vs Runtime AI

**Critical:** the AI used to build this application is NOT necessarily the AI used inside the
finished application.

- Coding agent may be: Claude, Kimi, DeepSeek, GLM, or another model.
- Application runtime AI may be: Qwen, DeepSeek, Kimi, GLM, another open-weight model, a managed
  inference service, or a self-hosted model.

`coding_agent != runtime_AI`. Never architect the application around the identity of the coding
model. Do not integrate Claude-, Kimi-, DeepSeek-, or GLM-specific assumptions into the
application. The finished product must work independently of the coding agent that built it.

## 4. Repository-First Development

Before writing code: inspect the entire repository, identify existing iOS/backend projects,
architecture docs, dependency management, tests, build scripts, env config, git status,
unfinished work, and what already works. Do not unnecessarily rewrite working code.

Maintain: `/docs/PROJECT_SPEC.md`, `/docs/ARCHITECTURE.md`, `/docs/DATA_MODEL.md`,
`/docs/API.md`, `/docs/AI.md`, `/docs/SCHEDULING.md`, `/docs/DEVELOPMENT.md`.

## 5. Autonomous Engineering Behavior

Work as an autonomous senior engineer. Per task: inspect relevant code, understand dependencies,
make the smallest coherent implementation, run tests, build affected components, fix errors,
re-run tests, update docs when necessary. Actually implement — do not merely describe code that
should exist, do not stop at skeletons for functional requirements, do not leave fake TODOs in
core functionality. Do not ask unnecessary clarification questions; for non-critical ambiguity,
choose the simplest robust implementation and document the decision. Only stop for destructive,
irreversible, or financially significant operations.

## 6. Target Platform

iPhone / iOS. Swift, SwiftUI, Swift Concurrency (async/await), modern Apple APIs, accessibility
(Dynamic Type, VoiceOver, Dark Mode). Clear separation of Presentation / Domain / Data /
Networking / Persistence / Speech / Review / Analytics. MVVM or equivalent testable architecture.
No business logic directly in SwiftUI Views.

## 7. Backend

Python, FastAPI, PostgreSQL, object storage for documents, optional pgvector for semantic
retrieval, background jobs for expensive processing.

```
/backend
  /app
    /api
    /auth
    /models
    /schemas
    /services
      /courses /documents /retrieval /learning /questions
      /evaluation /scheduling /mastery /analytics
    /ai
    /prompts
    /storage
  /tests
```

Keep backend services modular.

## 8. Database

PostgreSQL, UUID identifiers.

Core entities: User, Course, CourseSettings, Chapter, Topic, Concept, Document, DocumentChunk,
SourceReference, LearningItem, QuestionFormulation, StudyState, ReviewState, Review, Answer,
Evaluation, MasteryState, ReviewSession, ExamSession, ExamQuestion, PromptVersion, ModelVersion.

Future entities: CourseTemplate, CourseInstance, CoursePackage, CourseImport, CourseExport.

Do not collapse all of these into a generic "Card" table.

## 9. Course

Highest-level user-owned learning environment (e.g. "Dottore Commercialista", "Macroeconomia",
"Diritto Commerciale", "Bilancio Bancario", "Corporate Finance", "Medical Pathology",
"Professional Certification"). Each Course contains: title, description, language, chapters,
topics, concepts, source repository, study state, learning data, review data, progress,
analytics, settings.

## 10. Course Isolation

Fundamental security and product requirement. Course A must not automatically retrieve data from
Course B. Applies to: database queries, document retrieval, vector/semantic search, AI prompts,
question generation, answer evaluation, review sessions, analytics, notifications, mastery.
Every Course-specific request must carry a validated Course scope; the server must verify
ownership/access. Never trust a `course_id` merely because the client sent it.

## 11. Cross-Course Operations

Global cross-course retrieval is forbidden by default. Cross-course analysis may exist as an
explicit future feature (e.g. "Compare liquidity in my Corporate Finance and Banking courses"),
and when used must: explicitly identify selected Courses, explicitly construct cross-course
retrieval context, and clearly communicate that the operation is cross-course.

## 12. Course Hierarchy

```
COURSE → CHAPTER → TOPIC → CONCEPT → LEARNING ITEM → QUESTION FORMULATION
```

Example:

```
COURSE: Dottore Commercialista
  CHAPTER: Diritto commerciale
    TOPIC: La figura dell'imprenditore
      CONCEPTS: Nozione di imprenditore, Imprenditore commerciale, Imprenditore agricolo,
                Piccolo imprenditore, Impresa familiare, Registro delle imprese
  CHAPTER: Diritto bancario
    TOPIC: Contratti bancari
      CONCEPTS: Deposito bancario, Apertura di credito, Anticipazione bancaria, Mutuo
  CHAPTER: Bilancio bancario
    TOPIC: Stato patrimoniale attivo
      CONCEPTS: Cassa, Crediti verso banche, Crediti verso clientela, Attività finanziarie
```

## 13. Chapter

Major subject area. Fields: id, course_id, title, description, order, topics, progress.

## 14. Topic

Coherent family of Concepts. Fields: id, chapter_id, title, description, order, concepts.

## 15. Concept

Basic conceptual knowledge unit. Independently meaningful. A Concept is **NOT** equal to one
flashcard — it can contain many Learning Items.

Example — Concept "Imprenditore commerciale" → Learning Items: Definition, Characteristics,
Relevant activities, Difference from agricultural entrepreneur, Practical scenario, Oral
explanation.

## 16. Knowledge Repository

Every Course has a private Knowledge Repository. Initial file types: PDF, TXT, Markdown, DOCX,
PPTX, images/scans. Each document retains: filename, MIME type, size, creation date, import date,
hash, source type, storage location.

## 17. Document Processing

```
UPLOAD → EXTRACT → CLEAN → CHUNK → INDEX → ASSOCIATE → RETRIEVE
```

Preserve where possible: page number, section, heading, paragraph, source position. Never destroy
source identity.

## 18. Source Chain

Every generated Learning Item must be traceable:

```
Learning Item → Concept → Topic → Chapter → Course → Document → Document Chunk → Source Passage/Page
```

Every question should be able to explain "Where did this come from?" User can open "View source"
and see the relevant source passage.

## 19. Source Material as Authority

The user's Course repository is the primary source of truth for Course-specific learning. The AI
must not silently inject external knowledge into Course questions or corrections. If external
knowledge mode is not explicitly enabled: generation must be grounded in Course material,
evaluation must prioritize Course material, feedback should reference source material. If
retrieved source material is insufficient, return `INSUFFICIENT_CONTEXT`. Never hallucinate
source evidence.

## 20. AI-Generated Curriculum

After importing source material, AI may propose Course → Chapters → Topics → Concepts, plus
duplicates/prerequisites/relationships/important Concepts/suggested Learning Items. AI **must
not** automatically activate all Concepts. User must be able to: accept, reject, rename, merge,
split, reorder, move, delete, activate.

## 21. User Activation

One of the most important business rules. A Concept may exist in the Course but remain inactive.
Only after the user marks it studied and activates it does it enter the active learning system.
Until activation: no normal review, no SRS scheduling, no daily review, no automatic testing.

## 22. Study States

`NOT_STUDIED`, `STUDIED`, `ACTIVE`, `PAUSED`, `COMPLETED`.

- NOT_STUDIED: user has not indicated the Concept has been studied.
- STUDIED: user has studied/read the Concept.
- ACTIVE: Concept may generate Learning Items and enter review.
- PAUSED: previously active, temporarily excluded.
- COMPLETED: user marks the curriculum portion as completed.

Study State does **NOT** represent memory strength.

## 23. Memory State

Belongs to Learning Items. Suggested states: `NEW`, `LEARNING`, `REVIEW`, `RELEARNING`,
`MASTERED`. Generated from review history, outcomes, scheduling policy, intervals, retention
behavior.

## 24. Trainable vs Informational Content

Each Concept can contain Informational content (helps understand) and Trainable content (user
wants to actively retain). Only trainable Learning Items participate in spaced repetition. AI may
recommend trainable content; user controls activation.

## 25. Learning Item

Atomic review unit. Fields: id, course_id, chapter_id, topic_id, concept_id, title, objective,
expected_knowledge, essential_points, source_references, question_formulations, difficulty,
study state, review state, created_at, updated_at. Each Learning Item has its own SRS state.

## 26. Independent Scheduling

Two Learning Items belonging to the same Concept may have completely different memory states
(e.g. Definition → Level 6, Difference vs agricultural → Level 2, Scenario → Level 1). Do **not**
schedule the entire Concept as one card. Do **not** reset all Learning Items because one was
answered incorrectly.

## 27. Question Formulations

A Learning Item may have multiple equivalent question formulations (different phrasings of the
same underlying objective). These formulations share **ONE** SRS state. Prevents memorization of
wording instead of knowledge.

## 28. Question Types

Recall, Definition, Explanation, Why/how, Comparison, Cause/effect, Application, Scenario,
Calculation, Classification, Teach-back, Oral exam, Counterexample, Edge case, Concept
connection. Model chooses appropriate types based on the Learning Item.

## 29. Question Variation

May vary: wording, structure, scenario, example, context, response format, difficulty,
oral/written format. Question variation **must not** change the underlying Learning Objective. No
novelty for novelty's sake.

## 30. Answer Methods

**TEXT**: editable answer, submit, evaluate.
**VOICE**: record, stop, speech-to-text, display transcript, allow correction, submit final
transcript, evaluate.

MVP evaluates semantic answer content, not speech fluency.

## 31. Speech

Use native Apple speech capabilities where appropriate via a `SpeechTranscriptionService`
abstraction. Future: alternative/on-device transcription providers. Do not hard-code the voice
system into the review engine.

## 32. AI Provider Architecture

Create `AIProvider`. Required operations: `generateCurriculum`, `extractConcepts`,
`generateLearningItems`, `generateQuestion`, `generateQuestionVariations`, `evaluateAnswer`,
`generateFeedback`, `generateFollowUpQuestion`, `generateExam`.

The iOS client must **NOT** directly call an LLM provider.

```
iPhone → HTTPS → Backend → AIProvider → OpenAI-compatible or equivalent model API → Runtime AI
```

## 33. Runtime AI Providers

Configurable via env: `AI_PROVIDER`, `AI_BASE_URL`, `AI_API_KEY`, `AI_MODEL`, `AI_TIMEOUT`,
`AI_TEMPERATURE`, `AI_MAX_TOKENS`. Potential providers: Qwen, DeepSeek, Kimi, GLM, other
open-weight models, managed inference providers, self-hosted models. Do not hard-code one
provider. Provider switching must not require business-logic changes.

## 34. Multi-Model Architecture

Future: different models for different operations (fast model for classification/basic
extraction/simple question generation; strong model for difficult evaluation, misconception
detection, nuanced conceptual evaluation). Potential config: `AI_MODEL_EXTRACTION`,
`AI_MODEL_GENERATION`, `AI_MODEL_EVALUATION`, `AI_MODEL_EXAM`. Do not implement multiple models
unnecessarily in MVP, but design the abstraction so it is possible later.

## 35. Coding-Model Independence

The coding agent can be switched without changing: database, Swift code, FastAPI, AIProvider,
scheduling, Course structure, review engine. The repository must contain all essential project
knowledge so a new coding agent can continue by reading the `/docs` files.

## 36. AI Output Format

All machine-consumed AI operations return structured JSON. Do not parse free-form prose for
critical logic. Implement JSON schema validation. If malformed: (1) retry with a constrained
prompt, (2) if still invalid, return a structured error, (3) never crash the application, (4)
never silently guess.

## 37. Answer Evaluation Schema

```json
{
  "correctness": 0.0,
  "completeness": 0.0,
  "conceptual_understanding": 0.0,
  "precision": 0.0,
  "confidence": 0.0,
  "outcome": "AGAIN | HARD | GOOD | EASY",
  "correct_points": [],
  "missing_concepts": [],
  "misconceptions": [],
  "feedback": "",
  "source_corrections": [],
  "context_sufficient": true
}
```

All numerical metrics use 0.0–1.0.

## 38. Answer Evaluation

Evaluate: factual correctness, completeness, conceptual understanding, precision, essential
points, misconceptions. Classifications: `CORRECT`, `PARTIALLY_CORRECT`, `MISCONCEPTION`,
`WRONG`, `UNCERTAIN`. Do not force certainty when evidence is insufficient.

## 39. Semantic Evaluation

Do not use keyword matching as the primary evaluator. Different wording must be recognized as
equivalent when the meaning is equivalent.

## 40. Misconception Tracking

Store important misconceptions against the Concept and Learning Item. Future question generation
may target them. Do not repeatedly ask the exact same question unless pedagogically justified.

## 41. Feedback

Concise, educational, constructive, non-judgmental. Show what was correct, what was missing, and
the approximate next review interval.

## 42. AI vs Scheduler

**Critical rule:** AI does **NOT** decide the next review date. AI evaluates the response;
`SchedulingPolicy` determines the review state and date.

```
User Answer → AI Evaluation → Review Outcome → SchedulingPolicy → Next Review Date
```

## 43. Scheduling Abstraction

Create `SchedulingPolicy` with: `initialize(item)`, `processReview(item, outcome)`,
`calculateNextReview(item)`, `pause(item)`, `resume(item)`.

## 44. Chessable-Inspired Policy

`ChessableStyleSchedulingPolicy` default approximate schedule (must be configuration values, not
scattered across source):

| Level | Interval |
|---|---|
| 1 | 4 hours |
| 2 | 1 day |
| 3 | 3 days |
| 4 | 1 week |
| 5 | 2 weeks |
| 6 | 1 month |
| 7 | 3 months |
| 8 | 6 months |

## 45. Future Scheduling Policies

Architecture must support: `ChessableStyleSchedulingPolicy`, `FSRSPolicy`,
`AdaptiveSchedulingPolicy`, `CustomSchedulingPolicy`. User may eventually select a scheduling
mode.

## 46. Review Outcomes

`AGAIN`, `HARD`, `GOOD`, `EASY`. Scheduling transitions belong exclusively to `SchedulingPolicy`.
GOOD advances per policy; AGAIN returns to an earlier state/short interval; HARD limits
progression; EASY accelerates progression.

## 47. Late Reviews

If overdue: retain historical information, record lateness, do not automatically erase historical
progress. Store `original due_at`, `reviewed_at`, lateness duration. `SchedulingPolicy` determines
the next state.

## 48. Item-Level Review State

Every Learning Item stores: state, level, interval, due_at, last_reviewed_at, review_count,
successful_review_count, failed_review_count, lapse_count, scheduling_policy,
scheduling_policy_version.

## 49. Review Modes

`ADAPTIVE/DUE`, `COURSE ORDER`, `RANDOM`, `WEAK AREAS`, `RECENTLY FAILED`, `NEW ACTIVE`,
`SELECTED`, `EXAM`. Exam mode gives no immediate feedback.

## 50. Review Pool

A Review Session creates a dynamic Review Pool depending on: Course, optional Chapter, optional
Topic, optional Concepts, activation status, pause status, review mode, due date, item priority.
Never include unstudied/inactive/paused items in normal review.

## 51. Study Order vs Review Order

Curriculum order answers "What should I learn next?"; spaced repetition answers "What should I
remember now?" These are different. The app must support studying sequentially while reviewing
adaptively.

## 52. Concept Mastery

Derived metric considering: performance across Learning Items, successful reviews, failures,
long-term stability, question-type diversity, misconceptions, recency, coverage of Concept
dimensions. Never represent this estimate as a scientifically exact memory measurement.

## 53. Coverage Model

Track which dimensions of a Concept have been tested (e.g. Definition → tested, Mechanism →
tested, Application → weak, Comparison → not tested, Oral explanation → not tested). Question
generation can target missing dimensions.

## 54. Higher-Level Progress

Aggregate Learning Items → Concept → Topic → Chapter → Course. Display **Curriculum Progress**
and **Memory/Mastery Progress** separately — do not reduce these into one score.

## 55. Prerequisites

Optional Concept prerequisites, guidance only. Must not automatically activate Concepts.

## 56. Pause

User can pause Learning Item / Concept / Topic / Chapter / Course. Paused items retain history and
do not generate normal review prompts. Unpause restores previous state.

## 57. Exam Mode

User chooses Course/Chapter/Topic/Concepts, number of questions, difficulty, time limit, question
types. During exam: no immediate evaluation, store answers, support text/voice. At the end,
generate correctness, completeness, conceptual understanding, weak areas, misconceptions,
Concepts to review.

## 58. Question Selection

Account for: due state, weak items, previous formulations, question-type diversity, Concept
coverage, difficulty, recent history. Avoid exact wording repetition where useful; never generate
novelty that changes the intended knowledge.

## 59. Follow-Up Questions

If the answer is partially correct, the system may ask a focused follow-up belonging to the same
Concept context.

## 60. User Control

User can create/import Course, edit curriculum, activate/deactivate/pause/resume Concepts,
inspect source, start reviews, choose review mode, answer by text/voice, inspect
feedback/history/progress. AI may recommend; AI does not silently override the user.

## 61. Course Composition

Future architecture must support: duplicate Course/Chapter, copy Topic/Concept/Learning Items,
export/import Course, build personal Course from selected content. When content is copied,
personal review history is **not** automatically copied — published curriculum state and personal
learning state are separate.

## 62. Course Template vs User Instance

Future model:

```
COURSE TEMPLATE (reusable educational content) → USER COURSE INSTANCE (learner-specific
activation, memory, progress)
```

Course Template: structure, source content, Concepts, Learning Items, question templates. User
Course Instance: activation status, personal notes, reviews, memory state, mastery, preferences.
Enables future Course sharing/marketplace.

## 63. UI

Main navigation: Home, Courses, Review, Progress, Settings.

- **Course Dashboard**: course name, curriculum progress, memory progress, due reviews, weak
  areas, Chapters.
- **Chapter View**: Topics, active Concepts, due items, weak areas.
- **Topic View**: Concepts, activation state, mastery, review count, next review.
- **Concept View**: source material, explanation, Learning Items, mastery, weak Learning Items,
  activation controls.

## 64. Home

Today's reviews, overdue reviews, new active items, study time estimate, weak areas, active
Courses.

## 65. Review UI

Simple, focused, distraction-free. Show question, [Write Answer] / [Speak Answer], "Evaluating…",
then result: outcome, what you got right, what was missing, what was incorrect, source, next
review.

## 66. Source View

User can inspect document name, page, section, relevant source passage. Important for AI trust.

## 67. Progress

Active Concepts, estimated mastery, review count, retention trend, weak Concepts, upcoming review
burden, Course/Chapter/Topic progress, review calendar. Separate Curriculum from Memory.

## 68. Review Load

Show future load (today / tomorrow / next 7 days) to help prevent users from activating too much
new content at once.

## 69. Localization

Initial languages: Italian, English. Do not hard-code UI text. Course language is stored; AI
prompts should use the configured Course language.

## 70. Privacy

HTTPS, secure authentication, secure credential storage, server-side API keys, deletion of
documents/account data, controlled logging, minimal AI data transmission, no full document
logging. Design toward EU/GDPR-oriented privacy. Do not claim automatic legal compliance.

## 71. AI Cost Control

Minimize unnecessary model calls: caching, question formulation reuse, pre-generation, batching
where useful, smaller model for simple operations, stronger model for difficult evaluation. Do
not regenerate identical questions unnecessarily.

## 72. Retrieval / RAG

Every retrieval request **must** include course scope and, where appropriate, chapter/topic/
concept. Do not perform global retrieval.

```
User Task → Scope determination → Retriever → Relevant chunks → Prompt construction → AI →
Structured output → Validation
```

## 73. AI Prompt Versioning

Create prompt files, e.g. `concept_extraction_v1`, `curriculum_generation_v1`,
`learning_item_generation_v1`, `question_generation_v1`, `answer_evaluation_v1`,
`question_variation_v1`, `exam_generation_v1`. Store prompt version with generated content and
evaluations.

## 74. Model Version Tracking

Store: provider, model, model version, prompt version, timestamp. Required for later
benchmarking.

## 75. Model Benchmarking

Architect the evaluation layer so runtime models can eventually be benchmarked against a
human-labeled dataset on: correctness classification, completeness, misconception detection,
semantic equivalence, suggested outcome consistency. Do not assume one model is permanently
superior.

## 76. Mock AI

Create `MockAIProvider` supporting deterministic tests. Tests must never require real API access.

## 77. Testing

- **Database**: Course isolation, ownership, hierarchy, deletion, duplication.
- **Learning**: activation, pause, resume, Learning Item creation.
- **AI**: schema validation, malformed response, retries, evaluation, source insufficiency.
- **Scheduling**: correct/incorrect/hard/easy answer, overdue review, independent item
  progression.
- **Review**: due, random, course order, weak, failed, selected.

## 78. Test Fixtures

A. Fully correct answer. B. Correct but incomplete. C. Incorrect. D. Semantically correct with
different wording. E. Misconception. F. Ambiguous answer. G. Correct per external knowledge but
unsupported by Course source. H. Correct answer with irrelevant additional information. I.
Insufficient source context.

## 79. Offline

Offline-capable: view Courses/Concepts/existing Learning Items/review history, access cached
source material, preserve answer drafts. AI operations can require network. Never lose the user's
answer because of a network failure.

## 80. Error Handling

Handle network errors, timeout, model unavailable, malformed AI response, upload failure,
database failure, authentication failure, transcription failure — with structured errors. Never
crash because an LLM returned malformed output.

## 81. Security

Backend is the trusted security boundary; the iOS client is untrusted. Validate server-side: user
identity, Course ownership, permissions, resource ownership, AI requests, file access. Never
expose database password, AI API key, storage credentials, backend secrets.

## 82. API

Example endpoints (versioned):

```
POST   /courses
GET    /courses
GET    /courses/{id}
POST   /courses/{id}/chapters
POST   /chapters/{id}/topics
POST   /topics/{id}/concepts
POST   /courses/{id}/documents
POST   /concepts/{id}/activate
POST   /concepts/{id}/pause
POST   /concepts/{id}/resume
GET    /review/due
POST   /review/sessions
POST   /answers
POST   /answers/{id}/evaluate
GET    /learning-items/{id}
GET    /progress/courses/{id}
GET    /courses/{id}/analytics
```

## 83. Review Session

Fields: id, user_id, course_id, chapter_id, topic_id, concept_ids, mode, start_time, end_time,
selected Learning Items. Must retain enough information to reconstruct how the session was
selected.

## 84. Answer

Fields: id, user_id, learning_item_id, review_session_id, method, text, transcript, optional
audio reference, created_at. Audio retention must be configurable.

## 85. Evaluation

Fields: id, answer_id, correctness, completeness, conceptual_understanding, precision,
confidence, outcome, missing_concepts, misconceptions, feedback, context_sufficient, provider,
model, prompt_version, created_at.

## 86. Review History

Fields: id, learning_item_id, answer_id, previous_state, previous_level, outcome, next_state,
next_level, previous_due_at, next_due_at, reviewed_at, scheduling_policy,
scheduling_policy_version. Makes the scheduler auditable.

## 87. Notifications

Future notifications generated only for active/scheduled Learning Items (e.g. "You have 8
reviews due today"). Do not notify about inactive material.

## 88. Daily Study Strategy

Default session priority: (1) Due reviews, (2) Overdue reviews, (3) Weak areas, (4) Newly active
material. Users may override. Encourage maintaining prior learning over continuously activating
new content.

## 89. Product Design

Premium, academic, calm, intelligent, minimal, modern. Avoid childish UI, generic AI chat
interface, excessive gradients, noisy gamification, unnecessary complexity. Central experience:
"My adaptive personal study coach."

## 90. Gamification

Optional: streak, milestones, completed reviews, daily target. Never more important than
learning.

## 91. Course Import / Export

Future Course Package may contain: Course metadata, Chapters, Topics, Concepts, Learning Items,
Question Formulations, source references, curriculum order. Must **not** include personal review
history, mastery, or private notes unless explicitly requested.

## 92. Course Marketplace-Ready Architecture

Future: `Creator → Course Template → Published Course → User Course Instance → Personal Learning
State`. Not implemented in MVP, but architecture must not prevent it.

## 93. Performance

Review experience should feel responsive: prefetch next question, cache source content,
pre-generate alternative formulations, reuse AI-generated Learning Items, optimize API requests.
Do not block the UI unnecessarily.

## 94. Observability

Structured logs: request_id, user_id, course_id, operation, provider, model, latency, error type.
Do not log full study documents or full private answers by default.

## 95. Configuration

`.env.example` with: `DATABASE_URL`, `AUTH_SECRET`, `AI_PROVIDER`, `AI_BASE_URL`, `AI_API_KEY`,
`AI_MODEL`, `AI_TIMEOUT`, `AI_TEMPERATURE`, `AI_MAX_TOKENS`, `STORAGE_ENDPOINT`,
`STORAGE_BUCKET`, `LOG_LEVEL`. No secrets committed to Git.

## 96. Local Development

Reproducible local dev environment. Recommended: Docker Compose for PostgreSQL, backend, optional
pgvector, optional object storage. Document how iOS connects to local backend.

## 97. CI

Backend: formatting, lint, type checking, tests. iOS: build, unit tests. No core branch should
remain knowingly broken.

## 98. Documentation

Keep synchronized: PROJECT_SPEC.md, ARCHITECTURE.md, DATA_MODEL.md, API.md, AI.md,
SCHEDULING.md, DEVELOPMENT.md. Update whenever an architectural decision changes.

## 99. Development Phases

1. Repository inspection and documentation.
2. iOS foundation and navigation.
3. Backend foundation and authentication.
4. Database and Course hierarchy.
5. Document ingestion and source repository.
6. AI curriculum generation.
7. Concept activation.
8. Learning Items and question generation.
9. Runtime AI provider abstraction.
10. AI answer evaluation.
11. Chessable-style scheduling.
12. Review sessions.
13. Concept mastery and analytics.
14. Voice answering.
15. Exam Mode.
16. Offline/resilience improvements.
17. Course import/export foundations.

## 100. Phase Completion Rule

At the end of every phase: build, run tests, fix compiler errors, fix failing tests, review
architecture, update documentation, leave the repository in a working state.

## 101. First Task

Immediately inspect the repository before writing code. Determine current project state,
architecture, existing iOS/backend files, existing tests, dependency management, current build
status. Produce: repository summary, architecture summary, current problems, implementation plan,
proposed file structure. Then begin Phase 1.

## 102. Acceptance Test

MVP is complete when the full workflow works end to end: create Course → create/import
Chapters/Topics → import PDF → extract source text → create source chunks → generate curriculum
proposal → user accepts/edits curriculum → Concepts exist → user activates selected Concepts →
Learning Items generated → Questions generated → user starts Review → answers by text → AI
evaluates → feedback shown → scheduling policy updates the Learning Item → next review stored →
review history stored → Concept mastery updates → Topic progress updates → Chapter progress
updates → Course progress updates → a second Course remains isolated → the runtime AI provider
can be changed through configuration → the application still works without any dependency on the
coding agent's model identity.

## 103. Quality Bar

Correctness, Security, Data Integrity, Course Isolation, Testability, Maintainability,
Traceability, User Control, AI Replaceability. Do not optimize only for speed of initial code
generation.

## 104. Architectural Mistakes to Avoid

Never: make each Concept a single flashcard by default; schedule an entire Chapter as one card;
allow inactive Concepts into normal review; let the LLM calculate dates directly; mix content
from different Courses; put LLM API calls inside SwiftUI Views; hard-code an AI provider; rely on
free-form LLM output for critical logic; discard user answers after network errors; copy personal
review history into a Course Template by default; claim an AI-generated score is scientifically
exact; silently use external knowledge against the Course source; make the application dependent
on Claude, Kimi, DeepSeek or GLM.

## 105. Final Architecture

```
USER
 │
 ▼
iPHONE APP
 │
 ├── CURRICULUM ─▶ COURSE STRUCTURE ─▶ CHAPTER / TOPIC / CONCEPT ─┬─▶ QUESTION ─▶ ANSWER
 │                                                                 └─▶ SOURCE ─▶ KNOWLEDGE REPO
 └── REVIEW ─▶ REVIEW SESSION ─▶ LEARNING ITEM ─┘
                                                  ▼
                                          AI EVALUATION
                                                  ▼
                                          REVIEW OUTCOME
                                                  ▼
                                          SCHEDULING POLICY
                                                  ▼
                                            NEXT REVIEW
                                                  ▼
                                           MASTERY UPDATE
```

Backend:

```
iPhone → HTTPS → FastAPI → Domain Services (Course, Document, Retrieval, Learning, Review,
Mastery, AIProvider) → Runtime AI Provider → Model API
```

## 106. Final Product Philosophy

"I choose what I am studying. The app organizes my material. I activate the concepts I have
actually studied. The app breaks those concepts into things it can test. It asks me questions in
different ways. I can answer by speaking or writing. The AI understands whether I really answered
correctly. The scheduler decides when that knowledge should return. If I consistently know it, it
appears less often. If I struggle, it returns sooner. The system remembers which parts of a
concept I know and which parts I do not. The system never confuses my different Courses. Over
time, the app becomes a personalized map of what I have learned and what I still need to
reinforce."

## 107. Final Coding Instruction

Treat this document as authoritative. Implement, don't merely discuss. Inspect the repository
first. Work incrementally. Test continuously. Keep the system compiling. Keep documentation
synchronized. Keep Course data isolated. Keep the scheduling engine independent from the AI. Keep
the runtime AI provider replaceable. Keep the coding agent independent from the finished
application's AI.

## Amendments

Decisions that change the text above. The original sections are kept as written; where they
disagree with an amendment, the amendment wins. Details and reasoning are in the linked docs.

| # | Date | Sections | Amendment | Decided by |
|---|---|---|---|---|
| A1 | 2026-09-24 | §20, §16 | Material is filed under Chapters; the AI proposes Topics → Concepts one Chapter at a time, sees what the Chapter already contains, and by default analyzes only material not analyzed yet. Deleting material never deletes Concepts; unsupported ones are flagged for review. (API.md) | Owner |
| A2 | 2026-09-24 | §44, §46 | AGAIN → level 1. HARD (correct with difficulty) advances like GOOD and marks the question hard; the user can review only the questions marked hard. (SCHEDULING.md §3, §3a) | Owner |
| A3 | 2026-09-24 | §37, §42, §85 | The AI evaluation returns semantic evidence and **no outcome**. A deterministic, versioned ReviewOutcomeResolver maps evidence to AGAIN/HARD/GOOD, or leaves it to the user when inconclusive; it never produces EASY. User overrides are stored beside, never over, the AI evaluation. (SCHEDULING.md §3b) | Owner's engineering brief |
| A4 | 2026-09-24 | §49, §50 | Review modes are split into a **session intent** (LEARN, SCHEDULED_REVIEW, PRACTICE, EXAM) and a **selection mode** (NEW, DUE, COURSE_ORDER, RANDOM, WEAK, RECENTLY_FAILED, MARKED_HARD, SELECTED). PRACTICE never changes memory state unless the user opts in; EXAM must never affect it by accident. The hard-only review of A2 is PRACTICE + MARKED_HARD. | Owner's engineering brief |
| A5 | 2026-09-24 | §21, §43 | Activated items are encoded in a LEARN session (introduction → first retrieval → feedback) before entering scheduled review; the policy's `initialize` is its first successful learning transition. | Owner's engineering brief |
| A6 | 2026-09-24 | §24 | A Learning Item has a content **role** (CORE_TRAINABLE, SUPPORTING_TRAINABLE, COMMON_TRAP, INFORMATIONAL, REFERENCE, OPTIONAL_EXTENSION) and a separate user-controlled **in_training** flag; taking an item out of training keeps its sources and history. | Owner's engineering brief |
