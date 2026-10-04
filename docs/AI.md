# AI

Status: **The provider abstraction (Phase 9), curriculum generation (Phase 6), Learning Item and
question generation (Phase 8) and answer evaluation (Phase 10) are implemented and tested.**
Exams (Phase 15), follow-up questions and question variations are still design reference. No real model has been called from this repository yet:
everything is tested against `MockAIProvider`, a scripted transport, and a fake OpenAI-compatible
HTTP server (see DEVELOPMENT.md).

## 1. Coding agent vs runtime AI — do not confuse these

The coding agent building this repository (Claude, Kimi, DeepSeek, GLM, or another) is
**unrelated** to the runtime AI the finished application calls (Qwen, DeepSeek, Kimi, GLM, a
managed inference service, or a self-hosted model). Nothing in `backend/app/ai/` may assume a
specific coding agent built it, and nothing in the product may assume a specific runtime provider
(spec §3, §35, §104).

## 2. AIProvider interface

Defined once, in `backend/app/ai/provider.py`, and used by services only: never by route
handlers, and never by the iOS client.

```
backend/app/ai/
  provider.py   AIProvider (the interface), LLMAIProvider (model-backed), AICallInfo
  transport.py  ChatTransport; OpenAICompatibleTransport (httpx, /chat/completions)
  mock.py       MockAIProvider (deterministic, offline)
  schemas.py    operation inputs + the JSON schemas outputs are validated against
  factory.py    build_ai_provider(settings); get_ai_provider (FastAPI dependency)
backend/app/prompts/
  curriculum_generation_v1.py
```

Two layers, so a provider switch never touches business logic:

- **`LLMAIProvider`** builds each operation's versioned prompt, calls the transport, validates
  the answer against the operation's schema, and retries once (§5). It knows nothing about HTTP.
- **`ChatTransport`** sends messages and returns text. `OpenAICompatibleTransport` is the only
  code that talks to a model over the network.

Operations are added to the interface by the phase that needs them. Implemented:

```
generate_curriculum(CurriculumRequest) -> CurriculumResult            # Course: chapters → topics → concepts
generate_chapter_curriculum(ChapterCurriculumRequest) -> ChapterCurriculumResult
                                                                      # one Chapter: topics → concepts,
                                                                      # merged with its existing structure
generate_learning_items(LearningItemsRequest) -> LearningItemsResult  # one Concept: items + 1-3
                                                                      # questions each, with roles
evaluate_answer(EvaluationRequest) -> EvaluationResult                # semantic evidence, no outcome
```

`FallbackAIProvider` wraps several providers behind the same interface (§3).

Spec §32 operations covered differently: `extractConcepts` is part of the curriculum
operations; `generateQuestion` is part of `generate_learning_items` (questions are generated with
their item, in one call); `generateFeedback` is part of `evaluate_answer` (the evaluation
carries its feedback). Still to add: `generateQuestionVariations`, `generateFollowUpQuestion`,
`generateExam` (15). Each gets a prompt module, an output schema
in `schemas.py`, a method on `LLMAIProvider` using `_structured_call`, and a `MockAIProvider`
counterpart.

`evaluate_answer` returns evidence — it never returns or implies a review outcome or a next review
date. The outcome is the deterministic `ReviewOutcomeResolver`'s, the date the
`SchedulingPolicy`'s (SCHEDULING.md §1, §3b; spec §42).

## 3. Runtime provider configuration

No provider is hard-coded. Configured entirely through environment (spec §33, `.env.example`):

