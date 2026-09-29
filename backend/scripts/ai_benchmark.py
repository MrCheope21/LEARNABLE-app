"""Benchmarks the configured runtime AI provider/model (docs/FREE_AI_ROUTING.md §8).

    AI_PROVIDER=groq AI_MODEL=openai/gpt-oss-120b AI_API_KEY=... \\
        python scripts/ai_benchmark.py --operations evaluation --repeat 2 \\
        --report report.md --json report.json

Reads the same generic AI_* settings as the server and goes through the same router, so the
cost policy applies: under AI_COST_POLICY=FREE_ONLY (the default) a model that isn't
free-only eligible is refused before any call. It never learns where a key came from.

Operations: curriculum (Course scope), concept_extraction (Chapter scope), learning_items,
questions, evaluation. Evaluation runs a fixed, human-labeled case set: fully correct, correct
but incomplete, semantically equivalent, wrong, misconception, ambiguous, correct by outside
knowledge but unsupported by the course source, correct with irrelevant additions, and a
question the source can't answer. Each case has expected classifications, score ranges,
context sufficiency and allowed resolver outcomes; the report measures agreement per metric,
schema reliability (valid on the first attempt), score spread across --repeat runs, and
latency, then states whether the model meets the approval bar. Approval itself is a manual
step (AI_EVALUATION_APPROVED_MODELS): this script only recommends.

Nothing sensitive is printed or stored: no key, no header, no prompt text. Student answers in
the report are the fixed synthetic cases below.

Exit status: 0 when every call succeeded (and, with --strict, the approval bar is met);
1 on a failed call or, with --strict, a missed bar; 2 on configuration refused.
"""

import argparse
import json
import statistics
import sys
import time
from collections.abc import Callable
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import re

from app.ai.catalog import RouteOperation, model_family
from app.ai.factory import build_ai_provider
from app.ai.provider import AICallInfo, AIProvider
from app.ai.routing import RoutedAIProvider
from app.ai.schemas import (
    ChapterCurriculumRequest,
    CurriculumRequest,
    EvaluationOutput,
    EvaluationRequest,
    ExistingConcept,
    ExistingTopic,
    LearningItemsRequest,
    QuestionsRequest,
    SourcePassage,
)
from app.core.config import AI_PROVIDER_MOCK, Settings
from app.core.errors import AppError
from app.models.enums import EvaluationClassification as C
from app.models.enums import QuestionType
from app.services.evaluation.resolver import resolve_outcome

LANGUAGE = "it"
COURSE = "Diritto bancario"
CHAPTER = "Contratti bancari"

DEPOSIT = SourcePassage(
    ref="S1",
    document_name="contratti_bancari.pdf",
    page_number=12,
    section="Il deposito bancario",
    text=(
        "Il deposito bancario è il contratto con cui la banca acquista la proprietà delle somme "
        "di denaro depositate e si obbliga a restituirle nella stessa specie monetaria alla "
        "scadenza del termine convenuto oppure a richiesta del depositante. Poiché la banca "
        "diventa proprietaria del denaro, può utilizzarlo per la propria attività."
    ),
)
CREDIT_LINE = SourcePassage(
    ref="S2",
    document_name="contratti_bancari.pdf",
    page_number=13,
    section="L'apertura di credito",
    text=(
        "L'apertura di credito è il contratto con cui la banca si obbliga a tenere a "
        "disposizione del cliente una somma di denaro per un dato periodo di tempo o a tempo "
        "indeterminato. Il cliente può utilizzare la somma in più volte e, salvo patto "
        "contrario, può ripristinare la disponibilità con successivi versamenti."
    ),
)
PASSAGES = [DEPOSIT, CREDIT_LINE]

DEPOSIT_EN = SourcePassage(
    ref="S1",
    document_name="banking_contracts.pdf",
    page_number=12,
    section="Bank deposits",
    text=(
        "A bank deposit is the contract by which the bank acquires ownership of the sums of "
        "money deposited and undertakes to return them in the same currency at the agreed "
        "term or on the depositor's demand. Because the bank becomes the owner of the money, "
        "it may use it for its own business."
    ),
)
ESSENTIAL_EN = [
    "The bank acquires ownership of the deposited money",
    "The bank must return the same currency",
    "Repayment is due at the term or on the depositor's demand",
]

