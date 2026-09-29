"""Free-first routing, cost policy and fallback (docs/FREE_AI_ROUTING.md).

No network: the factory's transports are replaced by a recording fake, so every test can assert
exactly which provider/model endpoints were called, and prove that a paid one never was.
"""

import json
import logging

import httpx
import pytest
from pydantic import ValidationError

import app.ai.factory as factory_module
from app.ai.catalog import DEFAULT_ROUTES, RouteOperation, capability
from app.ai.cloudflare import CloudflareWorkersAITransport
from app.ai.factory import build_ai_provider
from app.ai.failures import FailureKind
from app.ai.routing import Candidate, RoutedAIProvider
from app.ai.schemas import EvaluationRequest, SourcePassage
from app.ai.structured import response_schema
from app.ai.transport import ChatCompletion, ChatMessage
from app.core.config import Settings
from app.core.errors import AIUnavailableError, FreeCapacityExhaustedError

STRONG_SECRET = "s" * 48

EVALUATION = {
    "classification": "CORRECT",
    "correctness": 0.95,
    "completeness": 0.9,
    "conceptual_understanding": 0.9,
    "precision": 0.9,
    "confidence": 0.9,
    "correct_points": ["ok"],
    "missing_points": [],
    "misconceptions": [],
    "source_corrections": [],
    "context_sufficient": True,
    "feedback": "Bene.",
}

ALL_KEYS = {
    "ai_groq_api_key": "groq-key",
    "ai_mistral_api_key": "mistral-key",
    "ai_gemini_api_key": "gemini-key",
    "ai_openrouter_api_key": "openrouter-key",
    "ai_nvidia_api_key": "nvidia-key",
    "ai_cloudflare_api_token": "cf-token",
    "ai_cloudflare_account_id": "acct123",
    "ai_cohere_api_key": "cohere-key",
}


class Network:
    """Scripted behavior per model id, and a log of every call (provider base URL, model)."""

    def __init__(self) -> None:
        self.calls: list[tuple[str, str]] = []
        self.failures: dict[str, FailureKind] = {}
        self.clients: list[dict] = []

    def fail(self, model: str, kind: FailureKind) -> None:
        self.failures[model] = kind

    def models_called(self) -> list[str]:
        return [model for _, model in self.calls]


@pytest.fixture
def network(monkeypatch) -> Network:
    net = Network()

    class FakeTransport:
        def __init__(self, **kwargs) -> None:
            self.base_url = kwargs["base_url"]
            net.clients.append(kwargs)

        def complete(
            self, *, model, messages, temperature, max_tokens, json_mode, response_schema=None
        ):
            net.calls.append((self.base_url, model))
            kind = net.failures.get(model)
            if kind is not None:
                raise AIUnavailableError("scripted", details={"failure": kind})
            return ChatCompletion(
                content=json.dumps(EVALUATION), served_model=model, truncated=False
            )

    monkeypatch.setattr(factory_module, "OpenAICompatibleTransport", FakeTransport)
    monkeypatch.setattr(factory_module, "CloudflareWorkersAITransport", FakeTransport)
    return net


def settings(**values) -> Settings:
    return Settings(_env_file=None, auth_secret=STRONG_SECRET, **values)


def router(**values) -> RoutedAIProvider:
    built = build_ai_provider(settings(ai_provider="router", **{**ALL_KEYS, **values}))
    assert isinstance(built, RoutedAIProvider)
    return built


def evaluation_request() -> EvaluationRequest:
    return EvaluationRequest(
        language="it",
        question="Che cos'è il deposito bancario?",
        objective="Definire il deposito",
        expected_knowledge="La banca acquista la proprietà del denaro.",
        essential_points=["proprietà"],
        passages=[SourcePassage("S1", "banca.pdf", 1, None, "La banca acquista la proprietà.")],
        answer="La banca diventa proprietaria del denaro.",
    )


