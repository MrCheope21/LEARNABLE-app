# Private Beta Scope

What the first private beta contains and what it deliberately doesn't. Status evidence is in
docs/PROJECT_STATUS.md. Nothing here is a promise about dates.

## In scope

| Capability | Clients |
|---|---|
| Text-based material: PDF, Markdown, text, DOCX, PPTX (text layer only) | Web, iOS |
| Course hierarchy: Course → Chapter → Topic → Concept | Web, iOS |
| AI curriculum proposal, edited by the user before it's applied | Web, iOS |
| Concept activation → AI Learning Items and questions, grounded in sources | Web, iOS |
| LEARN sessions (introduction, then recall) | Web, iOS |
| Scheduled review (SCHEDULED_REVIEW) on the deterministic Chessable-style ladder | Web, iOS |
| Text answers, grounded AI evaluation, deterministic outcome resolver | Web, iOS |
| User override of the grade, with an audit trail | Web, iOS |
| Review history (stored; shown as memory state and next review, not as a history screen) | Web, iOS |
| Curriculum and memory progress, review load | Web, iOS |
| Recovery of background jobs interrupted by a restart (marked failed, retryable) | Backend |

## Deferred

Not in the beta, and not to be started until the beta gates below are met:

- Voice answering (an unwired iOS service exists)
- Exam Mode
- OCR for scanned or image-only material
- Full offline use (only answer drafts are kept locally)
- Course import/export
- Coverage model (how much of the material the items cover)
- Advanced question variation and follow-up questions
- External-knowledge mode (answers judged beyond the course sources)
- Paid marketplace listings (the marketplace itself is free-only)

## Release decisions

- **The web client is English-only for the beta.** iOS is localized in Italian and English;
  web strings are in the components, not a catalog. A beta tester who studies in Italian gets
  Italian material, questions and feedback (they follow the course language) inside an English
  interface. This is accepted for a private beta, not for a public launch.
- **FREE_ONLY AI.** The beta runs on free provider capacity only. When it's exhausted the app
  says so (`free_capacity_exhausted`) instead of spending money. Expect that under load.
- **Background jobs stay in-process.** A restart fails running jobs (they become retryable);
  it doesn't lose data. A job queue waits for real volume or several backend replicas.

## Gates before inviting testers

1. An answer evaluator approved through the benchmark (`real-ai.yml`: `verify`, then
   `evaluation` with `repeat: 2`) and set in `AI_ROUTE_ANSWER_EVALUATION`. Until then the
   grading is the mock's keyword overlap, and a beta would test nothing that matters.
2. CI green on the pull request: backend, web (including the browser E2E), iOS unit tests and
   the iOS simulator acceptance run.
3. docs/HUMAN_SMOKE_TEST.md done once per client by someone who didn't build it, with no
   BLOCKER and no FAIL left open.
4. A deployment with HTTPS, a real `AUTH_SECRET`, PostgreSQL and backups (not built yet).