QUESTION = "Che cos'è il deposito bancario e quali sono i suoi effetti principali?"
OBJECTIVE = "Definire il deposito bancario e i suoi effetti"
ESSENTIAL = [
    "La banca acquista la proprietà del denaro depositato",
    "La banca deve restituire la stessa specie monetaria",
    "La restituzione avviene alla scadenza o a richiesta del depositante",
]
FULL_ANSWER = (
    "Il deposito bancario è il contratto con cui la banca acquista la proprietà del denaro "
    "depositato e si obbliga a restituire la stessa specie monetaria alla scadenza oppure a "
    "richiesta del depositante."
)


@dataclass(frozen=True)
class Case:
    """A human-labeled evaluation case. Ranges are inclusive; None means "not checked"."""

    answer: str
    classifications: frozenset[C]
    outcomes: frozenset[str | None]
    context_sufficient: bool | None = True
    correctness: tuple[float, float] | None = None
    completeness: tuple[float, float] | None = None
    # True: misconceptions must be reported; False: none may be; None: not checked.
    misconception: bool | None = None
    question: str = QUESTION
    objective: str = OBJECTIVE
    expected_knowledge: str = DEPOSIT.text
    essential_points: tuple[str, ...] = tuple(ESSENTIAL)
    passages: tuple[SourcePassage, ...] = (DEPOSIT,)


EVALUATION_CASES: dict[str, Case] = {
    "fully_correct": Case(
        FULL_ANSWER,
        frozenset({C.CORRECT}),
        frozenset({"GOOD", "EASY"}),
        correctness=(0.8, 1.0),
        completeness=(0.75, 1.0),
        misconception=False,
    ),
    "correct_incomplete": Case(
        "È un contratto in cui la banca diventa proprietaria del denaro che le viene depositato.",
        frozenset({C.PARTIALLY_CORRECT}),
        frozenset({"HARD", "AGAIN"}),
        correctness=(0.6, 1.0),
        completeness=(0.0, 0.6),
        misconception=False,
    ),
    "semantically_equivalent": Case(
        "Chi deposita trasferisce alla banca il denaro, che diventa suo e può usarlo; in cambio "
        "la banca deve ridare al cliente la stessa valuta quando scade il termine o quando lui "
        "la chiede indietro.",
        frozenset({C.CORRECT}),
        frozenset({"GOOD", "EASY", "HARD"}),
        correctness=(0.75, 1.0),
        completeness=(0.6, 1.0),
        misconception=False,
    ),
    "wrong": Case(
        "È il contratto con cui la banca si impegna a tenere a disposizione del cliente una "
        "somma che il cliente può utilizzare in più volte.",
        frozenset({C.WRONG, C.MISCONCEPTION}),
        frozenset({"AGAIN"}),
        correctness=(0.0, 0.35),
    ),
    "misconception": Case(
        "Con il deposito bancario la banca custodisce il denaro del cliente, che ne resta "
        "proprietario: la banca non può usarlo e deve restituire esattamente le stesse banconote.",
        frozenset({C.MISCONCEPTION, C.WRONG}),
        frozenset({"AGAIN"}),
        correctness=(0.0, 0.5),
        misconception=True,
    ),
    "ambiguous": Case(
        "Riguarda i soldi in banca.",
        frozenset({C.UNCERTAIN, C.WRONG, C.PARTIALLY_CORRECT}),
        frozenset({None, "AGAIN"}),
        context_sufficient=None,
        correctness=(0.0, 0.5),
    ),
    "external_unsupported": Case(
        "Il deposito bancario è disciplinato dagli articoli 1834 e seguenti del codice civile ed "
        "è garantito dal Fondo interbancario di tutela dei depositi fino a 100.000 euro.",
        frozenset({C.PARTIALLY_CORRECT, C.WRONG, C.UNCERTAIN}),
        frozenset({None, "AGAIN", "HARD"}),
        context_sufficient=None,
        correctness=(0.0, 0.6),
    ),
    "correct_with_irrelevant": Case(
        FULL_ANSWER + " Inoltre molte banche hanno sportelli automatici aperti 24 ore su 24.",
        frozenset({C.CORRECT}),
        frozenset({"GOOD", "EASY"}),
        correctness=(0.75, 1.0),
        completeness=(0.75, 1.0),
        misconception=False,
    ),
    "insufficient_context": Case(
        "Il 2,5% annuo.",
        frozenset(C),
        frozenset({None}),
        context_sufficient=False,
        question="Qual è il tasso di interesse legale in vigore quest'anno?",
        objective="Conoscere il tasso di interesse legale",
        expected_knowledge="(non presente nel materiale)",
        essential_points=(),
        passages=(CREDIT_LINE,),
    ),
}

