"""Three-stage check of one real provider and model (docs/FREE_AI_ROUTING.md §8).

    AI_PROVIDER=groq AI_MODEL=openai/gpt-oss-120b AI_API_KEY=... \\
        python scripts/verify_provider.py --credential-name GROQ_API_KEY --json verify.json

A. auth       the vendor's model-listing endpoint, with the key (free). The same call is also
              made without the key: if that succeeds too, the endpoint is public and stage A
              proves nothing about the key (NOT_VERIFIABLE); stage C still does.
B. discovery  whether AI_MODEL is among the models the listing returned.
C. smoke      one minimal structured-output call (generate one question for a two-line item)
              through the application's own provider stack and FREE_ONLY policy. Skipped when
              the key was rejected or the policy refuses the model before any call.

Records provider, requested model, the model the vendor reports serving, latency, schema
validity and a result class per stage. Never prints the key, request or response headers, or
response bodies. A passing smoke test approves nothing: evaluation approval is the owner's
decision after the benchmark (AI_EVALUATION_APPROVED_MODELS), and catalog `verified` flags are
edited by hand.
"""

import argparse
import json
import sys
import time
from collections.abc import Callable
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import httpx

from app.ai.catalog import PROVIDERS, RouteOperation, TransportKind
from app.ai.factory import build_ai_provider
from app.ai.failures import classify_http, failure_of
from app.ai.provider import AIProvider
from app.ai.routing import RoutedAIProvider
from app.ai.schemas import QuestionsRequest, SourcePassage
from app.core.config import AI_PROVIDER_MOCK, AI_PROVIDER_ROUTER, Settings
from app.core.errors import AppError
from app.models.enums import QuestionType

OK = "OK"
NOT_VERIFIABLE = "NOT_VERIFIABLE"
NOT_LISTED = "NOT_LISTED"
SKIPPED = "SKIPPED"
REFUSED_BY_POLICY = "REFUSED_BY_POLICY"
SERVED_BY_OTHER_MODEL = "SERVED_BY_OTHER_MODEL"

SMOKE_REQUEST = QuestionsRequest(
    course_title="Smoke test",
    concept_title="Water",
    item_title="Boiling point of water",
    objective="Know the boiling point of water at sea level.",
    expected_knowledge="At sea level, pure water boils at 100 degrees Celsius.",
    essential_points=["100 degrees Celsius", "at sea level"],
    question_types=[QuestionType.RECALL],
    count=1,
    language="en",
    passages=[
        SourcePassage(
            ref="S1",
            document_name="smoke.md",
            page_number=None,
            section=None,
            text="At sea level, pure water boils at 100 degrees Celsius.",
        )
    ],
    existing_questions=[],
)


@dataclass
class Stage:
    result: str
    latency_ms: int | None = None
    http_status: int | None = None
    detail: str = ""


@dataclass
class Report:
    provider: str
    requested_model: str
    returned_model: str | None = None
    catalog: dict[str, Any] = field(default_factory=dict)
    auth: Stage | None = None
    discovery: Stage | None = None
    smoke: Stage | None = None
    schema_valid: bool | None = None
    # Never changed by this script; reported so a reader can't mistake a pass for approval.
    evaluation_approved_changed: bool = False

    @property
    def passed(self) -> bool:
        return (
            self.auth is not None
            and self.auth.result in (OK, NOT_VERIFIABLE)
            and self.discovery is not None
            and self.discovery.result == OK
            and self.smoke is not None
            and self.smoke.result == OK
        )


def listing_request(settings: Settings) -> tuple[str, dict[str, Any]]:
    spec = PROVIDERS[settings.ai_provider]
    base = (settings.ai_base_url or spec.default_base_url or "").rstrip("/")
    if spec.transport is TransportKind.CLOUDFLARE:
        url = f"{base}/accounts/{settings.ai_cloudflare_account_id}/ai/models/search"
        return url, {"task": "Text Generation", "per_page": 200}
    return f"{base}/models", {}


def model_ids(settings: Settings, payload: Any) -> set[str]:
    if PROVIDERS[settings.ai_provider].transport is TransportKind.CLOUDFLARE:
        return {str(m.get("name")) for m in payload.get("result", [])}
    entries = (
        (payload.get("data") or payload.get("models") or [])
        if isinstance(payload, dict)
        else payload
    )
    ids = {str(m.get("id") or m.get("name")) for m in entries if isinstance(m, dict)}
    # Gemini lists "models/<id>"; the OpenAI-compatible endpoint is called with "<id>".
    return ids | {i.removeprefix("models/") for i in ids}


def check_auth_and_discovery(settings: Settings, client: httpx.Client, report: Report) -> None:
    url, params = listing_request(settings)
    key = settings.ai_api_key.get_secret_value()
    started = time.monotonic()
    try:
        response = client.get(url, params=params, headers={"Authorization": f"Bearer {key}"})
    except httpx.HTTPError:
        report.auth = Stage("PROVIDER_UNAVAILABLE", detail="the provider couldn't be reached")
        report.discovery = Stage(SKIPPED)
        return
    latency = round((time.monotonic() - started) * 1000)
    if response.status_code >= 400:
        # The body is used only to classify; it is never printed.
        kind = classify_http(response.status_code, response.text)
        report.auth = Stage(kind.value, latency, response.status_code)
        report.discovery = Stage(SKIPPED)
        return

    try:
        anonymous = client.get(url, params=params).status_code < 400
    except httpx.HTTPError:
        anonymous = False
    report.auth = (
        Stage(NOT_VERIFIABLE, latency, response.status_code, "the listing is public")
        if anonymous
        else Stage(OK, latency, response.status_code)
    )
    try:
        ids = model_ids(settings, response.json())
    except ValueError:
        report.discovery = Stage("PROVIDER_UNAVAILABLE", detail="the listing wasn't JSON")
        return
    listed = settings.ai_model in ids
    report.discovery = Stage(OK if listed else NOT_LISTED, detail=f"{len(ids)} models listed")


