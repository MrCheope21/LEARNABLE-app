"""Per-operation routing across runtime providers under a cost and data policy
(docs/FREE_AI_ROUTING.md §3-5).

Each operation has its own ordered list of candidates (provider + model). Candidates are
filtered once, when the router is built: under AI_COST_POLICY=FREE_ONLY a candidate that isn't
free_only_eligible is never constructed, so no code path can call a paid endpoint. At call time
candidates are tried in order; a failure moves to the next according to its FailureKind, and
two kinds take things out of rotation for the rest of the process:

- AUTH_FAILURE disables the provider (a bad key won't start working mid-run);
- MODEL_NOT_FREE excludes that model.

When nobody could answer, FREE_ONLY raises FreeCapacityExhaustedError; other policies raise
AIUnavailableError. Either way the error lists who was tried and why, never content or keys.
"""

import logging
import time
from collections.abc import Callable
from dataclasses import dataclass, replace
from typing import Any, Literal, Protocol

from app.ai.catalog import (
    PROVIDERS,
    ModelCapability,
    PrivacyClass,
    RouteOperation,
    is_dynamic_router,
)
from app.ai.failures import FailureKind, failure_of
from app.ai.provider import (
    AIProvider,
    ChapterCurriculumResult,
    CurriculumResult,
    EvaluationResult,
    LearningItemsResult,
    QuestionsResult,
)
from app.ai.schemas import (
    ChapterCurriculumRequest,
    CurriculumRequest,
    EvaluationRequest,
    LearningItemsRequest,
    QuestionsRequest,
)
from app.core.errors import AIInvalidOutputError, AIUnavailableError, FreeCapacityExhaustedError

logger = logging.getLogger(__name__)

CostPolicy = Literal["FREE_ONLY", "FREE_FIRST", "ANY_CONFIGURED"]
DataPolicy = Literal["development", "private"]


@dataclass(frozen=True)
class Candidate:
    capability: ModelCapability
    provider: AIProvider

    @property
    def provider_id(self) -> str:
        return self.capability.provider_id

    @property
    def model_id(self) -> str:
        return self.capability.model_id

    @property
    def key(self) -> str:
        return self.capability.key


@dataclass(frozen=True)
class Exclusion:
    key: str
    reason: str


def select_candidates(
    operation: RouteOperation,
    candidates: list[tuple[ModelCapability, Callable[[], AIProvider]]],
    *,
    cost_policy: CostPolicy,
    data_policy: DataPolicy,
    require_approved_evaluator: bool,
) -> tuple[list[Candidate], list[Exclusion]]:
    """Applies the policies to one operation's route. Providers are built only for the
    candidates that pass, so an excluded (e.g. paid) model never gets a client."""
    kept: list[tuple[ModelCapability, Callable[[], AIProvider]]] = []
    excluded: list[Exclusion] = []
    for capability, build in candidates:
        reason = _exclusion_reason(
            operation, capability, cost_policy, data_policy, require_approved_evaluator
        )
        if reason:
            excluded.append(Exclusion(capability.key, reason))
        else:
            kept.append((capability, build))
    if cost_policy == "FREE_FIRST":
        # Stable: free ones first in route order, then the rest in route order.
        kept.sort(key=lambda c: not c[0].free_only_eligible)
    return [Candidate(capability, build()) for capability, build in kept], excluded


def _exclusion_reason(
    operation: RouteOperation,
    capability: ModelCapability,
    cost_policy: CostPolicy,
    data_policy: DataPolicy,
    require_approved_evaluator: bool,
) -> str | None:
    if operation not in capability.operations:
        return "operation_not_supported"
    if cost_policy == "FREE_ONLY" and not capability.free_only_eligible:
        spec = PROVIDERS.get(capability.provider_id)
        if spec is not None and spec.billing_guard is not None:
            return (
                f"not_free_only_eligible ({capability.cost_class}): needs "
                f"{spec.billing_guard}=true and the model in AI_FREE_MODELS"
            )
        return f"not_free_only_eligible ({capability.cost_class})"
    if data_policy == "private" and capability.privacy_class is not PrivacyClass.PRIVATE_APPROVED:
        return f"not_approved_for_private_material ({capability.privacy_class})"
    if operation is RouteOperation.ANSWER_EVALUATION:
        if is_dynamic_router(capability.provider_id, capability.model_id):
            return "dynamic_router_not_allowed_for_evaluation"
        if require_approved_evaluator and not capability.evaluation_approved:
            return "evaluator_not_benchmark_approved"
        if capability.evaluation_requires_approval and not capability.evaluation_approved:
            return "small_model_needs_benchmark_approval"
    return None


class _Result(Protocol):
    @property
    def info(self) -> Any: ...