| Variable | Default | Meaning |
|---|---|---|
| `AI_PROVIDER` | empty | empty = AI off (server runs, AI endpoints return 503); `mock`; `router` (FREE_AI_ROUTING.md); a catalog provider (`groq`, `mistral`, `gemini`, `openrouter`, `nvidia`, `cloudflare`, `cohere`); or `openai_compatible` / `qwen` / `deepseek` / `kimi` / `glm` |
| `AI_COST_POLICY` | FREE_ONLY | FREE_ONLY / FREE_FIRST / ANY_CONFIGURED (FREE_AI_ROUTING.md §4) |
| `AI_BASE_URL` | | required unless `mock`, `router` or a catalog provider; e.g. `https://…/v1` (the transport appends `/chat/completions`) |
| `AI_API_KEY` | empty | sent as `Authorization: Bearer`; omitted when empty (self-hosted) |
| `AI_MODEL` | | required unless `mock` |
| `AI_TIMEOUT` | 60 | seconds per HTTP call |
| `AI_TEMPERATURE` | 0.2 | 0–2 |
| `AI_MAX_TOKENS` | 8192 | output cap; an answer cut off at the cap fails with a message saying so |
| `AI_JSON_MODE` | true | sends `response_format: {"type": "json_object"}`; turn off for endpoints that reject it |
| `AI_MAX_CONTEXT_CHARS` | 60000 | most source text per call (~15k tokens) |

**Fallbacks.** `AI_FALLBACK1_PROVIDER/_BASE_URL/_API_KEY/_MODEL` and `AI_FALLBACK2_…` add
providers tried in order. They form one route shared by every operation and run through the
same router, cost policy and failure handling as `AI_PROVIDER=router` (FREE_AI_ROUTING.md). The next one is used when the previous is **unavailable** (timeout,
connection error, any non-200 status such as 429 or 5xx, malformed response) or **kept
answering invalid output** after its own retry. Unexpected errors (bugs) are not masked by a
fallback. The result records the provider that actually answered and its `fallback_index`;
each attempt logs `ai_route … fallback_index=… error_class=…`. Fallbacks share the timeout/temperature/token settings
and use their one model for every operation. A fallback also receives the study material, so
only configure vendors you accept for that data.

- `openai_compatible`/`qwen`/`deepseek`/`kimi`/`glm` are **labels**: the same OpenAI-compatible
  transport, with no hard-coded URL, and UNKNOWN cost, so under the default FREE_ONLY they never
  run. The catalog providers (FREE_AI_ROUTING.md §2) have known endpoints. The name given is
  what gets recorded as `ai_provider`.
- Invalid combinations stop the server at startup (unknown `AI_PROVIDER`; a real provider
  without `AI_BASE_URL` or `AI_MODEL`), like a weak `AUTH_SECRET` does.
- Qwen, DeepSeek, Kimi, GLM, vLLM, Ollama and most managed inference services accept this
  format, so switching is a configuration change only.

### Recommended setup (owner's question, 2026-09-24)

Not measured: no real model has been called from this project, and model names and prices change
often, so check each vendor's current documentation. The recommendation rests on three
requirements: good Italian, reliable JSON, low cost per chapter.

| Role | Vendor | Why |
|---|---|---|
| Try-out phase | **OpenRouter** (`openai_compatible`, one key) | Run the same chapter through several models (DeepSeek, Qwen, Mistral, GLM, Kimi) and compare proposals before committing to one vendor |
| Primary | **DeepSeek** (`deepseek`), its current general chat model | Among the cheapest strong models; OpenAI-compatible with JSON mode |
| Fallback 1 | **Qwen** (`qwen`) via Alibaba Cloud Model Studio's international OpenAI-compatible endpoint | Different company and infrastructure; strong multilingual models |
| Fallback 2 | **Mistral** (`openai_compatible`), EU-hosted | A third, independent vendor, and the EU option (below) |

**Privacy decides the order more than quality.** DeepSeek processes data in China; Alibaba
Cloud's international region is outside the EU. For the owner's own textbooks that is a personal
choice. If the app will hold *other people's* material, EU data protection law (GDPR) applies,
and an EU-hosted primary (Mistral) is the safer default, with the others as opt-in only.

