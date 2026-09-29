"""What each runtime provider/model is, costs and may be used for (docs/FREE_AI_ROUTING.md §2).

Routing decisions read this table; nothing else in the app knows vendor names. An entry is a
claim about the vendor's current terms, so every entry records whether it has been verified
against a live call (`verified`). None has been yet: this repository's sandbox can't reach the
vendors, so the IDs come from the owner's research and must be confirmed with the Real AI
validation workflow (`operation: list-models`, then the benchmark).

A model that is not in this table is UNKNOWN cost and never runs under AI_COST_POLICY=FREE_ONLY
unless the owner lists it in AI_FREE_MODELS after checking the vendor's terms. OpenRouter has
one rule instead of entries: an ID ending in ":free" is the free variant (the suffix is never
stripped); anything else is paid.
"""

from dataclasses import dataclass, field, replace
from enum import StrEnum

from app.ai.provider import StructuredOutput

__all__ = ["StructuredOutput"]


_FAMILIES = (
    ("qwen", "qwen"),
    ("deepseek", "deepseek"),
    ("kimi", "kimi"),
    ("moonshot", "kimi"),
    ("glm", "glm"),
    ("thudm", "glm"),
    ("zhipu", "glm"),
    ("minimax", "minimax"),
    ("abab", "minimax"),
    ("hunyuan", "hunyuan"),
    ("gpt-oss", "gpt-oss"),
    ("gemma", "gemma"),
    ("gemini", "gemini"),
    ("nemotron", "nemotron"),
    ("mistral", "mistral"),
    ("llama", "llama"),
    ("command", "cohere-command"),
    ("mock", "mock"),
)


def model_family(model_id: str) -> str:
    """The model's maker/family from its ID, independent of the serving provider."""
    lowered = model_id.lower()
    for needle, family in _FAMILIES:
        if needle in lowered:
            return family
    return "unknown"


class CostClass(StrEnum):
    FREE_RECURRING = "FREE_RECURRING"  # a free allowance that renews (daily/monthly)
    FREE_LIMITED = "FREE_LIMITED"  # free, but small or unguaranteed capacity
    FREE_TRIAL = "FREE_TRIAL"  # free for a period or needs a payment method: not free-only
    # Temporary new-user quota/credits (e.g. ~90 days). Free-only eligible ONLY when the model is
    # allowlisted and, on gateways that could fall through to paid use, the owner has confirmed
    # the provider's billing guard (Free Quota Only / payment disabled).
    FREE_CREDITS = "FREE_CREDITS"
    PAID_LOW_COST = "PAID_LOW_COST"
    PAID = "PAID"
    UNKNOWN = "UNKNOWN"


class PrivacyClass(StrEnum):
    PRIVATE_APPROVED = "PRIVATE_APPROVED"  # the owner reviewed the terms for private material
    DEVELOPMENT_ONLY = "DEVELOPMENT_ONLY"  # e.g. content may be used to improve the product
    UNKNOWN = "UNKNOWN"  # terms not reviewed for private material


class TransportKind(StrEnum):
    OPENAI_COMPATIBLE = "openai_compatible"
    CLOUDFLARE = "cloudflare"
    MOCK = "mock"


class RouteOperation(StrEnum):
    """Routing keys. Each maps to one AIProvider operation, except FEEDBACK_GENERATION, which is
    reserved: feedback is currently produced inside answer evaluation, not by its own call."""

    CURRICULUM_GENERATION = "CURRICULUM_GENERATION"  # Course-scope proposal
    CONCEPT_EXTRACTION = "CONCEPT_EXTRACTION"  # Chapter-scope: topics/concepts from new material
    LEARNING_ITEM_GENERATION = "LEARNING_ITEM_GENERATION"
    QUESTION_GENERATION = "QUESTION_GENERATION"
    ANSWER_EVALUATION = "ANSWER_EVALUATION"
    FEEDBACK_GENERATION = "FEEDBACK_GENERATION"


ALL_OPERATIONS = frozenset(RouteOperation)
# Inexpensive work a small free model may do: simple questions, extraction, feedback. Grading
# is allowed only after benchmark approval (evaluation_requires_approval).
LIGHT_OPERATIONS = frozenset(
    {
        RouteOperation.QUESTION_GENERATION,
        RouteOperation.CONCEPT_EXTRACTION,
        RouteOperation.FEEDBACK_GENERATION,
        RouteOperation.ANSWER_EVALUATION,
    }
)
GENERATION = frozenset(
    {
        RouteOperation.CURRICULUM_GENERATION,
        RouteOperation.CONCEPT_EXTRACTION,
        RouteOperation.LEARNING_ITEM_GENERATION,
        RouteOperation.QUESTION_GENERATION,
    }
)