class RoutedAIProvider:
    """AIProvider over per-operation candidate lists."""

    def __init__(
        self,
        routes: dict[RouteOperation, list[Candidate]],
        *,
        cost_policy: CostPolicy,
        excluded: dict[RouteOperation, list[Exclusion]] | None = None,
    ) -> None:
        self._routes = routes
        self._cost_policy = cost_policy
        self.excluded = excluded or {}
        # Runtime exclusions for the rest of this process.
        self.disabled_providers: set[str] = set()
        self.not_free_models: set[str] = set()

    def candidates(self, operation: RouteOperation) -> list[Candidate]:
        return [
            c
            for c in self._routes.get(operation, [])
            if c.provider_id not in self.disabled_providers
            and c.key not in self.not_free_models
            # select_candidates already drops these; checked again so FREE_ONLY holds however
            # the routes were built.
            and (self._cost_policy != "FREE_ONLY" or c.capability.free_only_eligible)
        ]

    def generate_curriculum(self, request: CurriculumRequest) -> CurriculumResult:
        return self._run(
            RouteOperation.CURRICULUM_GENERATION, lambda p: p.generate_curriculum(request)
        )

    def generate_chapter_curriculum(
        self, request: ChapterCurriculumRequest
    ) -> ChapterCurriculumResult:
        return self._run(
            RouteOperation.CONCEPT_EXTRACTION, lambda p: p.generate_chapter_curriculum(request)
        )

    def generate_learning_items(self, request: LearningItemsRequest) -> LearningItemsResult:
        return self._run(
            RouteOperation.LEARNING_ITEM_GENERATION, lambda p: p.generate_learning_items(request)
        )

    def generate_questions(self, request: QuestionsRequest) -> QuestionsResult:
        return self._run(
            RouteOperation.QUESTION_GENERATION, lambda p: p.generate_questions(request)
        )

    def evaluate_answer(self, request: EvaluationRequest) -> EvaluationResult:
        return self._run(RouteOperation.ANSWER_EVALUATION, lambda p: p.evaluate_answer(request))

    def _run[R: _Result](self, operation: RouteOperation, call: Callable[[AIProvider], R]) -> R:
        attempts: list[dict[str, str]] = []
        last_kind: FailureKind | None = None
        for index, candidate in enumerate(self.candidates(operation)):
            if (
                candidate.provider_id in self.disabled_providers
                or candidate.key in self.not_free_models
            ):
                continue  # excluded by an earlier attempt of this same call
            started = time.monotonic()
            try:
                result = call(candidate.provider)
            except (AIUnavailableError, AIInvalidOutputError) as exc:
                kind = failure_of(exc)
                last_kind = kind
                attempts.append(
                    {
                        "provider": candidate.provider_id,
                        "model": candidate.model_id,
                        "failure": kind,
                    }
                )
                _log_attempt(operation, candidate, index, started, kind)
                if kind is FailureKind.AUTH_FAILURE:
                    self.disabled_providers.add(candidate.provider_id)
                    logger.error(
                        "ai_provider_disabled provider=%s reason=AUTH_FAILURE "
                        "(check this provider's API key configuration)",
                        candidate.provider_id,
                    )
                elif kind is FailureKind.FREE_QUOTA_EXHAUSTED:
                    # Its free quota is gone for now: don't spend calls finding that out again.
                    self.not_free_models.add(candidate.key)
                    logger.warning(
                        "ai_model_excluded provider=%s model=%s reason=FREE_QUOTA_EXHAUSTED",
                        candidate.provider_id,
                        candidate.model_id,
                    )
                elif kind is FailureKind.MODEL_NOT_FREE:
                    self.not_free_models.add(candidate.key)
                    logger.error(
                        "ai_model_excluded provider=%s model=%s reason=MODEL_NOT_FREE",
                        candidate.provider_id,
                        candidate.model_id,
                    )
                continue
            _log_attempt(operation, candidate, index, started, None)
            info = replace(result.info, fallback_index=index)
            return replace(result, info=info)  # type: ignore[type-var]

        details: dict[str, Any] = {"operation": operation.value, "attempts": attempts}
        if not attempts:
            details["reason"] = "no_eligible_candidate"
        if self._cost_policy == "FREE_ONLY":
            raise FreeCapacityExhaustedError(
                "No free AI capacity is available right now. Please try again later.",
                details=details,
            )
        if last_kind is not None:
            details["failure"] = last_kind
        raise AIUnavailableError("No configured AI provider could answer.", details=details)


def _log_attempt(
    operation: RouteOperation,
    candidate: Candidate,
    index: int,
    started: float,
    failure: FailureKind | None,
) -> None:
    # Operational metadata only (docs/FREE_AI_ROUTING.md §7): no prompt, passage, answer or key.
    logger.info(
        "ai_route operation=%s provider=%s model=%s fallback_index=%d latency_ms=%d "
        "schema_valid=%s error_class=%s",
        operation,
        candidate.provider_id,
        candidate.model_id,
        index,
        round((time.monotonic() - started) * 1000),
        "false"
        if failure is FailureKind.INVALID_STRUCTURED_OUTPUT
        else "true"
        if failure is None
        else "n/a",
        failure or "none",
    )
