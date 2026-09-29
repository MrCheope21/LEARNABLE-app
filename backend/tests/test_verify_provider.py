"""scripts/verify_provider.py: auth, model discovery, structured-output smoke (scripted HTTP)."""

import json

import httpx
import pytest

from app.ai.catalog import RouteOperation, capability
from app.ai.provider import LLMAIProvider, ModelSettings
from app.ai.routing import Candidate, RoutedAIProvider
from app.ai.transport import OpenAICompatibleTransport
from app.core.config import Settings
from tests.test_ai_benchmark import load

verify = load("verify_provider")

KEY = "gsk-this-must-never-be-printed"
MODEL = "openai/gpt-oss-120b"
QUESTIONS = {
    "context_sufficient": True,
    "questions": [{"question_type": "RECALL", "text": "At what temperature does water boil?"}],
}


@pytest.fixture(autouse=True)
def groq_env(monkeypatch):
    monkeypatch.setenv("AI_PROVIDER", "groq")
    monkeypatch.setenv("AI_MODEL", MODEL)
    monkeypatch.setenv("AI_API_KEY", KEY)


class Vendor:
    """A scripted OpenAI-compatible vendor that records every call."""

    def __init__(self, *, listing=200, public=False, models=(MODEL,), content=QUESTIONS):
        self.listing, self.public, self.models, self.content = listing, public, models, content
        self.chat_calls = 0

    def __call__(self, request: httpx.Request) -> httpx.Response:
        authorized = request.headers.get("authorization") == f"Bearer {KEY}"
        if request.url.path.endswith("/models"):
            if not authorized and not self.public:
                return httpx.Response(401, json={"error": {"message": "missing key"}})
            if self.listing != 200:
                return httpx.Response(self.listing, json={"error": {"message": "invalid api key"}})
            return httpx.Response(200, json={"data": [{"id": m} for m in self.models]})
        self.chat_calls += 1
        body = self.content if isinstance(self.content, str) else json.dumps(self.content)
        return httpx.Response(
            200,
            json={
                "model": f"{MODEL}-2026-09",
                "choices": [{"message": {"content": body}, "finish_reason": "stop"}],
            },
        )

    def client(self) -> httpx.Client:
        return httpx.Client(transport=httpx.MockTransport(self))

    def build(self, provider_id="groq", model=MODEL):
        def _build(settings: Settings) -> RoutedAIProvider:
            llm = LLMAIProvider(
                provider_name=provider_id,
                transport=OpenAICompatibleTransport(
                    "https://llm.invalid/v1", KEY, 5, client=self.client()
                ),
                settings=ModelSettings(model, {}, 0, 500, True),
            )
            candidate = Candidate(capability(provider_id, model), llm)
            return RoutedAIProvider(
                {op: [candidate] for op in RouteOperation}, cost_policy="FREE_ONLY"
            )

        return _build


def run(vendor: Vendor, tmp_path, capsys, build=None):
    out = tmp_path / "verify.json"
    code = verify.main(
        ["--json", str(out), "--credential-name", "GROQ_API_KEY"],
        client=vendor.client(),
        build=build or vendor.build(),
    )
    printed = capsys.readouterr()
    assert KEY not in printed.out + printed.err
    assert KEY not in out.read_text()
    return code, json.loads(out.read_text()), printed


def test_all_three_stages_pass_and_nothing_is_approved(tmp_path, capsys):
    vendor = Vendor()
    code, report, printed = run(vendor, tmp_path, capsys)

    assert code == 0
    assert report["passed"] is True
    assert report["auth"]["result"] == "OK"
    assert report["discovery"]["result"] == "OK"
    assert report["smoke"]["result"] == "OK"
    assert report["schema_valid"] is True
    assert report["provider"] == "groq"
    assert report["requested_model"] == MODEL
    assert report["returned_model"] == f"{MODEL}-2026-09"
    assert report["smoke"]["latency_ms"] is not None
    assert vendor.chat_calls == 1
    # A pass approves nothing.
    assert report["catalog"]["evaluation_approved"] is False
    assert report["evaluation_approved_changed"] is False
    assert "a smoke pass is not an evaluation approval" in printed.out


def test_a_rejected_key_stops_before_any_model_call(tmp_path, capsys):
    vendor = Vendor(listing=401)
    code, report, printed = run(vendor, tmp_path, capsys)

    assert code == 1
    assert report["auth"]["result"] == "AUTH_FAILURE"
    assert report["auth"]["http_status"] == 401
    assert report["discovery"]["result"] == "SKIPPED"
    assert report["smoke"]["result"] == "SKIPPED"
    assert vendor.chat_calls == 0
    assert "The provider rejected GROQ_API_KEY." in printed.err


def test_a_public_listing_does_not_count_as_an_auth_check(tmp_path, capsys):
    code, report, _ = run(Vendor(public=True), tmp_path, capsys)

    assert report["auth"]["result"] == "NOT_VERIFIABLE"
    assert report["smoke"]["result"] == "OK"  # stage C is what proves the key here
    assert code == 0


def test_an_unlisted_model_fails_discovery(tmp_path, capsys):
    code, report, _ = run(Vendor(models=("llama-3.3-70b-versatile",)), tmp_path, capsys)

    assert code == 1
    assert report["discovery"]["result"] == "NOT_LISTED"


def test_invalid_structured_output_is_reported_as_such(tmp_path, capsys):
    code, report, _ = run(Vendor(content="not json at all"), tmp_path, capsys)

    assert code == 1
    assert report["smoke"]["result"] == "INVALID_STRUCTURED_OUTPUT"
    assert report["schema_valid"] is False


def test_a_paid_model_is_refused_before_any_call(tmp_path, capsys, monkeypatch):
    monkeypatch.setenv("AI_PROVIDER", "deepseek")
    monkeypatch.setenv("AI_MODEL", "deepseek-chat")
    monkeypatch.setenv("AI_BASE_URL", "https://llm.invalid/v1")
    vendor = Vendor(models=("deepseek-chat",))

    code, report, _ = run(vendor, tmp_path, capsys, build=vendor.build("deepseek", "deepseek-chat"))

    assert code == 1
    assert report["smoke"]["result"] == "REFUSED_BY_POLICY"
    assert vendor.chat_calls == 0


def test_the_real_stack_is_used_by_default(monkeypatch, tmp_path, capsys):
    """Without an injected builder the app's own factory (and FREE_ONLY policy) is used."""
    monkeypatch.setenv("AI_PROVIDER", "deepseek")
    monkeypatch.setenv("AI_MODEL", "deepseek-chat")
    monkeypatch.setenv("AI_BASE_URL", "https://llm.invalid/v1")
    vendor = Vendor(models=("deepseek-chat",))
    out = tmp_path / "v.json"

    assert verify.main(["--json", str(out)], client=vendor.client()) == 1
    smoke = json.loads(out.read_text())["smoke"]
    assert smoke["result"] == "REFUSED_BY_POLICY"
    assert "not_free_only_eligible" in smoke["detail"]
    assert vendor.chat_calls == 0
