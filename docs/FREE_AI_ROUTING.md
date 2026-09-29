# Free AI Routing

How the backend uses zero-cost AI inference before any paid provider, and how that is
verified. Code: `backend/app/ai/{catalog,routing,factory,failures,structured,cloudflare}.py`.
General AI design: `docs/AI.md`.

**Status (2026-09-24): implemented and tested with mocks; no real provider called yet.** This
repository's cloud sandbox can't reach any vendor API (its network policy blocks them), so
every model ID below is **unverified**, and **no evaluator is approved**. The first real calls
happen in GitHub Actions (§8) once the owner adds secrets.

## 1. Shape

```
Answer ─▶ AIProvider evaluation ─▶ EvaluationResult ─▶ ReviewOutcomeResolver ─▶ outcome ─▶ SchedulingPolicy
               │
               └─ RoutedAIProvider: per-operation candidates, cost + data policy, fallback
```

The router only decides **who** produces the semantic evaluation (or the curriculum, items,
questions). Outcomes stay with the deterministic resolver and dates with the scheduling policy:
a provider never computes a due date or touches review state. All calls are server-side; no
key is ever sent to iOS or the web client.

## 2. Providers and models

The catalog (`app/ai/catalog.py`) records, per provider/model: which operations it may serve;
JSON / JSON Schema / strict JSON Schema support; whether the API is OpenAI-compatible; cost
class; privacy class; free-only eligibility; evaluation approval; and whether it has been
verified live.

| Provider | Transport | Endpoint (default) | GitHub secret |
|---|---|---|---|
| Groq | OpenAI-compatible | `https://api.groq.com/openai/v1` | `GROQ_API_KEY` |
| Mistral | OpenAI-compatible | `https://api.mistral.ai/v1` | `MISTRAL_API_KEY` |
| Google Gemini | OpenAI-compatible | `https://generativelanguage.googleapis.com/v1beta/openai/` | `GEMINI_API_KEY` |
| OpenRouter | OpenAI-compatible (+ `X-Title` header) | `https://openrouter.ai/api/v1` | `OPENROUTER_API_KEY` |
| NVIDIA hosted NIM | OpenAI-compatible | `https://integrate.api.nvidia.com/v1` | `NVIDIA_API_KEY` |
| Cloudflare Workers AI | own adapter (`/accounts/{id}/ai/run/{model}`) | `https://api.cloudflare.com/client/v4` | `CLOUDFLARE_API_TOKEN` + variable `CLOUDFLARE_ACCOUNT_ID` |
| Cohere (optional, benchmark) | OpenAI-compatible (compatibility API) | `https://api.cohere.ai/compatibility/v1` | `COHERE_API_KEY` |

One generic OpenAI-compatible transport serves six of the seven. Only Cloudflare needs its own
~80-line adapter, because its REST shape differs. Cerebras (trial / payment-method-backed) and
Hugging Face (too little recurring free credit) are deliberately absent, and Pollinations is
not included yet.

| Model | Operations | Structured output | Cost | Privacy | Free-only | Notes |
|---|---|---|---|---|---|---|
| `groq:openai/gpt-oss-120b` | all | strict JSON Schema | FREE_RECURRING | UNKNOWN | yes | preferred evaluator candidate |
| `groq:qwen/qwen3.8-27b` | all | strict JSON Schema | FREE_RECURRING | UNKNOWN | yes | question-generation candidate; confirm the ID |
| `mistral:mistral-small-latest` | all | strict JSON Schema | FREE_RECURRING | UNKNOWN | yes | Free (Experiment) plan |
| `gemini:gemini-2.5-flash` | all | JSON Schema | FREE_RECURRING | **DEVELOPMENT_ONLY** | yes | free-tier content may be used by Google |
| `gemini:gemini-2.5-flash-lite` | all | JSON Schema | FREE_RECURRING | **DEVELOPMENT_ONLY** | yes | as above |
| `cloudflare:@cf/zai-org/glm-4.7-flash` | all | JSON Schema | FREE_RECURRING | UNKNOWN | yes | daily free allocation |
| `cloudflare:@cf/google/gemma-4-26b-a4b-it` | all | JSON Schema | FREE_RECURRING | UNKNOWN | yes | |
| `cloudflare:@cf/nvidia/nemotron-3-120b-a12b` | all | JSON Schema | FREE_RECURRING | UNKNOWN | yes | evaluator candidate |
| `openrouter:<id>:free` (rule) | all | JSON Schema | FREE_LIMITED | UNKNOWN | yes | only IDs ending `:free`; the suffix is never stripped |
| `openrouter:<id>` (no `:free`) | — | — | PAID | — | **no** | never runs under FREE_ONLY |
| `nvidia:<id>` | all | JSON | UNKNOWN | UNKNOWN | **no, until allowlisted** | the owner adds verified Free Endpoints to `AI_FREE_MODELS` |
| `cohere:command-a-03-2025` | evaluation only | JSON | FREE_LIMITED | UNKNOWN | yes | benchmark, not production capacity |
| anything else | — | — | UNKNOWN | UNKNOWN | **no** | |