# The approval bar (docs/FREE_AI_ROUTING.md §8). Recommendation only; approving is manual.
APPROVAL = {
    "classification_agreement": 8 / 9,
    "outcome_agreement": 8 / 9,
    "context_sufficient_accuracy": 1.0,
    "misconception_detection": 1.0,
    "first_attempt_schema_validity": 0.9,
    "max_correctness_spread": 0.25,
}

OPERATIONS = ("curriculum", "concept_extraction", "learning_items", "questions", "evaluation")


@dataclass
class CaseResult:
    name: str
    operation: str
    run: int
    ok: bool
    expectation_met: bool | None = None
    summary: str = ""
    checks: dict[str, bool] = field(default_factory=dict)
    scores: dict[str, Any] = field(default_factory=dict)
    provider: str | None = None
    model: str | None = None
    # Who made the model, separate from who served it (provider).
    model_family: str | None = None
    model_version: str | None = None
    prompt_version: str | None = None
    latency_ms: int | None = None
    attempts: int | None = None
    fallback_index: int | None = None
    error_type: str | None = None
    failure: str | None = None


def _info(result: CaseResult, info: AICallInfo) -> None:
    result.provider = info.provider
    result.model = info.model
    result.model_family = model_family(info.model)
    result.model_version = info.model_version
    result.prompt_version = info.prompt_version
    result.latency_ms = info.latency_ms
    result.attempts = info.attempts
    result.fallback_index = info.fallback_index


def _run(name: str, operation: str, run: int, call: Callable[[CaseResult], None]) -> CaseResult:
    result = CaseResult(name=name, operation=operation, run=run, ok=False)
    started = time.monotonic()
    try:
        call(result)
        result.ok = True
    except AppError as exc:
        # AppError messages are written to be safe to show (no content, no keys).
        result.error_type = exc.error_type
        failure = (exc.details or {}).get("failure")
        attempts = (exc.details or {}).get("attempts") or []
        if not failure and attempts:
            failure = attempts[-1].get("failure")
        result.failure = str(failure) if failure else None
        result.summary = exc.message
    if result.latency_ms is None:
        result.latency_ms = round((time.monotonic() - started) * 1000)
    return result


_STOPWORDS = {
    "it": {
        "il",
        "la",
        "di",
        "che",
        "è",
        "un",
        "una",
        "per",
        "del",
        "della",
        "con",
        "non",
        "le",
        "si",
    },
    "en": {"the", "of", "and", "is", "to", "a", "in", "what", "which", "how", "does", "why", "an"},
}
_WORD = re.compile(r"[a-zàèéìòù]+")
_NUMBER = re.compile(r"\d+(?:[.,]\d+)?")


def question_quality(texts: list[str], source: str, language: str) -> dict[str, Any]:
    """Cheap, reproducible heuristics for comparing question generators. They flag problems
    (off-language, ungrounded, repetitive, invented figures); they don't replace reading the
    questions, which the JSON report keeps for that purpose."""
    if not texts:
        metrics = ("grounding", "source_fidelity", "clarity", "diversity", "language_match")
        return {**dict.fromkeys(metrics, 0.0), "questions": []}
    source_words = {w for w in _WORD.findall(source.lower()) if len(w) >= 5}
    source_numbers = set(_NUMBER.findall(source))
    other = "en" if language == "it" else "it"

    def words(text: str) -> list[str]:
        return _WORD.findall(text.lower())

    grounded = sum(1 for t in texts if {w for w in words(t) if len(w) >= 5} & source_words)
    faithful = sum(1 for t in texts if set(_NUMBER.findall(t)) <= source_numbers)
    clear = sum(1 for t in texts if t.endswith("?") and 5 <= len(t.split()) <= 45)
    in_language = sum(
        1
        for t in texts
        if len(set(words(t)) & _STOPWORDS[language]) > len(set(words(t)) & _STOPWORDS[other])
    )
    pairs = [(a, b) for i, a in enumerate(texts) for b in texts[i + 1 :]]
    similarity = [
        len(set(words(a)) & set(words(b))) / max(1, len(set(words(a)) | set(words(b))))
        for a, b in pairs
    ]
    n = len(texts)
    return {
        "grounding": grounded / n,
        "source_fidelity": faithful / n,
        "clarity": clear / n,
        "diversity": 1 - (sum(similarity) / len(similarity)) if similarity else 1.0,
        "language_match": in_language / n,
        "questions": texts,
    }