Chapter-scoped generation already keeps each call small (one chapter's new material), so a large
context window is not a deciding factor.

### Free-first routing, real providers and credentials

Superseded by **`docs/FREE_AI_ROUTING.md`**, which covers:

- the approved providers (Groq, Mistral, Gemini, Cloudflare Workers AI, OpenRouter, NVIDIA
  hosted NIM, Cohere as an optional benchmark);
- the model catalog with cost and privacy classes;
- `AI_PROVIDER=router` with per-operation routes;
- `AI_COST_POLICY` (default `FREE_ONLY`: a paid endpoint is never called) and `AI_DATA_POLICY`;
- normalized failures and fallback;
- structured output;
- the manual benchmark workflow.

Keys live only in GitHub Actions secrets (`GROQ_API_KEY`, `MISTRAL_API_KEY`, `GEMINI_API_KEY`,
`OPENROUTER_API_KEY`, `CLOUDFLARE_API_TOKEN`, `NVIDIA_API_KEY`, `COHERE_API_KEY`, and for
Chinese model families the gateways `DASHSCOPE_API_KEY`, `TENCENT_TOKENHUB_API_KEY`,
`SILICONFLOW_API_KEY`) plus variables such as `CLOUDFLARE_ACCOUNT_ID`. CI maps them onto the generic variables. The DeepSeek, Qwen,
Kimi and GLM secret names proposed earlier are no longer used.

## 4. Multi-model routing (per-operation model fallback implemented)

Spec §34 anticipates routing simple operations (classification, basic extraction, simple question
generation) to a fast model and difficult operations (open-ended evaluation, misconception
detection, nuanced conceptual evaluation) to a stronger model, via:

```
AI_MODEL_EXTRACTION=
AI_MODEL_GENERATION=
AI_MODEL_EVALUATION=
AI_MODEL_EXAM=
```

Implemented as a fallback: each operation belongs to one group
(`OPERATION_MODEL_GROUP` in `provider.py`; curriculum generation is `generation`), and uses
`AI_MODEL_<GROUP>` when set, `AI_MODEL` otherwise. Leaving them empty keeps one model for
everything. They share one endpoint (`AI_BASE_URL`); per-group endpoints are not supported yet.

## 5. Structured output contract

All machine-consumed AI operations return structured JSON, validated against a schema — never
parsed as free-form prose for critical logic (spec §36). Implemented in
`LLMAIProvider._structured_call`:

1. JSON wrapped in a Markdown code fence is accepted (common, and not worth a retry).
2. Otherwise invalid JSON, or JSON failing the schema, gets **one** retry: the original prompt
   plus a message naming what was wrong (locations and error kinds only, never content). The
   rejected answer isn't sent back.
3. Still invalid → `AIInvalidOutputError`. An answer cut off at `AI_MAX_TOKENS` fails
   immediately, since a retry would be cut off too. Transport failures (timeout, connection,
   non-200, malformed response envelope) → `AIUnavailableError`, not retried.
4. Background jobs turn these into a `FAILED` status with a user-safe message. Nothing crashes,
   nothing is guessed.

### Curriculum Schema (`CurriculumOutput`)

```json
{
  "context_sufficient": true,
  "chapters": [{"title": "", "description": "", "topics": [{"title": "", "description": "",
    "concepts": [{"title": "", "description": "", "source_refs": ["S1"]}]}]}]
}
```

Passages are sent as `[S1] Document: x.pdf | Page 3 | Section: …` blocks. The model cites refs,
not UUIDs, and the service maps them back. Grounding (spec §19) is enforced after validation: refs
that weren't sent are removed, Concepts left without one are dropped and counted, and a proposal
with nothing left is `INSUFFICIENT_CONTEXT`.

### Answer Evaluation Schema (`EvaluationOutput`; amends spec §37)

```json
{
  "classification": "CORRECT | PARTIALLY_CORRECT | MISCONCEPTION | WRONG | UNCERTAIN",
  "correctness": 0.0,
  "completeness": 0.0,
  "conceptual_understanding": 0.0,
  "precision": 0.0,
  "confidence": 0.0,
  "correct_points": [],
  "missing_points": [],
  "misconceptions": [],
  "source_corrections": [],
  "context_sufficient": true,
  "feedback": ""
}
```

- All scores are 0.0–1.0, validated; out-of-range or missing fields get the one constrained
  retry, then fail.
- **No `outcome`.** Spec §37 had the model return AGAIN/HARD/GOOD/EASY, which would let a
  model's quirks drive the schedule, against spec §42. The outcome comes from the
  `ReviewOutcomeResolver`. A model that volunteers an `outcome` key has it ignored
  (`extra="ignore"`), so it can never reach the scheduler (tested).
- `missing_points` is the spec's `missing_concepts`.
- The evaluation is grounded in the Learning Item's own source passages, its reference answer
  (`expected_knowledge`) and `essential_points`. The prompt tells the model not to count outside
  knowledge the passages don't support, to prefer UNCERTAIN over guessing, and to treat the
  student's answer as data (it may contain instructions).

### Learning Items Schema (`LearningItemsOutput`)

`{context_sufficient, items: [{title, objective, expected_knowledge, essential_points (≤10),
role, difficulty (1-5), source_refs, questions: [{question_type, text}] (≤5)}] (≤12)}`. Items
citing no passage that was sent are dropped. `role` and `question_type` are validated enums.

## 6. Semantic evaluation, not keyword matching

Evaluation must recognize different wording as equivalent when the meaning is equivalent (spec
§39). Keyword matching is not the primary evaluation strategy.

## 7. Source material as authority

Course material is the primary source of truth for Course-specific generation and evaluation
(spec §19):
- If `external_knowledge_mode` is off (default), generation is grounded in Course material,
  evaluation prioritizes Course material, feedback references source material.
- If retrieved context is insufficient, the AI operation returns `context_sufficient: false` /
  `INSUFFICIENT_CONTEXT` — never a hallucinated citation.

## 8. Retrieval (RAG) scoping

Every retrieval request must carry a course scope and, where applicable, chapter/topic/concept
scope. No global retrieval (spec §72, §10).

```
User Task → Scope determination → Retriever (course-scoped) → Relevant chunks →
Prompt construction → AIProvider call → Structured output → Schema validation
```

**Today there is no relevance ranking.** Curriculum generation sends the scoped passages in
document order until `AI_MAX_CONTEXT_CHARS` is spent. The scope is in the WHERE clause on both
`document_chunks.course_id` and `documents.course_id`. Embedding search (pgvector) becomes
necessary for Phase 8/10, where a single Concept's passages must be found inside a large Course.

## 9. Prompt versioning

Prompt templates live in `backend/app/prompts/`, one Python module per operation and version
(`VERSION`, `SYSTEM`, `USER`, and a `RETRY` template, all `string.Template` so source text
containing `$` is never interpreted). **A prompt is never edited once used**: add `_v2` and
switch the caller. Implemented: `curriculum_generation_v1`, `chapter_curriculum_v1`,
`learning_item_generation_v1`, `answer_evaluation_v1`. Planned:

```
concept_extraction_v1
curriculum_generation_v1
learning_item_generation_v1
question_generation_v1
answer_evaluation_v1
question_variation_v1
exam_generation_v1
```

The prompt version used is stored alongside every piece of generated content and every
`Evaluation` row (spec §73, §85). The curriculum prompt treats passages as data and tells the
model to ignore instructions inside them; that reduces, but can't eliminate, prompt injection from
uploaded material. Its effect is limited to the user's own proposal, which they review.

## 10. Model version tracking

Every AI call's `provider`, `model`, `model_version`, and `prompt_version` are stored with a
timestamp (spec §74), and its latency and attempt count are logged (`ai_call operation=…
latency_ms=… attempts=…`, never content or credentials) — required for later benchmarking (§75) and for auditability.
`model_version` is the model id the provider reports having served (often a dated snapshot),
falling back to the requested `model` when the response doesn't say.

## 11. Benchmarking (future)

The evaluation layer is architected so runtime models can later be benchmarked against a
human-labeled dataset of student responses, on: correctness classification, completeness,
misconception detection, semantic equivalence, suggested-outcome consistency (spec §75). No model
is assumed permanently superior.

## 12. MockAIProvider

`backend/app/ai/mock.py`: same interface, deterministic, offline. All automated tests use it
(the `ai_provider` fixture in `tests/conftest.py`) — no test requires real API access (spec §76).

- Default output is mechanical, not a real curriculum: one Chapter per document, one Topic per
  section (or per 5 passages), one Concept per passage citing it. Useful for local development
  (`AI_PROVIDER=mock`) and for building the iOS screens without an API key.
- `MockAIProvider(curriculum=...)` returns a scripted answer; `MockAIProvider(error=...)` raises.
  It records every request in `curriculum_requests`, so tests can assert what would have been
  sent to a model.
- `MockAIProvider(learning_items=...)` and `MockAIProvider(evaluation=...)` (a fixed output or a
  function of the request) script the other operations. Default learning items: one
  CORE_TRAINABLE item per passage (up to 3) with two formulations. Default evaluation: overlap
  with the essential points (a stand-in; spec §39 forbids keyword matching as the real
  evaluator).
- The answer fixtures A–I (spec §78) are pinned at the resolver level
  (`tests/test_outcome_resolver.py`): given the evidence a good evaluator returns for each, the
  outcome is fixed. Whether a real model returns that evidence must be checked against real
  models (benchmarking, §11).

## 13. Misconception tracking

Important misconceptions are stored against both the Concept and the Learning Item (spec §40) so
future question generation/selection can target them, without pedagogically-unjustified exact
repetition (spec §58).

## 14. Cost control

Minimize unnecessary model calls via caching, question-formulation reuse, pre-generation,
batching where useful, and a smaller/faster model for simple operations vs. a stronger model for
difficult evaluation once multi-model routing is built (spec §71).

## 15. Privacy in AI calls

Minimal data transmission to the AI provider; no full-document logging; no full private-answer
logging by default (spec §70, §94). Every call logs one content-free line at INFO:

```
ai_call operation=generate_curriculum provider=deepseek model=deepseek-chat latency_ms=5 attempts=2 error_type=none
```

Services log their own ids (proposal, course) next to failures. `request_id` and `user_id`
correlation are not implemented yet.

## Drawing answers (2026-10)

A Learning Item can be answered by drawing instead of words (`answer_format: DRAWING`), for
questions whose answer is a picture: a chemical structure, a diagram, a graph.

- **Reference.** `PUT /learning-items/{id}/reference-drawing` (PNG, JPEG or WebP, 3 MB at most,
  type read from the bytes) makes the item a drawing question; `DELETE` turns it back into a text
  question. Files live in DocumentStorage under `courses/{course}/drawings/...`, are served only to
  the owner (`Cache-Control: private, no-store`) and are deleted with the Course.
- **Answer.** `POST /review-sessions/{id}/answers` takes `drawing` (a data URL) instead of `text`
  (an optional note). The web client has a drawing pad (pen, eraser, undo, mouse, finger or
  stylus) and accepts a photo of a drawing made on paper, scaled down before upload.
- **Evaluation.** `AIProvider.evaluate_drawing` sends the question, then the reference image, then
  the student's image (OpenAI-style `image_url` content parts) with prompt
  `drawing_evaluation_v1`, and returns the same `EvaluationOutput` as text answers, so the
  ReviewOutcomeResolver, second opinions, weak spots and XP work unchanged.
- **Routing.** A separate operation, `DRAWING_EVALUATION` (`AI_ROUTE_DRAWING_EVALUATION`), that
  only models which read images may serve: by default Gemini 3.5 Flash-Lite, then Flash. Text-only
  models never receive drawings. With no such model, evaluation fails cleanly and the student
  grades the drawing themselves, with both drawings side by side.
- **Mock.** The offline mock can't see images: an identical drawing is CORRECT, anything else is
  UNCERTAIN (the student grades it). Real grading quality is unmeasured until the Gemini route is
  benchmarked on drawings.