### 2b. Chinese model ecosystems: gateways first

Provider (who serves the model) and model family (who made it) are separate dimensions.
`provider=tencent_tokenhub, model=kimi-k3` is not `provider=moonshot, model=kimi-k3`: they
differ in cost, quota and terms. Both dimensions are recorded:

- provider and exact model are persisted on every AI result;
- `model_family` (qwen, glm, kimi, deepseek, minimax, hunyuan, …) is derived from the model ID
  in the catalog and the benchmark reports.

Free access to Qwen, GLM, Kimi and DeepSeek comes first from gateways; the direct vendor APIs are
paid:

| Provider | Endpoint | GitHub secret | Cost class | Free-only when |
|---|---|---|---|---|
| `alibaba_model_studio` | `https://dashscope-intl.aliyuncs.com/compatible-mode/v1` (Singapore, where new-user quotas apply); optional workspace via variable `ALIBABA_WORKSPACE_ID` (header `X-DashScope-WorkSpace`) | `DASHSCOPE_API_KEY` | FREE_CREDITS (new-user quota per model, ~90 days) | the owner enabled **Free Quota Only** in the console **and** set `ALIBABA_FREE_ONLY_CONFIRMED=true` (app: `AI_ALIBABA_FREE_ONLY_CONFIRMED`) **and** the model is in `AI_FREE_MODELS` |
| `tencent_tokenhub` | `https://tokenhub-intl.tencentmaas.com/v1` | `TENCENT_TOKENHUB_API_KEY` | FREE_CREDITS (new-user trial packages) | post-paid billing is **disabled** in the console **and** `TENCENT_FREE_ONLY_CONFIRMED=true` (app: `AI_TENCENT_FREE_ONLY_CONFIRMED`) **and** the model is in `AI_FREE_MODELS` |
| `siliconflow` | `https://api.siliconflow.com/v1` | `SILICONFLOW_API_KEY` | FREE_RECURRING for its free models only | the model is a catalog free model or in `AI_FREE_MODELS` |
| `deepseek` (direct) | `https://api.deepseek.com/v1` | not needed now | PAID_LOW_COST | only if the account has a granted free balance and the model is allowlisted |
| `moonshot` (direct Kimi) | `https://api.moonshot.ai/v1` | not needed now | PAID | never by default |
| `zai` (direct GLM) | `https://api.z.ai/api/paas/v4` | not needed now | FREE_CREDITS at most | allowlisted promotional credits |
| `minimax` (direct) | `https://api.minimax.io/v1` | not needed now | PAID | never by default |

**Why the billing guard is enforced in code.** Alibaba's and Tencent's free quotas are
temporary, and exhausting them can turn into pay-as-you-go. The app can't read the console
setting, so the owner confirms it with a variable. Until both the guard and the model's
allowlist entry are present, no model of that provider runs under FREE_ONLY, whatever the
catalog says. The app never enables post-paid billing.

**Exhausted free quota.** A provider refusing because a free quota or trial package is used up
(e.g. Alibaba's "free tier … exhausted", Tencent's trial package) is `FREE_QUOTA_EXHAUSTED`:

- the router falls back to the next candidate;
- that model is excluded for the rest of the process.

