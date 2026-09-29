"""Builds the configured AIProvider (docs/AI.md §3, docs/FREE_AI_ROUTING.md). The only place that
reads AI_* settings.

- AI_PROVIDER empty: AI off (None).
- AI_PROVIDER=mock: the deterministic MockAIProvider.
- AI_PROVIDER=<one provider> (+ AI_FALLBACK1/2): that chain, used for every operation.
- AI_PROVIDER=router: per-operation routes (AI_ROUTE_* or the catalog defaults) over every
  provider that has credentials.

Both non-mock modes produce a RoutedAIProvider, so the cost and data policies apply the same way
and a model excluded by policy is never given a client.
"""

import logging
from collections.abc import Callable
from functools import lru_cache

from pydantic import SecretStr

from app.ai.catalog import (
    DEFAULT_ROUTES,
    PROVIDERS,
    ModelCapability,
    RouteOperation,
    StructuredOutput,
    TransportKind,
    capability,
)
from app.ai.cloudflare import CloudflareWorkersAITransport
from app.ai.mock import MockAIProvider
from app.ai.provider import AIProvider, LLMAIProvider, ModelSettings
from app.ai.routing import Candidate, Exclusion, RoutedAIProvider, select_candidates
from app.ai.transport import ChatTransport, OpenAICompatibleTransport
from app.core.config import (
    AI_PROVIDER_MOCK,
    AI_PROVIDER_ROUTER,
    Settings,
    get_settings,
    parse_model_list,
)

logger = logging.getLogger(__name__)

_EVALUATION_OPERATIONS = {RouteOperation.ANSWER_EVALUATION, RouteOperation.FEEDBACK_GENERATION}


def build_ai_provider(settings: Settings) -> AIProvider | None:
    if not settings.ai_provider:
        return None
    if settings.ai_provider == AI_PROVIDER_MOCK:
        return MockAIProvider()
    return _Builder(settings).build()


