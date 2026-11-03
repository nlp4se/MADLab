"""Structured HTTP error handling for the web layer.

The engine (``mad/``) raises framework-agnostic domain errors
(:mod:`mad.errors`); the persistence/validation layers raise Pydantic
``ValidationError``; FastAPI raises ``RequestValidationError`` for bad request
payloads. This module maps all of them to a single, predictable JSON envelope so
the frontend can render errors uniformly (Req 12.1).

Envelope shape::

    {
      "detail": "<human-readable message>",
      "error": "<machine-readable error code>",
      "errors": [ ... optional field-level details ... ]
    }

``error`` is the exception class name (e.g. ``"UnderDevelopment"``,
``"ValidationError"``), letting clients branch without string-matching
``detail``. ``errors`` is only present for validation failures and carries the
per-field breakdown.

HTTP status mapping for domain errors:

============================  ======  ===========================================
Exception                     Status  Rationale
============================  ======  ===========================================
ConfigValidationError         422     Invalid configuration artifact (unprocessable)
TemplateError                 422     Input template cannot be resolved
UnderDevelopment              409     Value is configurable but not yet executable
ProviderError                 502     Upstream model provider failed
ExecutionError                500     Debate execution failed at runtime
MADError (other/base)         500     Unclassified engine error
============================  ======  ===========================================
"""

from __future__ import annotations

from typing import Any

from fastapi import FastAPI, Request, status
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from pydantic import ValidationError

from mad.errors import (
    ConfigValidationError,
    ExecutionError,
    MADError,
    ProviderError,
    TemplateError,
    UnderDevelopment,
)

# Map each concrete domain error to an HTTP status code. Order matters: the
# handler walks this in definition order, so more specific subclasses must come
# before their base ``MADError``.
# 422 is spelled as a literal to stay compatible across FastAPI versions: the
# status constant was renamed (``..._ENTITY`` -> ``..._CONTENT``) and the old
# name is deprecated in newer releases while the new name is absent from older.
_HTTP_422 = 422

_DOMAIN_STATUS: list[tuple[type[MADError], int]] = [
    (ConfigValidationError, _HTTP_422),
    (TemplateError, _HTTP_422),
    (UnderDevelopment, status.HTTP_409_CONFLICT),
    (ProviderError, status.HTTP_502_BAD_GATEWAY),
    (ExecutionError, status.HTTP_500_INTERNAL_SERVER_ERROR),
    (MADError, status.HTTP_500_INTERNAL_SERVER_ERROR),
]


def _status_for(exc: MADError) -> int:
    """Return the HTTP status code for a domain error instance."""
    for exc_type, code in _DOMAIN_STATUS:
        if isinstance(exc, exc_type):
            return code
    return status.HTTP_500_INTERNAL_SERVER_ERROR


def _envelope(detail: str, error: str, errors: list[Any] | None = None) -> dict[str, Any]:
    """Build the structured error body."""
    body: dict[str, Any] = {"detail": detail, "error": error}
    if errors is not None:
        body["errors"] = errors
    return body


async def mad_error_handler(_request: Request, exc: MADError) -> JSONResponse:
    """Map any :class:`~mad.errors.MADError` to a structured JSON response.

    When the error carries a ``.fields`` payload (e.g. a
    :class:`~mad.errors.ConfigValidationError` raised by artifact import with
    per-field schema errors), those are surfaced under ``errors`` so the client
    gets actionable, field-level detail (Req 4.2).
    """
    code = _status_for(exc)
    detail = str(exc) or exc.__class__.__name__
    fields = getattr(exc, "fields", None)
    errors = fields if isinstance(fields, list) and fields else None
    return JSONResponse(
        status_code=code,
        content=_envelope(detail, exc.__class__.__name__, errors=errors),
    )


async def request_validation_handler(
    _request: Request, exc: RequestValidationError
) -> JSONResponse:
    """Map FastAPI request-validation errors to the structured envelope (422)."""
    return JSONResponse(
        status_code=_HTTP_422,
        content=_envelope(
            "Request validation failed.",
            "RequestValidationError",
            errors=_jsonable_errors(exc.errors()),
        ),
    )


async def pydantic_validation_handler(
    _request: Request, exc: ValidationError
) -> JSONResponse:
    """Map a bare Pydantic ``ValidationError`` (e.g. from the service/engine layer)."""
    return JSONResponse(
        status_code=_HTTP_422,
        content=_envelope(
            "Validation failed.",
            "ValidationError",
            errors=_jsonable_errors(exc.errors()),
        ),
    )


def _jsonable_errors(errors: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Reduce pydantic/FastAPI error records to a JSON-serializable, stable shape.

    The raw error records can embed non-serializable context (exception
    instances under ``ctx``); we keep only ``loc``/``msg``/``type`` and coerce
    ``loc`` to a list so the payload always serializes cleanly.
    """
    cleaned: list[dict[str, Any]] = []
    for err in errors:
        cleaned.append(
            {
                "loc": list(err.get("loc", [])),
                "msg": err.get("msg", ""),
                "type": err.get("type", ""),
            }
        )
    return cleaned


def register_exception_handlers(app: FastAPI) -> None:
    """Register all structured exception handlers on ``app``.

    Registering the base :class:`~mad.errors.MADError` is sufficient for every
    subclass because FastAPI dispatches on the most specific registered class
    and we classify the concrete type inside :func:`mad_error_handler`.
    """
    app.add_exception_handler(MADError, mad_error_handler)  # type: ignore[arg-type]
    app.add_exception_handler(RequestValidationError, request_validation_handler)  # type: ignore[arg-type]
    app.add_exception_handler(ValidationError, pydantic_validation_handler)  # type: ignore[arg-type]


__all__ = [
    "register_exception_handlers",
    "mad_error_handler",
    "request_validation_handler",
    "pydantic_validation_handler",
]