def check_smoke(provider: AIProvider | None, report: Report) -> None:
    if report.auth is not None and report.auth.result == "AUTH_FAILURE":
        report.smoke = Stage(SKIPPED, detail="the key was rejected")
        return
    if not isinstance(provider, RoutedAIProvider):
        report.smoke = Stage(SKIPPED, detail="no provider stack for this configuration")
        return
    operation = RouteOperation.QUESTION_GENERATION
    candidates = provider.candidates(operation)
    if candidates:
        capability = candidates[0].capability
        report.catalog = {
            "cost_class": capability.cost_class.value,
            "free_only_eligible": capability.free_only_eligible,
            "evaluation_approved": capability.evaluation_approved,
            "catalog_verified": capability.verified,
            "model_family": capability.model_family,
        }
    else:
        reasons = [e.reason for e in provider.excluded.get(operation, [])]
        report.smoke = Stage(
            REFUSED_BY_POLICY, detail=", ".join(reasons) or "no eligible candidate"
        )
        return

    started = time.monotonic()
    try:
        result = provider.generate_questions(SMOKE_REQUEST)
    except AppError as exc:
        kind = _failure(exc)
        report.schema_valid = False if kind == "INVALID_STRUCTURED_OUTPUT" else None
        report.smoke = Stage(kind, round((time.monotonic() - started) * 1000), detail=exc.message)
        return
    info = result.info
    report.returned_model = info.model_version
    report.schema_valid = True  # the output was parsed and validated against the schema
    if info.model != report.requested_model or info.fallback_index != 0:
        report.smoke = Stage(
            SERVED_BY_OTHER_MODEL,
            info.latency_ms,
            detail=f"answered by {info.provider}:{info.model}",
        )
        return
    questions = len(result.output.questions)
    report.smoke = Stage(OK, info.latency_ms, detail=f"{questions} question(s)")


def _failure(exc: AppError) -> str:
    """The vendor-level failure: the router reports it per attempt, under `attempts`."""
    attempts = (exc.details or {}).get("attempts") or []
    if attempts and attempts[-1].get("failure"):
        return str(attempts[-1]["failure"])
    return failure_of(exc).value


def render(report: Report) -> str:
    lines = [
        f"Provider:        {report.provider}",
        f"Requested model: {report.requested_model}",
        f"Returned model:  {report.returned_model or '-'}",
    ]
    for name, stage in (("A auth", report.auth), ("B discovery", report.discovery)):
        lines.append(_stage_line(name, stage))
    lines.append(_stage_line("C smoke", report.smoke))
    lines.append(f"Schema valid:    {_yes_no(report.schema_valid)}")
    if report.catalog:
        lines.append(
            "Catalog:         " + ", ".join(f"{k}={v}" for k, v in sorted(report.catalog.items()))
        )
    lines.append("evaluation_approved is unchanged: a smoke pass is not an evaluation approval.")
    lines.append(f"Overall:         {'PASS' if report.passed else 'FAIL'}")
    return "\n".join(lines)


def _stage_line(name: str, stage: Stage | None) -> str:
    if stage is None:
        return f"{name:<16} -"
    parts = [stage.result]
    if stage.http_status is not None:
        parts.append(f"HTTP {stage.http_status}")
    if stage.latency_ms is not None:
        parts.append(f"{stage.latency_ms} ms")
    if stage.detail:
        parts.append(stage.detail)
    return f"{name + ':':<16} " + " · ".join(parts)


def _yes_no(value: bool | None) -> str:
    return "-" if value is None else ("yes" if value else "no")


def main(
    argv: list[str] | None = None,
    client: httpx.Client | None = None,
    build: Callable[[Settings], AIProvider | None] = build_ai_provider,
) -> int:
    parser = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    parser.add_argument("--json", type=Path, help="write the JSON report here")
    parser.add_argument(
        "--credential-name",
        default="the configured API key",
        help="name of the credential source, used only in messages",
    )
    args = parser.parse_args(argv)

    settings = Settings()
    if settings.ai_provider in ("", AI_PROVIDER_MOCK, AI_PROVIDER_ROUTER) or (
        settings.ai_provider not in PROVIDERS
    ):
        print("Set AI_PROVIDER to one catalog provider and AI_MODEL to one model.", file=sys.stderr)
        return 2
    if not settings.ai_model or not settings.ai_api_key.get_secret_value():
        print(f"AI_MODEL and {args.credential_name} are required.", file=sys.stderr)
        return 2

    report = Report(provider=settings.ai_provider, requested_model=settings.ai_model)
    with client or httpx.Client(timeout=30) as http:
        check_auth_and_discovery(settings, http, report)
    check_smoke(build(settings), report)

    print(render(report))
    if args.json:
        payload = asdict(report) | {"passed": report.passed}
        args.json.write_text(json.dumps(payload, indent=2), encoding="utf-8")
    if report.auth is not None and report.auth.result == "AUTH_FAILURE":
        print(f"The provider rejected {args.credential_name}.", file=sys.stderr)
    return 0 if report.passed else 1


if __name__ == "__main__":
    raise SystemExit(main())