**Small free models** (SiliconFlow `THUDM/GLM-Z1-9B-0414`, candidate) may do light work:
simple question generation, concept extraction, basic feedback. They are never used for
grading until the benchmark approves them (`AI_EVALUATION_APPROVED_MODELS`), even though they
are free.

Candidate models from the owner's research. All are unverified: run `list-models` first.

- Alibaba: `qwen3.8-27b`. Other families it serves (DeepSeek, Kimi, GLM, MiniMax): add their
  exact IDs from `list-models`, only those the console shows as having free quota.
- Tencent TokenHub: `glm-5.3-flash`, `kimi-k3`, `deepseek/deepseek-flash` (Hunyuan, MiniMax,
  Qwen: from `list-models`).
- SiliconFlow: `THUDM/GLM-Z1-9B-0414`, plus the free Qwen/GLM light models the account shows.

With FREE_FIRST, gateway-hosted DeepSeek runs before direct paid DeepSeek even when the direct
one is listed first (tested). Under FREE_ONLY the direct one never runs.

The privacy classes are deliberately cautious. Nobody has reviewed these vendors' terms for
private material, so apart from Gemini's known free-tier data use they are UNKNOWN, not
approved. The mock is the only PRIVATE_APPROVED model.

NVIDIA's allowlist starts empty on purpose. Its catalog mixes "Free Endpoint" models with
others, and neither the model IDs nor that label could be verified from here. Run `list-models`
(§8), check the label on build.nvidia.com, then set the repository variable
`AI_FREE_MODELS=nvidia:<id>,…`.

## 3. Configuration

The backend reads only generic `AI_*` variables. It never reads GitHub's secret names.

- **Single provider:** `AI_PROVIDER=groq`, `AI_MODEL=…`, `AI_API_KEY=…`. `AI_BASE_URL` is
  optional for catalog providers, and Cloudflare also needs `AI_CLOUDFLARE_ACCOUNT_ID`. The
  pre-existing labels (`openai_compatible`, `deepseek`, …) still work but are UNKNOWN cost, so
  they only run with `AI_COST_POLICY=ANY_CONFIGURED` or `FREE_FIRST`.
- **Router:** `AI_PROVIDER=router`, one credential per provider (`AI_GROQ_API_KEY`,
  `AI_MISTRAL_API_KEY`, `AI_GEMINI_API_KEY`, `AI_OPENROUTER_API_KEY`, `AI_NVIDIA_API_KEY`,
  `AI_CLOUDFLARE_API_TOKEN` + `AI_CLOUDFLARE_ACCOUNT_ID`, `AI_COHERE_API_KEY`). Providers without
  a credential are skipped (`not_configured`).
- **Routes, per operation:** `AI_ROUTE_<OPERATION>=provider:model,provider:model,…` for
  CURRICULUM_GENERATION (Course scope), CONCEPT_EXTRACTION (Chapter scope: topics and concepts
  from new material), LEARNING_ITEM_GENERATION, QUESTION_GENERATION and ANSWER_EVALUATION.
  FEEDBACK_GENERATION is reserved: feedback is produced inside answer evaluation today. Blank
  uses the catalog defaults below.

**Default routes are provisional:** the owner's initial candidate order, not benchmark results.
Grading order must come from the benchmark (§8).

| Operation | Default route |
|---|---|
| CURRICULUM_GENERATION, CONCEPT_EXTRACTION, LEARNING_ITEM_GENERATION | Gemini Flash → Mistral Small → Groq GPT-OSS 120B → Cloudflare GLM-4.7 Flash |
| QUESTION_GENERATION | Mistral Small → Gemini Flash → Groq Qwen → Cloudflare GLM-4.7 Flash |
| ANSWER_EVALUATION | Groq GPT-OSS 120B → Mistral Small → Cloudflare Nemotron → Gemini Flash |

OpenRouter (low daily allowance) and NVIDIA (allowlist) are not in the defaults. Add them to a
route once verified.

## 4. Policies

**`AI_COST_POLICY`** (default `FREE_ONLY`):

- `FREE_ONLY`: only `free_only_eligible` models are ever **constructed**. A paid or
  unknown-cost candidate is dropped when the router is built, and the router refuses it again
  at call time, so a route assembled any other way can't reach it either. If
  no eligible candidate can answer, the call fails with `free_capacity_exhausted` (HTTP 503),
  listing who was tried and why.