EVALUATION_CHAIN = (
    "groq:openai/gpt-oss-120b,"
    "mistral:mistral-small-latest,"
    "gemini:gemini-2.5-flash,"
    "cloudflare:@cf/nvidia/nemotron-3-120b-a12b"
)


# --- The fallback chain the owner specified ---


def test_groq_quota_exhausted_falls_back_to_mistral(network):
    network.fail("openai/gpt-oss-120b", FailureKind.QUOTA_EXHAUSTED)
    provider = router(ai_route_answer_evaluation=EVALUATION_CHAIN)

    result = provider.evaluate_answer(evaluation_request())

    assert network.models_called() == ["openai/gpt-oss-120b", "mistral-small-latest"]
    assert (result.info.provider, result.info.model) == ("mistral", "mistral-small-latest")
    assert result.info.fallback_index == 1


def test_mistral_unavailable_falls_back_to_gemini_then_the_next_free_provider(network):
    network.fail("openai/gpt-oss-120b", FailureKind.RATE_LIMITED)
    network.fail("mistral-small-latest", FailureKind.PROVIDER_UNAVAILABLE)
    network.fail("gemini-2.5-flash", FailureKind.TIMEOUT)
    provider = router(ai_route_answer_evaluation=EVALUATION_CHAIN)

    result = provider.evaluate_answer(evaluation_request())

    assert network.models_called() == [
        "openai/gpt-oss-120b",
        "mistral-small-latest",
        "gemini-2.5-flash",
        "@cf/nvidia/nemotron-3-120b-a12b",
    ]
    assert result.info.provider == "cloudflare"
    assert result.info.fallback_index == 3


def test_all_free_providers_unavailable_is_free_capacity_exhausted(network):
    for model in (
        "openai/gpt-oss-120b",
        "mistral-small-latest",
        "gemini-2.5-flash",
        "@cf/nvidia/nemotron-3-120b-a12b",
    ):
        network.fail(model, FailureKind.QUOTA_EXHAUSTED)
    provider = router(ai_route_answer_evaluation=EVALUATION_CHAIN)

    with pytest.raises(FreeCapacityExhaustedError) as exc:
        provider.evaluate_answer(evaluation_request())

    assert exc.value.error_type == "free_capacity_exhausted"
    assert [a["provider"] for a in exc.value.details["attempts"]] == [
        "groq",
        "mistral",
        "gemini",
        "cloudflare",
    ]
    assert {a["failure"] for a in exc.value.details["attempts"]} == {"QUOTA_EXHAUSTED"}


def test_free_only_never_touches_a_paid_or_unknown_model(network):
    # Paid and unknown-cost candidates sit at the FRONT of the route, with valid keys.
    route = (
        "openrouter:openai/gpt-4o,"  # OpenRouter without ':free' is the paid variant
        "nvidia:some/unlisted-model,"  # not allowlisted: unknown cost
        "cohere:command-r-unlisted," + EVALUATION_CHAIN  # not in the catalog: unknown cost
    )
    for model in ("openai/gpt-oss-120b", "mistral-small-latest", "gemini-2.5-flash"):
        network.fail(model, FailureKind.QUOTA_EXHAUSTED)
    network.fail("@cf/nvidia/nemotron-3-120b-a12b", FailureKind.RATE_LIMITED)
    provider = router(ai_route_answer_evaluation=route)

    with pytest.raises(FreeCapacityExhaustedError):
        provider.evaluate_answer(evaluation_request())

    called = set(network.models_called())
    assert not called & {"openai/gpt-4o", "some/unlisted-model", "command-r-unlisted"}
    reasons = {e.key: e.reason for e in provider.excluded[RouteOperation.ANSWER_EVALUATION]}
    assert reasons["openrouter:openai/gpt-4o"].startswith("not_free_only_eligible (PAID)")
    assert reasons["nvidia:some/unlisted-model"].startswith("not_free_only_eligible (UNKNOWN)")


