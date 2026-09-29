"""Normalized provider failures (docs/FREE_AI_ROUTING.md §5).

Every vendor reports problems differently (status codes, error bodies). Transports translate
them into one `FailureKind`, carried in the error's `details["failure"]`, so routing decides
what to do next without knowing any vendor. Error bodies are inspected only to classify; they
are never copied into errors or logs.
"""

from enum import StrEnum

from app.core.errors import AIInvalidOutputError, AIUnavailableError, AppError


class FailureKind(StrEnum):
    AUTH_FAILURE = "AUTH_FAILURE"
    RATE_LIMITED = "RATE_LIMITED"
    QUOTA_EXHAUSTED = "QUOTA_EXHAUSTED"
    # A model's free quota/trial package is used up (e.g. Alibaba with "Free Quota Only",
    # Tencent TokenHub with payment disabled): the provider refuses instead of billing.
    FREE_QUOTA_EXHAUSTED = "FREE_QUOTA_EXHAUSTED"
    PROVIDER_UNAVAILABLE = "PROVIDER_UNAVAILABLE"
    MODEL_UNAVAILABLE = "MODEL_UNAVAILABLE"
    MODEL_NOT_FREE = "MODEL_NOT_FREE"
    TIMEOUT = "TIMEOUT"
    INVALID_STRUCTURED_OUTPUT = "INVALID_STRUCTURED_OUTPUT"


# The next candidate may be tried after these. AUTH_FAILURE, MODEL_UNAVAILABLE and
# MODEL_NOT_FREE also move on, but additionally take the provider or model out of rotation.
FALLBACK_ALLOWED = frozenset(
    {
        FailureKind.RATE_LIMITED,
        FailureKind.QUOTA_EXHAUSTED,
        FailureKind.FREE_QUOTA_EXHAUSTED,
        FailureKind.PROVIDER_UNAVAILABLE,
        FailureKind.TIMEOUT,
        FailureKind.INVALID_STRUCTURED_OUTPUT,
        FailureKind.MODEL_UNAVAILABLE,
        FailureKind.AUTH_FAILURE,
        FailureKind.MODEL_NOT_FREE,
    }
)

_QUOTA_HINTS = (
    "quota",
    "daily free allocation",
    "free allocation",
    "neurons",
    "insufficient_quota",
    "insufficient credits",
    "credits",
    "exceeded your",
    "limit exceeded",
    "resource_exhausted",
)
_FREE_QUOTA_HINTS = (
    "free tier",
    "free_tier",
    "freetier",
    "free quota",
    "free_quota",
    "freequota",
    "free trial",
    "trial package",
    "trial quota",
    "free package",
)
_NOT_FREE_HINTS = ("workers paid", "paid plan", "requires a paid", "upgrade your plan", "not free")
_MODEL_HINTS = (
    "model not found",
    "does not exist",
    "unknown model",
    "no such model",
    "model_not_found",
    "not a valid model",
    "decommissioned",
    "deprecated",
)


def classify_http(status: int, body: str) -> FailureKind:
    """Maps an HTTP error to a FailureKind. `body` is used only for keyword matching."""
    text = body.lower()
    if status in (400, 402, 403, 429) and any(h in text for h in _FREE_QUOTA_HINTS):
        return FailureKind.FREE_QUOTA_EXHAUSTED
    if status == 429:
        return (
            FailureKind.QUOTA_EXHAUSTED
            if any(h in text for h in _QUOTA_HINTS)
            else FailureKind.RATE_LIMITED
        )
    if status == 402:
        return FailureKind.QUOTA_EXHAUSTED
    if status in (401, 403):
        if any(h in text for h in _NOT_FREE_HINTS):
            return FailureKind.MODEL_NOT_FREE
        return FailureKind.AUTH_FAILURE
    if status == 404 or (status in (400, 422) and any(h in text for h in _MODEL_HINTS)):
        return FailureKind.MODEL_UNAVAILABLE
    if status == 408 or status == 504:
        return FailureKind.TIMEOUT
    return FailureKind.PROVIDER_UNAVAILABLE


def failure_of(error: AppError) -> FailureKind:
    """The FailureKind an AI error carries (older errors default by type)."""
    failure = error.details.get("failure") if error.details else None
    if isinstance(failure, str) and failure in FailureKind.__members__:
        return FailureKind(failure)
    if isinstance(error, AIInvalidOutputError):
        return FailureKind.INVALID_STRUCTURED_OUTPUT
    if isinstance(error, AIUnavailableError) and error.details.get("reason") == "timeout":
        return FailureKind.TIMEOUT
    return FailureKind.PROVIDER_UNAVAILABLE