def check_evaluation(output: EvaluationOutput, case: Case) -> tuple[dict[str, bool], str]:
    outcome = resolve_outcome(output)
    outcome_name = outcome.value if outcome else None
    checks = {
        "classification": output.classification in case.classifications,
        "outcome": outcome_name in case.outcomes,
    }
    if case.context_sufficient is not None:
        checks["context_sufficient"] = output.context_sufficient == case.context_sufficient
    if case.correctness is not None:
        low, high = case.correctness
        checks["correctness"] = low <= output.correctness <= high
    if case.completeness is not None:
        low, high = case.completeness
        checks["completeness"] = low <= output.completeness <= high
    if case.misconception is not None:
        checks["misconception"] = bool(output.misconceptions) == case.misconception
    summary = (
        f"{output.classification.value}, correctness {output.correctness:.2f}, completeness "
        f"{output.completeness:.2f}, confidence {output.confidence:.2f} → "
        f"{outcome_name or 'self-grade'}"
    )
    failed = [name for name, ok in checks.items() if not ok]
    if failed:
        summary += " (unexpected: " + ", ".join(failed) + ")"
    return checks, summary


def run_generation(provider: AIProvider, operations: set[str], run: int) -> list[CaseResult]:
    results: list[CaseResult] = []

    def curriculum(result: CaseResult) -> None:
        out = provider.generate_curriculum(
            CurriculumRequest(course_title=COURSE, language=LANGUAGE, passages=PASSAGES)
        )
        _info(result, out.info)
        concepts = [c for ch in out.output.chapters for t in ch.topics for c in t.concepts]
        grounded = [c for c in concepts if set(c.source_refs) & {"S1", "S2"}]
        result.expectation_met = out.output.context_sufficient and len(grounded) >= 2
        result.summary = f"{len(concepts)} concepts, {len(grounded)} grounded in the passages"

    def concept_extraction(result: CaseResult) -> None:
        out = provider.generate_chapter_curriculum(
            ChapterCurriculumRequest(
                course_title=COURSE,
                chapter_title=CHAPTER,
                language=LANGUAGE,
                existing_topics=[
                    ExistingTopic(
                        ref="T1",
                        title="Il deposito bancario",
                        concepts=[ExistingConcept(ref="C1", title="Nozione di deposito")],
                    )
                ],
                passages=PASSAGES,
            )
        )
        _info(result, out.info)
        topics = out.output.topics
        reused = any(t.existing_topic_ref == "T1" for t in topics)
        result.expectation_met = out.output.context_sufficient and bool(topics)
        result.summary = f"{len(topics)} topics, existing topic reused: {reused}"

    def learning_items(result: CaseResult) -> None:
        out = provider.generate_learning_items(
            LearningItemsRequest(
                course_title=COURSE,
                chapter_title=CHAPTER,
                topic_title="Il deposito bancario",
                concept_title="Il deposito bancario",
                concept_description="Nozione ed effetti del deposito bancario",
                language=LANGUAGE,
                passages=[DEPOSIT],
            )
        )
        _info(result, out.info)
        items = out.output.items
        cited = [i for i in items if "S1" in i.source_refs]
        questions = sum(len(i.questions) for i in items)
        result.expectation_met = (
            out.output.context_sufficient and bool(items) and len(cited) == len(items)
        )
        result.summary = f"{len(items)} items ({len(cited)} cited), {questions} questions"

    def questions_in(language: str) -> Callable[[CaseResult], None]:
        italian = language == "it"
        passage = DEPOSIT if italian else DEPOSIT_EN
        existing = ["Che cos'è il deposito bancario?" if italian else "What is a bank deposit?"]

        def step(result: CaseResult) -> None:
            out = provider.generate_questions(
                QuestionsRequest(
                    course_title=COURSE if italian else "Banking law",
                    concept_title="Il deposito bancario" if italian else "Bank deposits",
                    item_title="Nozione di deposito bancario" if italian else "Bank deposit",
                    objective=OBJECTIVE if italian else "Define a bank deposit and its effects",
                    expected_knowledge=passage.text,
                    essential_points=ESSENTIAL if italian else ESSENTIAL_EN,
                    question_types=[
                        QuestionType.APPLICATION,
                        QuestionType.SCENARIO,
                        QuestionType.EXPLANATION,
                    ],
                    count=3,
                    language=language,
                    passages=[passage],
                    existing_questions=existing,
                )
            )
            _info(result, out.info)
            texts = [q.text.strip() for q in out.output.questions if q.text.strip() not in existing]
            result.scores = question_quality(texts, passage.text, language)
            result.scores["types"] = sorted({q.question_type.value for q in out.output.questions})
            result.expectation_met = out.output.context_sufficient and len(texts) >= 1
            q = result.scores
            result.summary = (
                f"{len(texts)} new; grounding {q['grounding']:.2f}, "
                f"fidelity {q['source_fidelity']:.2f}, clarity {q['clarity']:.2f}, "
                f"diversity {q['diversity']:.2f}, language {q['language_match']:.2f}"
            )

        return step

    steps = {
        "curriculum": ("generate_curriculum", curriculum),
        "concept_extraction": ("generate_chapter_curriculum", concept_extraction),
        "learning_items": ("generate_learning_items", learning_items),
        "questions": ("generate_questions", questions_in("it")),
        "questions_en": ("generate_questions", questions_in("en")),
    }
    for name, (operation, step) in steps.items():
        if name.removesuffix("_en") in operations:
            results.append(_run(name, operation, run, step))
    return results