def test_free_only_holds_even_for_routes_not_built_by_the_factory():
    """The router re-checks eligibility itself, so no other construction path can bypass it."""

    class Recording:
        called = False

        def evaluate_answer(self, request):
            Recording.called = True
            raise AssertionError("a paid model was called under FREE_ONLY")

    paid = Candidate(capability("openrouter", "openai/gpt-4o"), Recording())  # type: ignore[arg-type]
    provider = RoutedAIProvider({RouteOperation.ANSWER_EVALUATION: [paid]}, cost_policy="FREE_ONLY")

    assert provider.candidates(RouteOperation.ANSWER_EVALUATION) == []
    with pytest.raises(FreeCapacityExhaustedError):
        provider.evaluate_answer(evaluation_request())
    assert Recording.called is False


def test_no_free_candidate_at_all_is_also_free_capacity_exhausted(network):
    provider = router(ai_route_answer_evaluation="openrouter:openai/gpt-4o")
    with pytest.raises(FreeCapacityExhaustedError) as exc:
        provider.evaluate_answer(evaluation_request())
    assert exc.value.details["reason"] == "no_eligible_candidate"
    assert network.calls == []


def test_openrouter_free_suffix_is_kept_and_eligible(network):
    provider = router(
        ai_route_question_generation="openrouter:meta-llama/llama-3.3-70b-instruct:free"
    )
    [candidate] = provider.candidates(RouteOperation.QUESTION_GENERATION)
    assert candidate.model_id.endswith(":free")
    assert capability("openrouter", "meta-llama/llama-3.3-70b-instruct").free_only_eligible is False


def test_a_dynamic_router_is_never_an_evaluator(network):
    provider = router(
        ai_route_answer_evaluation="openrouter:openrouter/free,mistral:mistral-small-latest",
        ai_cost_policy="ANY_CONFIGURED",
    )
    assert [c.key for c in provider.candidates(RouteOperation.ANSWER_EVALUATION)] == [
        "mistral:mistral-small-latest"
    ]


# --- Runtime exclusions ---


def test_auth_failure_disables_the_provider_for_the_run(network, caplog):
    caplog.set_level(logging.INFO)
    network.fail("openai/gpt-oss-120b", FailureKind.AUTH_FAILURE)
    provider = router(ai_route_answer_evaluation=EVALUATION_CHAIN)

    provider.evaluate_answer(evaluation_request())
    provider.evaluate_answer(evaluation_request())

    # Groq was tried once, then skipped on the next call.
    assert network.models_called().count("openai/gpt-oss-120b") == 1
    assert "groq" in provider.disabled_providers
    assert "ai_provider_disabled provider=groq reason=AUTH_FAILURE" in caplog.text
    assert "groq-key" not in caplog.text


def test_model_not_free_is_excluded_for_the_run(network):
    network.fail("@cf/nvidia/nemotron-3-120b-a12b", FailureKind.MODEL_NOT_FREE)
    provider = router(
        ai_route_answer_evaluation="cloudflare:@cf/nvidia/nemotron-3-120b-a12b,mistral:mistral-small-latest"
    )
    provider.evaluate_answer(evaluation_request())
    provider.evaluate_answer(evaluation_request())
    assert network.models_called().count("@cf/nvidia/nemotron-3-120b-a12b") == 1
    assert "cloudflare:@cf/nvidia/nemotron-3-120b-a12b" in provider.not_free_models


# --- Policies ---


def test_free_first_uses_paid_only_after_every_free_candidate(network):
    network.fail("mistral-small-latest", FailureKind.QUOTA_EXHAUSTED)
    provider = router(
        ai_cost_policy="FREE_FIRST",
        ai_route_answer_evaluation="openrouter:openai/gpt-4o,mistral:mistral-small-latest",
    )
    result = provider.evaluate_answer(evaluation_request())
    assert network.models_called() == ["mistral-small-latest", "openai/gpt-4o"]
    assert result.info.model == "openai/gpt-4o"


def test_any_configured_keeps_the_route_order(network):
    provider = router(
        ai_cost_policy="ANY_CONFIGURED",
        ai_route_answer_evaluation="openrouter:openai/gpt-4o,mistral:mistral-small-latest",
    )
    provider.evaluate_answer(evaluation_request())
    assert network.models_called() == ["openai/gpt-4o"]