- `FREE_FIRST`: free candidates in route order, then the others.
- `ANY_CONFIGURED`: route order as written.

**`AI_DATA_POLICY`** (default `development`): `private` keeps only models the owner has
approved for private material (`AI_PRIVATE_APPROVED_MODELS`). That excludes Gemini's free tier
and every model whose terms haven't been reviewed. Production with real users' material should
run `private`.

**Evaluators:**

- A dynamically routed model (e.g. `openrouter/…` routers) is never an evaluator: a grade must
  be attributable to one exact model.
- `AI_EVALUATION_REQUIRE_APPROVED=true` limits grading to models in
  `AI_EVALUATION_APPROVED_MODELS`. Only add a model there after it passes §8.

Tests prove it (`tests/test_free_ai_routing.py`). They place paid and unknown models at the
**front** of a route with valid keys, make every free candidate fail, and assert the paid ones
were never called and the result is `free_capacity_exhausted`. They also cover the chain
Groq (quota) → Mistral (down) → Gemini (timeout) → next free provider.

## 5. Failures and fallback

Every transport maps errors to one kind (`app/ai/failures.py`). Error bodies are read only to
classify; they never go into errors or logs.

| Kind | From | Router |
|---|---|---|
| AUTH_FAILURE | 401/403 | next candidate; **provider disabled for the rest of the process**; logged as a configuration failure |
| RATE_LIMITED | 429 | next candidate |
| QUOTA_EXHAUSTED | 429 mentioning quota/credits/daily free allocation (e.g. Cloudflare's), 402 | next candidate |
| FREE_QUOTA_EXHAUSTED | 400/402/403/429 mentioning a free tier/quota/trial package (Alibaba with Free Quota Only, TokenHub trial) | next candidate; **model excluded for the process** |
| PROVIDER_UNAVAILABLE | 5xx, connection errors, malformed responses | next candidate |
| MODEL_UNAVAILABLE | 404, "model not found" | next candidate |
| MODEL_NOT_FREE | 403 "requires Workers Paid" / paid plan | next candidate; **model excluded for the process** |
| TIMEOUT | client timeout, 408/504 | next candidate |
| INVALID_STRUCTURED_OUTPUT | output still invalid after the one constrained retry, or truncated | next candidate |

Each candidate is tried at most once per call, plus its single schema retry. Nothing retries
endlessly.

## 6. Structured output

The application's Pydantic schemas stay authoritative: every answer is validated locally,
whatever the provider promised. What is requested depends on the model:

- **strict JSON Schema** (Groq GPT-OSS/Qwen, Mistral): constrained decoding to the schema.
- **JSON Schema, not strict** (Gemini, Cloudflare, OpenRouter): the schema as a hint.
- **JSON mode** (NVIDIA allowlisted, Cohere, unknown): `json_object`.

The schema sent (`app/ai/structured.py`) is derived from the Pydantic model and adapted for
strict decoders:

- `$ref`s are inlined;
- every property is required, and objects get `additionalProperties: false`;
- length, range and size keywords are removed.

The removed limits are still enforced by local validation, so the domain rules are not
weakened (tested).

## 7. Observability

Every attempt logs `ai_route operation=… provider=… model=… fallback_index=… latency_ms=…
schema_valid=… error_class=…`, and every successful call logs `ai_call …` with the prompt
version. Nothing else is logged: no prompt, passage, student answer, key or header.

Provider, model, served model version and prompt version are persisted with:

- proposals, Learning Items, evaluations;
- AI-written question formulations (new columns, migration `2a69dc52c3ea`).

## 8. Real-provider workflow and benchmark

`.github/workflows/real-ai.yml`, manual only, cost policy pinned to FREE_ONLY. Inputs:

- **provider:** `groq`, `mistral`, `gemini`, `cloudflare`, `openrouter`, `nvidia`, `cohere`,
  `alibaba_model_studio`, `tencent_tokenhub`, `siliconflow`, or `router` (the whole configured
  free chain with fallback; not for `verify` or `list-models`).
- **operation:**
  - `verify` (default): three stages for one provider and model, via
    `backend/scripts/verify_provider.py`:
    - **A. auth:** the model-listing call with the key. The same call is repeated without the
      key; if that also succeeds the listing is public, and A reports `NOT_VERIFIABLE`.
    - **B. model discovery:** whether the model ID is listed.
    - **C. smoke:** one minimal structured-output call (one question for a two-line item),
      through the app's own provider stack under FREE_ONLY.

    It records provider, requested model, the model the vendor reports serving, latency,
    schema validity and a result class per stage (`OK`, a `FailureKind`, `NOT_LISTED`,
    `REFUSED_BY_POLICY`, `SERVED_BY_OTHER_MODEL`, `SKIPPED`). No credentials, headers or
    bodies. **A pass approves nothing:** it doesn't set `evaluation_approved` and doesn't edit
    the catalog's `verified` flag. Evaluators are approved only after the benchmark below.
  - `list-models`: the IDs the key can use; OpenRouter free ones are marked.
  - `evaluation`, `questions`, `learning_items`, `concept_extraction`, `curriculum`, or `all`.
- **model**, **repeat** (score consistency), **strict**.

It maps `GROQ_API_KEY` etc. onto the generic variables, fails with
`<NAME> is not configured in GitHub Actions Secrets.` when the key is missing, and reports an
HTTP 401/403 by secret name only. Model IDs can be overridden per provider with repository
variables (`GROQ_MODEL`, `MISTRAL_MODEL`, `GEMINI_MODEL`, `CLOUDFLARE_MODEL`,
`OPENROUTER_MODEL`, `NVIDIA_MODEL`, `COHERE_MODEL`), and routes with `AI_ROUTE_*`.

`backend/scripts/ai_benchmark.py` runs nine human-labeled evaluation cases:

1. fully correct
2. correct but incomplete
3. semantically equivalent
4. wrong
5. misconception
6. ambiguous
7. correct by outside knowledge but unsupported by the course source
8. correct with irrelevant additions
9. insufficient source context

It measures:

- classification agreement;
- correctness and completeness consistency (expected ranges);
- misconception detection;
- `context_sufficient` accuracy;
- resolver-outcome agreement;
- schema reliability (first-attempt validity);
- correctness spread across repeats;
- latency.

Results go to the job summary and a JSON artifact (no credentials, and only the fixed
synthetic answers).

**Approval bar** (recommendation only, `APPROVAL` in the script):

- all calls succeed;
- classification and outcome agreement ≥ 8/9;
- `context_sufficient` accuracy and misconception detection 100%;
- first-attempt schema validity ≥ 90%;
- correctness spread ≤ 0.25.

Approving is a manual step: add the model to `AI_EVALUATION_APPROVED_MODELS`. The resolver's
thresholds are global and unchanged. If benchmarks show systematic per-model calibration
differences, the fix is an explicit, versioned per-model calibration, not a quiet global
tweak.

**Question generation comparison.** The `questions` operation runs in Italian and in English,
and reports these heuristic scores next to the question texts:

- grounding: shares key terms with the source;
- source fidelity: no figures that aren't in the source;
- clarity: a real question of sensible length;
- diversity: low overlap between questions;
- language match.

The scores flag problems; a person still reads the questions.

The same nine-case evaluation benchmark applies to every provider and family, including Qwen,
GLM, Kimi and DeepSeek through the gateways. The primary evaluator is chosen only from those
results.

**Order of work once keys exist:**

1. `verify` per provider (and `list-models` when B fails), then fix IDs in
   `app/ai/catalog.py`.
2. `evaluation` with `repeat: 2` for each evaluator candidate.
3. Approve the models that pass, and set `AI_ROUTE_ANSWER_EVALUATION` in the order the results
   support.
4. `questions` / `learning_items` / `curriculum` for generation candidates.
5. `router` with `all` to exercise the whole chain.

## 9. Retrieval stays scoped

Only relevant passages are sent, never whole documents:

- a Concept's own passages for items;
- an item's own passages for questions and evaluation;
- a Chapter's new material for concept extraction.

Retrieval is capped by `AI_MAX_CONTEXT_CHARS`. This keeps quota use, privacy exposure and
grounding under control on free tiers.
