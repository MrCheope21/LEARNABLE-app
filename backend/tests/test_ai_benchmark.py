"""The real-provider benchmark and model listing (scripts/ai_benchmark.py, scripts/list_models.py).

They only earn their keep when run against real providers, so they are exercised here against
the mock and scripted HTTP to keep them working between those runs.
"""

import importlib.util
import json
from pathlib import Path

import httpx
import pytest

from app.ai.catalog import RouteOperation, capability
from app.ai.provider import LLMAIProvider, ModelSettings
from app.ai.routing import Candidate, RoutedAIProvider
from app.ai.transport import OpenAICompatibleTransport
from app.core.config import Settings

SCRIPTS = Path(__file__).resolve().parents[1] / "scripts"


def load(name: str):
    spec = importlib.util.spec_from_file_location(name, SCRIPTS / f"{name}.py")
    assert spec
    assert spec.loader
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


benchmark = load("ai_benchmark")
list_models = load("list_models")


@pytest.fixture
def mock_env(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("AI_PROVIDER", "mock")


def test_self_test_runs_every_operation_and_the_nine_labeled_cases(mock_env, tmp_path):
    report = tmp_path / "report.json"

    assert benchmark.main(["--allow-mock", "--repeat", "2", "--json", str(report)]) == 0

    payload = json.loads(report.read_text())
    operations = {r["operation"] for r in payload["results"]}
    assert operations == {
        "generate_curriculum",
        "generate_chapter_curriculum",
        "generate_learning_items",
        "generate_questions",
        "evaluate_answer",
    }
    evaluated = [r for r in payload["results"] if r["operation"] == "evaluate_answer"]
    assert len(evaluated) == 9 * 2
    assert {r["name"] for r in evaluated} == {f"evaluate_{n}" for n in benchmark.EVALUATION_CASES}
    metrics = payload["metrics"]
    assert metrics["calls_succeeded"] == 18
    assert metrics["max_correctness_spread"] == 0.0  # deterministic mock
    assert all(r["prompt_version"] and r["provider"] == "mock" for r in payload["results"])


def test_the_approval_bar_really_discriminates(mock_env):
    # A keyword-overlap evaluator can't spot a paraphrase, a misconception or missing context.
    assert benchmark.main(["--allow-mock", "--operations", "evaluation", "--strict"]) == 1


def test_mock_is_refused_without_the_self_test_flag(mock_env):
    assert benchmark.main([]) == 2


def test_a_paid_or_unknown_model_is_refused_before_any_call(monkeypatch, capsys):
    monkeypatch.setenv("AI_PROVIDER", "deepseek")
    monkeypatch.setenv("AI_BASE_URL", "https://llm.invalid/v1")
    monkeypatch.setenv("AI_MODEL", "deepseek-chat")
    monkeypatch.setenv("AI_API_KEY", "sk-this-must-never-be-printed")

    assert benchmark.main(["--operations", "evaluation"]) == 2

    err = capsys.readouterr().err
    assert "not_free_only_eligible" in err
    assert "sk-this-must-never-be-printed" not in err


def test_a_rejected_credential_is_reported_by_name_only(monkeypatch, capsys):
    monkeypatch.setenv("AI_PROVIDER", "groq")
    monkeypatch.setenv("AI_MODEL", "openai/gpt-oss-120b")
    monkeypatch.setenv("AI_API_KEY", "gsk-this-must-never-be-printed")
    unauthorized = httpx.Client(transport=httpx.MockTransport(lambda _: httpx.Response(401)))

    def build(settings: Settings) -> RoutedAIProvider:
        llm = LLMAIProvider(
            provider_name="groq",
            transport=OpenAICompatibleTransport(
                "https://llm.invalid/v1",
                settings.ai_api_key.get_secret_value(),
                5,
                client=unauthorized,
            ),
            settings=ModelSettings("openai/gpt-oss-120b", {}, 0, 100, True),
        )
        cap = capability("groq", "openai/gpt-oss-120b")
        return RoutedAIProvider(
            {op: [Candidate(cap, llm)] for op in RouteOperation}, cost_policy="FREE_ONLY"
        )

    monkeypatch.setattr(benchmark, "build_ai_provider", build)

    assert benchmark.main(["--operations", "evaluation", "--credential-name", "GROQ_API_KEY"]) == 1

    out = capsys.readouterr()
    assert "Authentication failed for provider 'groq': check GROQ_API_KEY." in out.err
    assert "gsk-this-must-never-be-printed" not in out.out + out.err


# --- list_models ---


def settings(**values) -> Settings:
    return Settings(_env_file=None, auth_secret="s" * 48, **values)


def test_openrouter_listing_marks_free_models():
    def handler(request: httpx.Request) -> httpx.Response:
        assert request.url.path == "/api/v1/models"
        return httpx.Response(
            200,
            json={
                "data": [
                    {"id": "x/model:free", "pricing": {"prompt": "0", "completion": "0"}},
                    {"id": "x/model", "pricing": {"prompt": "0.000001", "completion": "0.000002"}},
                ]
            },
        )

    client = httpx.Client(transport=httpx.MockTransport(handler))
    ids = list_models.model_ids(
        settings(ai_provider="openrouter", ai_model="x", ai_api_key="k"), client
    )
    assert ids == ["x/model", "x/model:free  [free]"]


def test_cloudflare_listing_uses_the_account_search():
    seen = {}

    def handler(request: httpx.Request) -> httpx.Response:
        seen["path"] = request.url.path
        return httpx.Response(
            200,
            json={
                "result": [
                    {"name": "@cf/zai-org/glm-4.7-flash", "properties": []},
                    {
                        "name": "@cf/x/beta",
                        "properties": [{"property_id": "beta", "value": "true"}],
                    },
                ]
            },
        )

    client = httpx.Client(transport=httpx.MockTransport(handler))
    ids = list_models.model_ids(
        settings(
            ai_provider="cloudflare",
            ai_model="@cf/x",
            ai_api_key="t",
            ai_cloudflare_account_id="acct",
        ),
        client,
    )
    assert seen["path"] == "/client/v4/accounts/acct/ai/models/search"
    assert ids == ["@cf/x/beta  [beta]", "@cf/zai-org/glm-4.7-flash"]