def test_owner_allowlisted_free_model_becomes_eligible(network):
    provider = router(
        ai_route_question_generation="nvidia:vendor/free-endpoint-model",
        ai_free_models="nvidia:vendor/free-endpoint-model",
    )
    assert [c.model_id for c in provider.candidates(RouteOperation.QUESTION_GENERATION)] == [
        "vendor/free-endpoint-model"
    ]


def test_private_data_policy_excludes_development_only_providers(network):
    provider = router(
        ai_data_policy="private",
        ai_route_question_generation="gemini:gemini-2.5-flash,mistral:mistral-small-latest,mock:mock",
        ai_private_approved_models="mistral:mistral-small-latest",
    )
    kept = [c.key for c in provider.candidates(RouteOperation.QUESTION_GENERATION)]
    assert kept == ["mistral:mistral-small-latest", "mock:mock"]
    reasons = {e.key: e.reason for e in provider.excluded[RouteOperation.QUESTION_GENERATION]}
    assert "DEVELOPMENT_ONLY" in reasons["gemini:gemini-2.5-flash"]


def test_requiring_approved_evaluators(network):
    provider = router(
        ai_evaluation_require_approved=True,
        ai_route_answer_evaluation=EVALUATION_CHAIN,
        ai_evaluation_approved_models="mistral:mistral-small-latest",
    )
    assert [c.key for c in provider.candidates(RouteOperation.ANSWER_EVALUATION)] == [
        "mistral:mistral-small-latest"
    ]


def test_providers_without_credentials_are_skipped(network):
    built = build_ai_provider(
        settings(
            ai_provider="router",
            ai_mistral_api_key="k",
            ai_route_answer_evaluation=EVALUATION_CHAIN,
        )
    )
    assert isinstance(built, RoutedAIProvider)
    assert [c.provider_id for c in built.candidates(RouteOperation.ANSWER_EVALUATION)] == [
        "mistral"
    ]
    reasons = {e.key: e.reason for e in built.excluded[RouteOperation.ANSWER_EVALUATION]}
    assert reasons["groq:openai/gpt-oss-120b"] == "not_configured"


def test_default_routes_only_name_free_eligible_catalog_models(network):
    for operation, route in DEFAULT_ROUTES.items():
        for entry in filter(None, route.split(",")):
            provider_id, _, model = entry.partition(":")
            cap = capability(provider_id, model)
            assert cap.free_only_eligible, f"{operation}: {entry}"
            assert operation in cap.operations or operation is RouteOperation.FEEDBACK_GENERATION


def test_each_provider_gets_its_own_key_and_endpoint(network):
    provider = router(ai_route_answer_evaluation=EVALUATION_CHAIN)
    provider.evaluate_answer(evaluation_request())
    by_url = {c["base_url"]: c for c in network.clients}
    assert by_url["https://api.groq.com/openai/v1"]["api_key"] == "groq-key"
    cloudflare = next(c for c in network.clients if "account_id" in c)
    assert cloudflare["account_id"] == "acct123"


def test_single_provider_mode_uses_the_catalog_endpoint(network):
    built = build_ai_provider(
        settings(ai_provider="groq", ai_model="openai/gpt-oss-120b", ai_api_key="k")
    )
    assert isinstance(built, RoutedAIProvider)
    built.evaluate_answer(evaluation_request())
    assert network.calls == [("https://api.groq.com/openai/v1", "openai/gpt-oss-120b")]


# --- Configuration validation ---


@pytest.mark.parametrize(
    ("values", "message"),
    [
        ({"ai_provider": "router", "ai_route_answer_evaluation": "groq"}, "provider:model"),
        ({"ai_provider": "router", "ai_route_answer_evaluation": "acme:x"}, "unknown provider"),
        ({"ai_provider": "cloudflare", "ai_model": "@cf/x"}, "AI_CLOUDFLARE_ACCOUNT_ID"),
        ({"ai_provider": "mock", "ai_fallback1_provider": "router"}, "only be AI_PROVIDER"),
        ({"ai_cost_policy": "CHEAP"}, "ai_cost_policy"),
    ],
)
def test_invalid_routing_configuration_refuses_to_load(values, message):
    with pytest.raises(ValidationError, match=message):
        settings(**values)