@dataclass(frozen=True)
class ProviderSpec:
    provider_id: str
    transport: TransportKind
    # None: the endpoint must be configured (AI_BASE_URL or AI_<ID>_BASE_URL).
    default_base_url: str | None
    extra_headers: dict[str, str] = field(default_factory=dict)
    notes: str = ""
    # Setting the owner must turn on to confirm the provider can't bill after its free quota
    # (e.g. Alibaba "Free Quota Only"). Until then none of its models is free-only eligible.
    billing_guard: str | None = None


@dataclass(frozen=True)
class ModelCapability:
    provider_id: str
    model_id: str
    operations: frozenset[RouteOperation]
    supports_json: bool
    supports_json_schema: bool
    supports_strict_json_schema: bool
    openai_compatible: bool
    cost_class: CostClass
    privacy_class: PrivacyClass
    free_only_eligible: bool
    # Set only after the evaluation benchmark passes (docs/FREE_AI_ROUTING.md §8).
    evaluation_approved: bool = False
    verified: bool = False
    notes: str = ""
    # Who made the model (qwen, glm, kimi, deepseek, ...), as opposed to who serves it
    # (provider_id). The same family can be served by several providers.
    model_family: str = ""
    # Small/cheap models: never used for grading until the benchmark approves them.
    evaluation_requires_approval: bool = False

    def __post_init__(self) -> None:
        if not self.model_family:
            object.__setattr__(self, "model_family", model_family(self.model_id))

    @property
    def key(self) -> str:
        return f"{self.provider_id}:{self.model_id}"

    @property
    def supports_question_generation(self) -> bool:
        return RouteOperation.QUESTION_GENERATION in self.operations

    @property
    def supports_learning_item_generation(self) -> bool:
        return RouteOperation.LEARNING_ITEM_GENERATION in self.operations

    @property
    def supports_curriculum_generation(self) -> bool:
        return RouteOperation.CURRICULUM_GENERATION in self.operations

    @property
    def supports_evaluation(self) -> bool:
        return RouteOperation.ANSWER_EVALUATION in self.operations

    @property
    def structured_output(self) -> StructuredOutput:
        if self.supports_strict_json_schema:
            return StructuredOutput.JSON_SCHEMA_STRICT
        if self.supports_json_schema:
            return StructuredOutput.JSON_SCHEMA
        if self.supports_json:
            return StructuredOutput.JSON_OBJECT
        return StructuredOutput.NONE


