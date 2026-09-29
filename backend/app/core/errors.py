"""Domain errors raised by services and mapped to the API error envelope in app/api/errors.py.

Services raise these instead of HTTPException so business logic stays framework-agnostic and each
route handler doesn't need its own try/except translation.
"""

from typing import Any


class AppError(Exception):
    status_code = 500
    error_type = "internal_error"

    def __init__(self, message: str, details: dict[str, Any] | None = None) -> None:
        super().__init__(message)
        self.message = message
        self.details = details or {}


class NotFoundError(AppError):
    """Raised when a resource doesn't exist OR exists but isn't owned by the requesting user.

    Both cases map to 404 — never 403 — so a response never confirms that a resource id belonging
    to someone else actually exists (docs/PROJECT_SPEC.md §10).
    """

    status_code = 404
    error_type = "not_found"


class ConflictError(AppError):
    status_code = 409
    error_type = "conflict"


class InvalidStateTransitionError(AppError):
    """Concept activation state machine violation (docs/PROJECT_SPEC.md §21, §22)."""

    status_code = 409
    error_type = "invalid_state_transition"


class AuthenticationError(AppError):
    status_code = 401
    error_type = "authentication_failed"


class PayloadTooLargeError(AppError):
    status_code = 413
    error_type = "payload_too_large"


class UnsupportedMediaTypeError(AppError):
    status_code = 415
    error_type = "unsupported_media_type"


class AINotConfiguredError(AppError):
    """AI_PROVIDER is empty: the server runs, but AI features are off."""

    status_code = 503
    error_type = "ai_not_configured"


class AIUnavailableError(AppError):
    """The runtime AI provider couldn't be reached or answered with an error."""

    status_code = 503
    error_type = "ai_unavailable"


class FreeCapacityExhaustedError(AppError):
    """AI_COST_POLICY=FREE_ONLY and no free provider/model could answer (all rate-limited, out
    of quota, down, or none configured). A paid endpoint is never tried instead
    (docs/FREE_AI_ROUTING.md §4)."""

    status_code = 503
    error_type = "free_capacity_exhausted"


class AIInvalidOutputError(AppError):
    """The provider answered, but not with valid structured output, even after the constrained
    retry (docs/PROJECT_SPEC.md §36). Never guessed around."""

    status_code = 502
    error_type = "ai_invalid_output"


class InvalidRequestError(AppError):
    """A well-formed request that doesn't fit the resource, e.g. a Chapter tree sent to apply a
    Course proposal. Same status and type as body validation errors."""

    status_code = 422
    error_type = "validation_error"