def test_keys_are_masked_in_settings_repr():
    assert "groq-key" not in repr(settings(ai_provider="router", **ALL_KEYS))


# --- Cloudflare Workers AI adapter ---


def cloudflare(handler) -> CloudflareWorkersAITransport:
    client = httpx.Client(transport=httpx.MockTransport(handler))
    return CloudflareWorkersAITransport(
        "https://api.cloudflare.com/client/v4", "acct123", "cf-token", 10, client=client
    )


def cf_complete(transport, schema=True):
    from app.ai.schemas import EvaluationOutput

    return transport.complete(
        model="@cf/zai-org/glm-4.7-flash",
        messages=[ChatMessage("user", "u")],
        temperature=0.1,
        max_tokens=100,
        json_mode=False,
        response_schema=response_schema(EvaluationOutput, strict=False) if schema else None,
    )


def test_cloudflare_request_shape_and_string_response():
    seen = {}

    def handler(req: httpx.Request) -> httpx.Response:
        seen["url"] = str(req.url)
        seen["auth"] = req.headers["authorization"]
        seen["body"] = json.loads(req.content)
        return httpx.Response(200, json={"success": True, "result": {"response": '{"a": 1}'}})

    result = cf_complete(cloudflare(handler))

    assert seen["url"] == (
        "https://api.cloudflare.com/client/v4/accounts/acct123/ai/run/@cf/zai-org/glm-4.7-flash"
    )
    assert seen["auth"] == "Bearer cf-token"
    assert seen["body"]["response_format"]["type"] == "json_schema"
    assert seen["body"]["response_format"]["json_schema"]["type"] == "object"
    assert result.content == '{"a": 1}'


def test_cloudflare_already_parsed_json_and_openai_shaped_results():
    parsed = cf_complete(
        cloudflare(lambda _r: httpx.Response(200, json={"result": {"response": {"a": 1}}}))
    )
    assert json.loads(parsed.content) == {"a": 1}
    shaped = cf_complete(
        cloudflare(
            lambda _r: httpx.Response(
                200,
                json={
                    "result": {
                        "choices": [{"message": {"content": "{}"}, "finish_reason": "length"}]
                    }
                },
            )
        )
    )
    assert shaped.truncated is True


@pytest.mark.parametrize(
    ("status", "body", "failure"),
    [
        (
            429,
            {
                "errors": [
                    {
                        "code": 3036,
                        "message": "You have used up your daily free allocation of 10,000 neurons",
                    }
                ]
            },
            "QUOTA_EXHAUSTED",
        ),
        (403, {"errors": [{"message": "This model requires Workers Paid"}]}, "MODEL_NOT_FREE"),
        (401, {"errors": [{"message": "Authentication error"}]}, "AUTH_FAILURE"),
        (200, {"success": False, "errors": []}, "PROVIDER_UNAVAILABLE"),
    ],
)
def test_cloudflare_failures_are_normalized(status, body, failure):
    with pytest.raises(AIUnavailableError) as exc:
        cf_complete(cloudflare(lambda _r: httpx.Response(status, json=body)))
    assert exc.value.details["failure"] == failure
    assert "neurons" not in json.dumps(exc.value.details)
    assert "cf-token" not in repr(cloudflare(lambda _r: httpx.Response(200)))


# --- Chinese model ecosystems via gateways (docs/FREE_AI_ROUTING.md §2b) ---