PROVIDERS: dict[str, ProviderSpec] = {
    spec.provider_id: spec
    for spec in [
        ProviderSpec("mock", TransportKind.MOCK, None, notes="Deterministic, offline."),
        ProviderSpec("groq", TransportKind.OPENAI_COMPATIBLE, "https://api.groq.com/openai/v1"),
        ProviderSpec("mistral", TransportKind.OPENAI_COMPATIBLE, "https://api.mistral.ai/v1"),
        ProviderSpec(
            "gemini",
            TransportKind.OPENAI_COMPATIBLE,
            "https://generativelanguage.googleapis.com/v1beta/openai/",
            notes="Free tier: Google may use content to improve its products.",
        ),
        ProviderSpec(
            "openrouter",
            TransportKind.OPENAI_COMPATIBLE,
            "https://openrouter.ai/api/v1",
            extra_headers={"X-Title": "Learnable"},
            notes="Only ':free' model IDs are free; small daily allowance on free accounts.",
        ),
        ProviderSpec(
            "nvidia",
            TransportKind.OPENAI_COMPATIBLE,
            "https://integrate.api.nvidia.com/v1",
            notes="Not every hosted NIM model is free: only allowlisted Free Endpoints run "
            "under FREE_ONLY (AI_FREE_MODELS).",
        ),
        ProviderSpec(
            "cloudflare",
            TransportKind.CLOUDFLARE,
            "https://api.cloudflare.com/client/v4",
            notes="Needs AI_CLOUDFLARE_ACCOUNT_ID. Free daily allocation; some models need "
            "Workers Paid.",
        ),
        ProviderSpec(
            "cohere",
            TransportKind.OPENAI_COMPATIBLE,
            "https://api.cohere.ai/compatibility/v1",
            notes="Trial keys: benchmark only, not production capacity.",
        ),
        # --- Chinese model ecosystems: gateways first (docs/FREE_AI_ROUTING.md §2b) ---
        ProviderSpec(
            "alibaba_model_studio",
            TransportKind.OPENAI_COMPATIBLE,
            # Singapore (international) region: where new-user free quotas apply.
            "https://dashscope-intl.aliyuncs.com/compatible-mode/v1",
            notes="Serves Qwen, DeepSeek, Kimi, GLM, MiniMax. New-user free quota per model, "
            "temporary (~90 days). Without 'Free Quota Only' it continues as pay-as-you-go.",
            billing_guard="AI_ALIBABA_FREE_ONLY_CONFIRMED",
        ),
        ProviderSpec(
            "tencent_tokenhub",
            TransportKind.OPENAI_COMPATIBLE,
            "https://tokenhub-intl.tencentmaas.com/v1",
            notes="Serves DeepSeek, GLM, Kimi, MiniMax, Qwen, Hunyuan. New-user free trial "
            "packages for eligible models; post-paid billing must stay disabled.",
            billing_guard="AI_TENCENT_FREE_ONLY_CONFIRMED",
        ),
        ProviderSpec(
            "siliconflow",
            TransportKind.OPENAI_COMPATIBLE,
            "https://api.siliconflow.com/v1",
            notes="Mixes paid and genuinely free models: only allowlisted free ones are "
            "free-only eligible.",
        ),
        # Direct vendor APIs: paid (or temporary credits). Not in FREE_ONLY by default.
        ProviderSpec(
            "deepseek",
            TransportKind.OPENAI_COMPATIBLE,
            "https://api.deepseek.com/v1",
            notes="Direct API is paid (low cost). Prefer free gateway-hosted DeepSeek first.",
        ),
        ProviderSpec(
            "moonshot",
            TransportKind.OPENAI_COMPATIBLE,
            "https://api.moonshot.ai/v1",
            notes="Direct Kimi API: pay-as-you-go.",
        ),
        ProviderSpec(
            "zai",
            TransportKind.OPENAI_COMPATIBLE,
            "https://api.z.ai/api/paas/v4",
            notes="Direct GLM API: promotional credits at most (FREE_CREDITS when allowlisted).",
        ),
        ProviderSpec(
            "minimax",
            TransportKind.OPENAI_COMPATIBLE,
            "https://api.minimax.io/v1",
            notes="Direct MiniMax API: paid.",
        ),
        # Pre-routing labels: OpenAI-compatible endpoints the owner configures fully.
        ProviderSpec("openai_compatible", TransportKind.OPENAI_COMPATIBLE, None),
        ProviderSpec("qwen", TransportKind.OPENAI_COMPATIBLE, None),
        ProviderSpec("kimi", TransportKind.OPENAI_COMPATIBLE, None),
        ProviderSpec("glm", TransportKind.OPENAI_COMPATIBLE, None),
    ]
}

# Providers whose credentials the router reads (AI_<ID>_API_KEY, Cloudflare: API token).
ROUTABLE_PROVIDERS = (
    "groq",
    "mistral",
    "gemini",
    "openrouter",
    "nvidia",
    "cloudflare",
    "cohere",
    "alibaba_model_studio",
    "tencent_tokenhub",
    "siliconflow",
    "deepseek",
    "moonshot",
    "zai",
    "minimax",
)


def _model(
    provider: str,
    model: str,
    *,
    operations: frozenset[RouteOperation] = ALL_OPERATIONS,
    json_schema: bool = True,
    strict: bool = False,
    cost: CostClass = CostClass.FREE_RECURRING,
    privacy: PrivacyClass = PrivacyClass.UNKNOWN,
    notes: str = "",
    evaluation_requires_approval: bool = False,
) -> ModelCapability:
    return ModelCapability(
        provider_id=provider,
        model_id=model,
        operations=operations,
        supports_json=True,
        supports_json_schema=json_schema or strict,
        supports_strict_json_schema=strict,
        openai_compatible=PROVIDERS[provider].transport is TransportKind.OPENAI_COMPATIBLE,
        cost_class=cost,
        privacy_class=privacy,
        free_only_eligible=cost in (CostClass.FREE_RECURRING, CostClass.FREE_LIMITED),
        notes=notes,
        evaluation_requires_approval=evaluation_requires_approval,
    )


