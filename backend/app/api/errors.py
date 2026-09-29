"""Maps every error to the envelope documented in docs/API.md:

{"error_type": "...", "message": "...", "details": {...}}
"""

import logging
from collections.abc import Mapping
from http import HTTPStatus
from typing import Any

from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from starlette.exceptions import HTTPException as StarletteHTTPException

from app.core.errors import AppError, AuthenticationError

logger = logging.getLogger(__name__)

_HTTP_ERROR_TYPES = {404: "not_found", 405: "method_not_allowed"}


def error_response(
    status_code: int,
    error_type: str,
    message: str,
    details: dict[str, Any] | None = None,
    headers: Mapping[str, str] | None = None,
) -> JSONResponse:
    return JSONResponse(
        status_code=status_code,
        content={"error_type": error_type, "message": message, "details": details or {}},
        headers=headers,
    )


async def _app_error(_request: Request, exc: AppError) -> JSONResponse:
    headers = {"WWW-Authenticate": "Bearer"} if isinstance(exc, AuthenticationError) else None
    return error_response(exc.status_code, exc.error_type, exc.message, exc.details, headers)


async def _validation_error(_request: Request, exc: RequestValidationError) -> JSONResponse:
    # Only loc/msg/type are returned: pydantic's full error also echoes the rejected `input`
    # (which can be a password) and non-JSON-serializable `ctx` objects.
    errors = [
        {"loc": list(err.get("loc", ())), "msg": err.get("msg", ""), "type": err.get("type", "")}
        for err in exc.errors()
    ]
    return error_response(422, "validation_error", "Request validation failed", {"errors": errors})


async def _http_error(_request: Request, exc: StarletteHTTPException) -> JSONResponse:
    error_type = _HTTP_ERROR_TYPES.get(exc.status_code, "http_error")
    message = exc.detail if isinstance(exc.detail, str) else HTTPStatus(exc.status_code).phrase
    return error_response(exc.status_code, error_type, message, headers=exc.headers)


async def _unhandled_error(request: Request, exc: Exception) -> JSONResponse:
    # Logged with method/path only — never the body, which may hold study material or answers
    # (docs/PROJECT_SPEC.md §94).
    logger.exception("Unhandled error on %s %s", request.method, request.url.path)
    return error_response(500, "internal_error", "An unexpected error occurred")


def register_exception_handlers(app: FastAPI) -> None:
    app.add_exception_handler(AppError, _app_error)  # type: ignore[arg-type]
    app.add_exception_handler(RequestValidationError, _validation_error)  # type: ignore[arg-type]
    app.add_exception_handler(StarletteHTTPException, _http_error)  # type: ignore[arg-type]
    app.add_exception_handler(Exception, _unhandled_error)