GATEWAY_KEYS = {
    "ai_alibaba_model_studio_api_key": "dashscope-key",
    "ai_tencent_tokenhub_api_key": "tokenhub-key",
    "ai_siliconflow_api_key": "siliconflow-key",
    "ai_deepseek_api_key": "deepseek-key",
    "ai_moonshot_api_key": "moonshot-key",
}
QWEN = "alibaba_model_studio:qwen3.8-27b"
KIMI_TENCENT = "tencent_tokenhub:kimi-k3"
DEEPSEEK_TENCENT = "tencent_tokenhub:deepseek/deepseek-flash"


def gateway_router(**values) -> RoutedAIProvider:
    return router(**{**GATEWAY_KEYS, **values})


@pytest.mark.parametrize(
    ("guard", "allowlisted", "eligible"),
    [(False, False, False), (False, True, False), (True, False, False), (True, True, True)],
)
def test_alibaba_needs_free_quota_only_and_an_allowlisted_model(
    network, guard, allowlisted, eligible
):
    provider = gateway_router(
        ai_route_question_generation=QWEN,
        ai_alibaba_free_only_confirmed=guard,
        ai_free_models=QWEN if allowlisted else "",
    )
    kept = [c.key for c in provider.candidates(RouteOperation.QUESTION_GENERATION)]
    assert kept == ([QWEN] if eligible else [])


def test_tencent_needs_payment_disabled_and_an_allowlisted_model(network):
    unguarded = gateway_router(ai_route_answer_evaluation=KIMI_TENCENT, ai_free_models=KIMI_TENCENT)
    assert unguarded.candidates(RouteOperation.ANSWER_EVALUATION) == []
    guarded = gateway_router(
        ai_route_answer_evaluation=KIMI_TENCENT,
        ai_free_models=KIMI_TENCENT,
        ai_tencent_free_only_confirmed=True,
    )
    [candidate] = guarded.candidates(RouteOperation.ANSWER_EVALUATION)
    assert candidate.capability.cost_class == "FREE_CREDITS"


def test_free_quota_exhausted_falls_back_and_excludes_the_model(network):
    network.fail("kimi-k3", FailureKind.FREE_QUOTA_EXHAUSTED)
    provider = gateway_router(
        ai_route_answer_evaluation=f"{KIMI_TENCENT},mistral:mistral-small-latest",
        ai_free_models=KIMI_TENCENT,
        ai_tencent_free_only_confirmed=True,
    )
    first = provider.evaluate_answer(evaluation_request())
    provider.evaluate_answer(evaluation_request())
    assert first.info.provider == "mistral"
    assert network.models_called().count("kimi-k3") == 1
    assert KIMI_TENCENT in provider.not_free_models


@pytest.mark.parametrize(
    ("status", "body"),
    [
        (
            403,
            "The free tier of the model has been exhausted. "
            "Disable 'use free tier only' to continue on a paid basis.",
        ),
        (429, "Your free trial package quota is used up"),
        (400, "AllocationQuota.FreeTierOnly"),
    ],
)
def test_free_quota_messages_are_classified(status, body):
    from app.ai.failures import classify_http

    assert classify_http(status, body) is FailureKind.FREE_QUOTA_EXHAUSTED


def test_siliconflow_small_free_model_does_light_work_but_never_grades_unapproved(network):
    small = "siliconflow:THUDM/GLM-Z1-9B-0414"
    provider = gateway_router(
        ai_route_question_generation=small,
        ai_route_answer_evaluation=small,
        ai_route_learning_item_generation=small,
    )
    assert [c.key for c in provider.candidates(RouteOperation.QUESTION_GENERATION)] == [small]
    assert provider.candidates(RouteOperation.ANSWER_EVALUATION) == []
    assert provider.candidates(RouteOperation.LEARNING_ITEM_GENERATION) == []
    reasons = {e.key: e.reason for e in provider.excluded[RouteOperation.ANSWER_EVALUATION]}
    assert reasons[small] == "small_model_needs_benchmark_approval"
    approved = gateway_router(ai_route_answer_evaluation=small, ai_evaluation_approved_models=small)
    assert [c.key for c in approved.candidates(RouteOperation.ANSWER_EVALUATION)] == [small]