# Candidates from the owner's research (2026-09). Not benchmarked, not live-verified.
MODELS: dict[str, ModelCapability] = {
    m.key: m
    for m in [
        ModelCapability(
            provider_id="mock",
            model_id="mock",
            operations=ALL_OPERATIONS,
            supports_json=True,
            supports_json_schema=True,
            supports_strict_json_schema=True,
            openai_compatible=False,
            cost_class=CostClass.FREE_RECURRING,
            privacy_class=PrivacyClass.PRIVATE_APPROVED,
            free_only_eligible=True,
            verified=True,
            notes="Offline, deterministic, never leaves the server.",
        ),
        _model("groq", "openai/gpt-oss-120b", strict=True, notes="Preferred evaluator candidate."),
        _model(
            "groq",
            "qwen/qwen3.8-27b",
            strict=True,
            notes="Question-generation candidate; confirm the exact ID with list-models.",
        ),
        _model("mistral", "mistral-small-latest", strict=True, notes="Free (Experiment) plan."),
        _model(
            "gemini",
            "gemini-3.5-flash-lite",
            privacy=PrivacyClass.DEVELOPMENT_ONLY,
            notes="Verified live 2026-09-29 and benchmarked (9/9 cases). Free tier content may be "
            "used by Google: development/demo material only.",
        ),
        _model(
            "gemini",
            "gemini-3.5-flash",
            privacy=PrivacyClass.DEVELOPMENT_ONLY,
            notes="Verified live 2026-09-29. Small free daily allowance; free tier content may be "
            "used by Google.",
        ),
        _model(
            "gemini",
            "gemini-2.5-flash",
            privacy=PrivacyClass.DEVELOPMENT_ONLY,
            notes="Free tier content may be used by Google: development/demo material only.",
        ),
        _model(
            "gemini",
            "gemini-2.5-flash-lite",
            privacy=PrivacyClass.DEVELOPMENT_ONLY,
            notes="Free tier content may be used by Google: development/demo material only.",
        ),
        _model(
            "nvidia",
            "openai/gpt-oss-20b",
            json_schema=False,
            cost=CostClass.FREE_LIMITED,
            notes="Last resort. Owner-approved 2026-09-29 as free (NVIDIA API Catalog); passed the "
            "grading benchmark in JSON mode but takes 25-50 s per call.",
        ),
        _model("cloudflare", "@cf/zai-org/glm-4.7-flash"),
        _model("cloudflare", "@cf/google/gemma-4-26b-a4b-it"),
        _model("cloudflare", "@cf/nvidia/nemotron-3-120b-a12b"),
        # Gateways for Chinese model families. FREE_CREDITS: eligible only when allowlisted AND
        # the provider's billing guard is confirmed (see capability()).
        _model(
            "alibaba_model_studio",
            "qwen3.8-27b",
            cost=CostClass.FREE_CREDITS,
            notes="Singapore new-user free quota; confirm with list-models and the console.",
        ),
        _model("tencent_tokenhub", "glm-5.3-flash", cost=CostClass.FREE_CREDITS),
        _model("tencent_tokenhub", "kimi-k3", cost=CostClass.FREE_CREDITS),
        _model("tencent_tokenhub", "deepseek/deepseek-flash", cost=CostClass.FREE_CREDITS),
        _model(
            "siliconflow",
            "THUDM/GLM-Z1-9B-0414",
            operations=LIGHT_OPERATIONS,
            json_schema=False,
            notes="Free small model: light work only; grading needs benchmark approval.",
            evaluation_requires_approval=True,
        ),
        _model("deepseek", "deepseek-flash", cost=CostClass.PAID_LOW_COST),
        _model("moonshot", "kimi-k3", cost=CostClass.PAID),
        _model("zai", "glm-5.3-flash", cost=CostClass.FREE_CREDITS),
        _model(
            "cohere",
            "command-a-03-2025",
            operations=frozenset({RouteOperation.ANSWER_EVALUATION}),
            json_schema=False,
            cost=CostClass.FREE_LIMITED,
            notes="Independent evaluation benchmark; trial key limits.",
        ),
    ]
}

OPENROUTER_FREE_SUFFIX = ":free"