class _Builder:
    def __init__(self, settings: Settings) -> None:
        self.s = settings
        self.free = frozenset(f"{p}:{m}" for p, m in parse_model_list(settings.ai_free_models))
        self.private = frozenset(
            f"{p}:{m}" for p, m in parse_model_list(settings.ai_private_approved_models)
        )
        self.approved = frozenset(
            f"{p}:{m}" for p, m in parse_model_list(settings.ai_evaluation_approved_models)
        )
        guards = {
            "alibaba_model_studio": settings.ai_alibaba_free_only_confirmed,
            "tencent_tokenhub": settings.ai_tencent_free_only_confirmed,
        }
        self.guards = frozenset(provider for provider, confirmed in guards.items() if confirmed)
        # One transport (HTTP client) per provider endpoint, shared by its models.
        self._transports: dict[tuple[str, str], ChatTransport] = {}

    def build(self) -> RoutedAIProvider:
        routes: dict[RouteOperation, list[Candidate]] = {}
        excluded: dict[RouteOperation, list[Exclusion]] = {}
        for operation in RouteOperation:
            planned, not_configured = self._plan(operation)
            kept, dropped = select_candidates(
                operation,
                planned,
                cost_policy=self.s.ai_cost_policy,
                data_policy=self.s.ai_data_policy,
                require_approved_evaluator=self.s.ai_evaluation_require_approved,
            )
            routes[operation] = kept
            excluded[operation] = not_configured + dropped
            logger.info(
                "ai_routes operation=%s policy=%s candidates=%s excluded=%s",
                operation,
                self.s.ai_cost_policy,
                ",".join(c.key for c in kept) or "none",
                ",".join(f"{e.key}({e.reason})" for e in excluded[operation]) or "none",
            )
        return RoutedAIProvider(routes, cost_policy=self.s.ai_cost_policy, excluded=excluded)

    # --- planning: which provider:model pairs, with what credentials ---

    def _plan(
        self, operation: RouteOperation
    ) -> tuple[list[tuple[ModelCapability, Callable[[], AIProvider]]], list[Exclusion]]:
        if self.s.ai_provider == AI_PROVIDER_ROUTER:
            return self._plan_router(operation)
        return self._plan_single(operation), []

    def _plan_router(
        self, operation: RouteOperation
    ) -> tuple[list[tuple[ModelCapability, Callable[[], AIProvider]]], list[Exclusion]]:
        configured = getattr(self.s, f"ai_route_{operation.value.lower()}")
        entries = parse_model_list(configured or DEFAULT_ROUTES[operation])
        planned: list[tuple[ModelCapability, Callable[[], AIProvider]]] = []
        missing: list[Exclusion] = []
        for provider_id, model in entries:
            cap = self._capability(provider_id, model)
            if provider_id == AI_PROVIDER_MOCK:
                planned.append((cap, MockAIProvider))
                continue
            credential, base_url = self._router_credentials(provider_id)
            if credential is None or base_url is None:
                missing.append(Exclusion(cap.key, "not_configured"))
                continue
            planned.append((cap, self._llm(provider_id, base_url, credential, model, cap)))
        return planned, missing

    def _plan_single(
        self, operation: RouteOperation
    ) -> list[tuple[ModelCapability, Callable[[], AIProvider]]]:
        s = self.s
        group_model = (
            s.ai_model_evaluation if operation in _EVALUATION_OPERATIONS else s.ai_model_generation
        )
        chain = [(s.ai_provider, s.ai_base_url, s.ai_api_key, group_model or s.ai_model)]
        # Fallbacks use their one model for every operation (per-operation models tune the
        # primary).
        for provider, base_url, key, model in (
            (
                s.ai_fallback1_provider,
                s.ai_fallback1_base_url,
                s.ai_fallback1_api_key,
                s.ai_fallback1_model,
            ),
            (
                s.ai_fallback2_provider,
                s.ai_fallback2_base_url,
                s.ai_fallback2_api_key,
                s.ai_fallback2_model,
            ),
        ):
            if provider:
                chain.append((provider, base_url, key, model))
        planned: list[tuple[ModelCapability, Callable[[], AIProvider]]] = []
        for provider_id, base_url, key, model in chain:
            if provider_id == AI_PROVIDER_MOCK:
                planned.append((self._capability("mock", "mock"), MockAIProvider))
                continue
            cap = self._capability(provider_id, model)
            url = base_url or PROVIDERS[provider_id].default_base_url or ""
            planned.append((cap, self._llm(provider_id, url, key, model, cap)))
        return planned

    def _capability(self, provider_id: str, model: str) -> ModelCapability:
        return capability(
            provider_id,
            model,
            free_models=self.free,
            private_approved=self.private,
            evaluation_approved=self.approved,
            billing_guards=self.guards,
        )

    def _router_credentials(self, provider_id: str) -> tuple[SecretStr | None, str | None]:
        field = (
            "ai_cloudflare_api_token"
            if provider_id == "cloudflare"
            else f"ai_{provider_id}_api_key"
        )
        key: SecretStr | None = getattr(self.s, field, None)
        if key is None or not key.get_secret_value():
            return None, None
        if provider_id == "cloudflare" and not self.s.ai_cloudflare_account_id.strip():
            return None, None
        override = getattr(self.s, f"ai_{provider_id}_base_url", "")
        return key, override or PROVIDERS[provider_id].default_base_url

    # --- clients ---

    def _llm(
        self,
        provider_id: str,
        base_url: str,
        key: SecretStr,
        model: str,
        cap: ModelCapability,
    ) -> Callable[[], AIProvider]:
        def build() -> AIProvider:
            structured = cap.structured_output if self.s.ai_json_mode else StructuredOutput.NONE
            return LLMAIProvider(
                provider_name=provider_id,
                transport=self._transport(provider_id, base_url, key),
                settings=ModelSettings(
                    default_model=model,
                    group_models={},
                    temperature=self.s.ai_temperature,
                    max_tokens=self.s.ai_max_tokens,
                    json_mode=self.s.ai_json_mode,
                    structured=structured,
                ),
            )

        return build

    def _transport(self, provider_id: str, base_url: str, key: SecretStr) -> ChatTransport:
        cache_key = (provider_id, base_url)
        if cache_key not in self._transports:
            spec = PROVIDERS[provider_id]
            if spec.transport is TransportKind.CLOUDFLARE:
                self._transports[cache_key] = CloudflareWorkersAITransport(
                    base_url=base_url,
                    account_id=self.s.ai_cloudflare_account_id.strip(),
                    api_token=key.get_secret_value(),
                    timeout=self.s.ai_timeout,
                )
            else:
                headers = dict(spec.extra_headers)
                if provider_id == "alibaba_model_studio" and self.s.ai_alibaba_workspace_id.strip():
                    headers["X-DashScope-WorkSpace"] = self.s.ai_alibaba_workspace_id.strip()
                self._transports[cache_key] = OpenAICompatibleTransport(
                    base_url=base_url,
                    api_key=key.get_secret_value(),
                    timeout=self.s.ai_timeout,
                    extra_headers=headers,
                )
        return self._transports[cache_key]


@lru_cache
def get_ai_provider() -> AIProvider | None:
    """FastAPI dependency. Returns None instead of raising, so an endpoint can check the
    caller's Course ownership first: an intruder gets 404, never a 503 that confirms the id."""
    return build_ai_provider(get_settings())