def test_direct_deepseek_is_paid_low_cost_and_never_free_only(network):
    provider = gateway_router(ai_route_answer_evaluation="deepseek:deepseek-flash")
    assert provider.candidates(RouteOperation.ANSWER_EVALUATION) == []
    reasons = {e.key: e.reason for e in provider.excluded[RouteOperation.ANSWER_EVALUATION]}
    assert "PAID_LOW_COST" in reasons["deepseek:deepseek-flash"]


def test_gateway_hosted_deepseek_is_used_before_direct_paid_deepseek(network):
    # Even with direct DeepSeek listed first, FREE_FIRST tries the free gateway first.
    provider = gateway_router(
        ai_cost_policy="FREE_FIRST",
        ai_route_answer_evaluation=f"deepseek:deepseek-flash,{DEEPSEEK_TENCENT}",
        ai_free_models=DEEPSEEK_TENCENT,
        ai_tencent_free_only_confirmed=True,
    )
    result = provider.evaluate_answer(evaluation_request())
    assert network.models_called() == ["deepseek/deepseek-flash"]
    assert result.info.provider == "tencent_tokenhub"


def test_provider_and_model_family_are_separate_dimensions():
    via_gateway = capability("tencent_tokenhub", "kimi-k3")
    direct = capability("moonshot", "kimi-k3")
    assert via_gateway.model_family == direct.model_family == "kimi"
    assert via_gateway.provider_id != direct.provider_id
    assert via_gateway.cost_class == "FREE_CREDITS"
    assert direct.cost_class == "PAID"
    assert capability("siliconflow", "THUDM/GLM-Z1-9B-0414").model_family == "glm"
    assert capability("alibaba_model_studio", "qwen3.8-27b").model_family == "qwen"


def test_alibaba_singapore_endpoint_and_optional_workspace(network):
    provider = gateway_router(
        ai_route_question_generation=QWEN,
        ai_alibaba_free_only_confirmed=True,
        ai_free_models=QWEN,
        ai_alibaba_workspace_id="ws-123",
    )
    provider.candidates(RouteOperation.QUESTION_GENERATION)
    [client] = [c for c in network.clients if "dashscope" in c["base_url"]]
    assert client["base_url"] == "https://dashscope-intl.aliyuncs.com/compatible-mode/v1"
    assert client["extra_headers"]["X-DashScope-WorkSpace"] == "ws-123"
    assert client["api_key"] == "dashscope-key"


def test_tokenhub_uses_the_international_endpoint(network):
    provider = gateway_router(
        ai_route_question_generation=KIMI_TENCENT,
        ai_free_models=KIMI_TENCENT,
        ai_tencent_free_only_confirmed=True,
    )
    provider.candidates(RouteOperation.QUESTION_GENERATION)
    assert any(c["base_url"] == "https://tokenhub-intl.tencentmaas.com/v1" for c in network.clients)


def test_openrouter_paid_ids_cannot_be_allowlisted_into_free_only():
    cap = capability(
        "openrouter", "openai/gpt-4o", free_models=frozenset({"openrouter:openai/gpt-4o"})
    )
    assert cap.free_only_eligible is False


def test_billing_guards_default_to_off():
    loaded = settings()
    assert loaded.ai_alibaba_free_only_confirmed is False
    assert loaded.ai_tencent_free_only_confirmed is False


def test_a_successful_call_never_makes_an_unguarded_provider_eligible(network):
    # Billing safety comes only from the owner's confirmation, never from API behavior: an
    # allowlisted but unguarded Tencent model stays excluded however well other calls go.
    provider = gateway_router(
        ai_route_answer_evaluation=f"{KIMI_TENCENT},mistral:mistral-small-latest",
        ai_free_models=KIMI_TENCENT,
    )
    for _ in range(3):
        provider.evaluate_answer(evaluation_request())
    assert "kimi-k3" not in network.models_called()
    assert [c.key for c in provider.candidates(RouteOperation.ANSWER_EVALUATION)] == [
        "mistral:mistral-small-latest"
    ]