def run_evaluation(provider: AIProvider, run: int) -> list[CaseResult]:
    results = []
    for name, case in EVALUATION_CASES.items():

        def evaluate(result: CaseResult, case: Case = case) -> None:
            out = provider.evaluate_answer(
                EvaluationRequest(
                    language=LANGUAGE,
                    question=case.question,
                    objective=case.objective,
                    expected_knowledge=case.expected_knowledge,
                    essential_points=list(case.essential_points),
                    passages=list(case.passages),
                    answer=case.answer,
                )
            )
            _info(result, out.info)
            result.checks, result.summary = check_evaluation(out.output, case)
            result.expectation_met = all(result.checks.values())
            result.scores = {
                "classification": out.output.classification.value,
                "correctness": out.output.correctness,
                "completeness": out.output.completeness,
                "confidence": out.output.confidence,
                "context_sufficient": out.output.context_sufficient,
            }

        results.append(_run(f"evaluate_{name}", "evaluate_answer", run, evaluate))
    return results


def evaluation_metrics(results: list[CaseResult]) -> dict[str, Any]:
    evaluated = [r for r in results if r.operation == "evaluate_answer"]
    if not evaluated:
        return {}
    ok = [r for r in evaluated if r.ok]

    def share(check: str) -> float | None:
        relevant = [r for r in ok if check in r.checks]
        return None if not relevant else sum(r.checks[check] for r in relevant) / len(relevant)

    spreads = []
    for name in EVALUATION_CASES:
        values = [r.scores["correctness"] for r in ok if r.name == f"evaluate_{name}"]
        if len(values) > 1:
            spreads.append(max(values) - min(values))
    latencies = [r.latency_ms for r in ok if r.latency_ms is not None]
    metrics: dict[str, Any] = {
        "calls": len(evaluated),
        "calls_succeeded": len(ok),
        "classification_agreement": share("classification"),
        "outcome_agreement": share("outcome"),
        "correctness_consistency": share("correctness"),
        "completeness_consistency": share("completeness"),
        "misconception_detection": share("misconception"),
        "context_sufficient_accuracy": share("context_sufficient"),
        "first_attempt_schema_validity": (
            sum(1 for r in ok if r.attempts == 1) / len(evaluated) if evaluated else None
        ),
        "schema_validity": len(ok) / len(evaluated),
        "max_correctness_spread": max(spreads) if spreads else None,
        "median_latency_ms": statistics.median(latencies) if latencies else None,
        "max_latency_ms": max(latencies) if latencies else None,
    }
    bar_met = metrics["calls_succeeded"] == metrics["calls"]
    for metric, threshold in APPROVAL.items():
        value = metrics.get(metric)
        if value is None:
            continue
        bar_met &= value <= threshold if metric == "max_correctness_spread" else value >= threshold
    metrics["meets_approval_bar"] = bar_met
    return metrics