def capability(
    provider_id: str,
    model_id: str,
    *,
    free_models: frozenset[str] = frozenset(),
    private_approved: frozenset[str] = frozenset(),
    evaluation_approved: frozenset[str] = frozenset(),
    billing_guards: frozenset[str] = frozenset(),
) -> ModelCapability:
    """The capability of provider:model, with the owner's allowlists applied (AI_FREE_MODELS,
    AI_PRIVATE_APPROVED_MODELS, AI_EVALUATION_APPROVED_MODELS) and the providers whose billing
    guard the owner confirmed (`billing_guards`)."""
    key = f"{provider_id}:{model_id}"
    known = MODELS.get(key)
    if known is not None:
        base = known
    elif provider_id == "openrouter" and model_id.endswith(OPENROUTER_FREE_SUFFIX):
        base = _model(
            "openrouter",
            model_id,
            cost=CostClass.FREE_LIMITED,
            notes="OpenRouter free variant (':free' kept).",
        )
    elif key in free_models and provider_id != "openrouter":
        # (An OpenRouter ID without ':free' is the paid variant: never allowlistable.)
        spec = PROVIDERS.get(provider_id)
        base = ModelCapability(
            provider_id=provider_id,
            model_id=model_id,
            operations=ALL_OPERATIONS,
            supports_json=True,
            supports_json_schema=False,
            supports_strict_json_schema=False,
            openai_compatible=spec is not None
            and spec.transport is TransportKind.OPENAI_COMPATIBLE,
            cost_class=CostClass.FREE_LIMITED,
            privacy_class=PrivacyClass.UNKNOWN,
            free_only_eligible=True,
            notes="Allowlisted free by the owner (AI_FREE_MODELS).",
        )
    else:
        spec = PROVIDERS.get(provider_id)
        base = ModelCapability(
            provider_id=provider_id,
            model_id=model_id,
            operations=ALL_OPERATIONS,
            supports_json=True,
            supports_json_schema=False,
            supports_strict_json_schema=False,
            openai_compatible=spec is not None
            and spec.transport is TransportKind.OPENAI_COMPATIBLE,
            cost_class=CostClass.PAID if provider_id == "openrouter" else CostClass.UNKNOWN,
            privacy_class=PrivacyClass.UNKNOWN,
            free_only_eligible=False,
        )
    spec = PROVIDERS.get(provider_id)
    if key in free_models and not base.free_only_eligible and base.cost_class is not CostClass.PAID:
        # The owner verified this model's free quota/credits (never an OpenRouter paid ID:
        # those are PAID by rule and can't be allowlisted into FREE_ONLY).
        base = replace(base, cost_class=CostClass.FREE_CREDITS, free_only_eligible=True)
    if spec is not None and spec.billing_guard is not None:
        # A gateway whose free quota can roll over into paid use: free-only needs BOTH the
        # confirmed guard and an allowlisted model, whatever the catalog says.
        guarded = provider_id in billing_guards and key in free_models
        base = replace(base, free_only_eligible=guarded)
    if key in private_approved:
        base = replace(base, privacy_class=PrivacyClass.PRIVATE_APPROVED)
    if key in evaluation_approved:
        base = replace(base, evaluation_approved=True)
    return base


def is_dynamic_router(provider_id: str, model_id: str) -> bool:
    """Models that pick a different underlying model per call (e.g. OpenRouter's routers):
    never acceptable as an evaluator, whose results must be attributable (spec §74)."""
    return provider_id == "openrouter" and model_id.startswith("openrouter/")


# NVIDIA gpt-oss-20b is the last resort everywhere: it passed the grading benchmark but takes
# 25-50 s per call, and it only runs when AI_FREE_MODELS lists it (NVIDIA free status is
# owner-verified, never assumed).
# Default routes for AI_PROVIDER=router, used when AI_ROUTE_<OPERATION> is empty. PROVISIONAL:
# the order is the owner's initial candidate list, not a benchmark result. Re-order from the
# Real AI benchmark (docs/FREE_AI_ROUTING.md §8) by setting AI_ROUTE_* rather than trusting this.
_GENERATION_DEFAULT = (
    "gemini:gemini-3.5-flash-lite,"
    "mistral:mistral-small-latest,"
    "groq:openai/gpt-oss-120b,"
    "cloudflare:@cf/zai-org/glm-4.7-flash,"
    "nvidia:openai/gpt-oss-20b"
)
DEFAULT_ROUTES: dict[RouteOperation, str] = {
    RouteOperation.CURRICULUM_GENERATION: _GENERATION_DEFAULT,
    RouteOperation.CONCEPT_EXTRACTION: _GENERATION_DEFAULT,
    RouteOperation.LEARNING_ITEM_GENERATION: _GENERATION_DEFAULT,
    RouteOperation.QUESTION_GENERATION: (
        "gemini:gemini-3.5-flash-lite,"
        "mistral:mistral-small-latest,"
        "groq:qwen/qwen3.8-27b,"
        "cloudflare:@cf/zai-org/glm-4.7-flash,"
        "nvidia:openai/gpt-oss-20b"
    ),
    RouteOperation.ANSWER_EVALUATION: (
        "gemini:gemini-3.5-flash-lite,"
        "groq:openai/gpt-oss-120b,"
        "mistral:mistral-small-latest,"
        "cloudflare:@cf/nvidia/nemotron-3-120b-a12b,"
        "nvidia:openai/gpt-oss-20b"
    ),
    RouteOperation.FEEDBACK_GENERATION: "",
}