def render_markdown(settings: Settings, results: list[CaseResult], metrics: dict[str, Any]) -> str:
    title = settings.ai_provider
    if settings.ai_model:
        title += f" / {settings.ai_model}"
    lines = [
        f"## AI benchmark: `{title}` (policy {settings.ai_cost_policy})",
        "",
        "| Case | Run | Call | Expectation | Latency | Served by | Prompt | Result |",
        "|---|---|---|---|---|---|---|---|",
    ]
    for r in results:
        call = "ok" if r.ok else f"FAILED ({r.failure or r.error_type})"
        verdict = {True: "met", False: "NOT met", None: "—"}[r.expectation_met]
        latency = f"{r.latency_ms} ms" if r.latency_ms is not None else "—"
        served = f"{r.provider}:{r.model_version} ({r.model_family})" if r.provider else "—"
        lines.append(
            f"| {r.name} | {r.run} | {call} | {verdict} | {latency} | {served} "
            f"| {r.prompt_version or '—'} | {r.summary} |"
        )
    if metrics:
        lines += ["", "### Evaluation metrics", "", "| Metric | Value | Bar |", "|---|---|---|"]
        for key, value in metrics.items():
            if key == "meets_approval_bar":
                continue
            bar = APPROVAL.get(key)
            shown = f"{value:.2f}" if isinstance(value, float) else str(value)
            shown_bar = "" if bar is None else f"{bar:.2f}"
            lines.append(f"| {key} | {shown} | {shown_bar} |")
        lines += [
            "",
            "**Meets the evaluation approval bar: "
            + ("YES" if metrics["meets_approval_bar"] else "NO")
            + "** (approval is a manual step: AI_EVALUATION_APPROVED_MODELS).",
        ]
    return "\n".join(lines) + "\n"


def auth_failure(results: list[CaseResult]) -> bool:
    return any(r.failure == "AUTH_FAILURE" for r in results)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    parser.add_argument(
        "--operations",
        default="all",
        help=f"comma-separated: all, {', '.join(OPERATIONS)}",
    )
    parser.add_argument("--repeat", type=int, default=1, help="evaluation runs per case (1-5)")
    parser.add_argument("--report", type=Path, help="write the Markdown report here")
    parser.add_argument("--json", type=Path, help="write the JSON report here")
    parser.add_argument(
        "--strict", action="store_true", help="fail when the approval bar is missed"
    )
    parser.add_argument(
        "--allow-mock", action="store_true", help="accept AI_PROVIDER=mock (self-test only)"
    )
    parser.add_argument(
        "--credential-name",
        default="the configured API key",
        help="name of the credential source, used only in error messages",
    )
    args = parser.parse_args(argv)
    operations = set(OPERATIONS) if args.operations == "all" else set(args.operations.split(","))
    unknown = operations - set(OPERATIONS)
    if unknown or not 1 <= args.repeat <= 5:
        print(f"Invalid --operations {sorted(unknown)} or --repeat.", file=sys.stderr)
        return 2

    settings = Settings()
    if not settings.ai_provider:
        print("AI_PROVIDER is not set: nothing to benchmark.", file=sys.stderr)
        return 2
    if settings.ai_provider == AI_PROVIDER_MOCK and not args.allow_mock:
        print(
            "AI_PROVIDER=mock is not a real provider (use --allow-mock to self-test).",
            file=sys.stderr,
        )
        return 2
    provider = build_ai_provider(settings)
    if provider is None:
        return 2
    if isinstance(provider, RoutedAIProvider):
        refused = [
            f"{op}: {e.key} ({e.reason})"
            for op in RouteOperation
            for e in provider.excluded.get(op, [])
        ]
        if refused and not any(provider.candidates(op) for op in RouteOperation):
            print("Refused by policy before any call:\n  " + "\n  ".join(refused), file=sys.stderr)
            return 2

    results: list[CaseResult] = []
    for run in range(1, args.repeat + 1):
        if run == 1:
            results += run_generation(provider, operations, run)
        if "evaluation" in operations:
            results += run_evaluation(provider, run)
    metrics = evaluation_metrics(results)
    report = render_markdown(settings, results, metrics)
    print(report)
    if args.report:
        args.report.write_text(report, encoding="utf-8")
    if args.json:
        payload = {
            "provider": settings.ai_provider,
            "model": settings.ai_model,
            "cost_policy": settings.ai_cost_policy,
            "metrics": metrics,
            "results": [asdict(r) for r in results],
        }
        args.json.write_text(json.dumps(payload, indent=2, ensure_ascii=False), encoding="utf-8")

    if auth_failure(results):
        print(
            f"Authentication failed for provider '{settings.ai_provider}': "
            f"check {args.credential_name}.",
            file=sys.stderr,
        )
        return 1
    if not all(r.ok for r in results):
        return 1
    if args.strict and metrics and not metrics["meets_approval_bar"]:
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
