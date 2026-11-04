"""Domain error types for the MAD engine.

These are plain Python exceptions with no web/framework dependency. The web
layer (``app``) maps them to structured HTTP responses; the CLI prints them.
Concrete usage arrives with the engine implementation (phases 1-4); the base
hierarchy is defined here so modules can import a stable set of errors.
"""

from __future__ import annotations

import json
import re
from typing import Any, Optional


class MADError(Exception):
    """Base class for all MAD engine errors.

    ``transcript`` carries the partial :class:`~mad.engine.transcript.Transcript`
    when a debate aborts mid-run (set by ``run_debate``), so callers can keep
    the messages, errors and notes recorded before the failure (task 11.17).
    """

    transcript: Any = None


class ConfigValidationError(MADError):
    """Raised when a MAD configuration artifact fails validation."""


class UnderDevelopment(MADError):
    """Raised when a configured taxonomy value is not yet executable.

    The configuration can still be saved/persisted; only execution is gated.
    """


class TemplateError(MADError):
    """Raised when an input template cannot be resolved against an instance.

    Typically carries the names of placeholders that have no corresponding
    field in the instance (or in the available-field set during validation).
    """


class ProviderError(MADError):
    """Raised for model-provider resolution, connectivity, or invocation failures.

    Attributes (all optional; set by the provider adapter when it can classify
    the upstream failure, task 11.17):
        category: One of :data:`PROVIDER_ERROR_CATEGORIES` (``"other"`` when
            unknown).
        status_code: The upstream HTTP status, if known.
        retry_after_s: The delay the provider asked for before retrying (a
            ``Retry-After`` header or a Gemini ``retryDelay``), if any.
    """

    def __init__(
        self,
        message: str = "",
        *,
        category: str = "other",
        status_code: Optional[int] = None,
        retry_after_s: Optional[float] = None,
    ) -> None:
        super().__init__(message)
        self.category = category if category in PROVIDER_ERROR_CATEGORIES else "other"
        self.status_code = status_code
        self.retry_after_s = retry_after_s

    @property
    def retryable(self) -> bool:
        """Whether retrying the same request can succeed.

        Auth, missing-model and rejected-request errors are deterministic, so
        retrying only burns quota. Rate limits, timeouts, connection and server
        errors are transient (the caller still honours ``retry_after_s``).
        """
        return self.category not in {"auth", "not_found", "bad_request"}

    @property
    def request_rejected(self) -> bool:
        """Whether the provider may have rejected the request's shape.

        Only then is a differently-shaped request (the JSON-mode fallback of
        structured output) worth a try. A rate limit, auth, timeout or server
        error would hit the fallback call too.
        """
        return self.category in {"bad_request", "other"}


# Classified provider failure kinds (see :class:`ProviderError`).
PROVIDER_ERROR_CATEGORIES = frozenset(
    {
        "rate_limit",
        "auth",
        "not_found",
        "timeout",
        "connection",
        "server",
        "bad_request",
        "other",
    }
)


class ExecutionError(MADError):
    """Raised when a debate execution fails at runtime."""


# ---------------------------------------------------------------------------
# Short, secret-free error text for transcripts and instance errors
# ---------------------------------------------------------------------------

# Credentials that can leak into provider error text (URLs, echoed headers).
_SECRET_PATTERNS = (
    re.compile(r"(?i)([?&]key=)[^&\s\"']+"),
    re.compile(r"(?i)(api[_-]?key[\"']?\s*[:=]\s*[\"']?)[^\s\"',}]+"),
    re.compile(r"(?i)(bearer\s+)[A-Za-z0-9._\-]+"),
    re.compile(r"()\bsk-[A-Za-z0-9_\-]{8,}"),
    re.compile(r"()\bAIza[0-9A-Za-z_\-]{20,}"),
)

# The ``"message": "..."`` field of a JSON error body (OpenAI, Gemini, Anthropic).
_JSON_MESSAGE = re.compile(r'"message"\s*:\s*("(?:[^"\\]|\\.)*")')

# Wrapper prefixes LiteLLM repeats in front of the provider text.
_LITELLM_PREFIX = re.compile(r"(?:litellm\.\w+:\s*)+")


def redact_secrets(text: str, secrets: tuple[Optional[str], ...] = ()) -> str:
    """Mask API keys / tokens in ``text`` (known ``secrets`` plus common shapes)."""
    for secret in secrets:
        if secret:
            text = text.replace(secret, "***")
    for pattern in _SECRET_PATTERNS:
        text = pattern.sub(lambda m: f"{m.group(1)}***", text)
    return text


def truncate(text: str, limit: int) -> str:
    """``text`` cut to ``limit`` characters with an ellipsis."""
    if limit <= 0 or len(text) <= limit:
        return text
    return text[: max(0, limit - 1)].rstrip() + "…"


def error_summary(exc: BaseException, limit: int = 300) -> str:
    """A short, secret-free, human-readable description of ``exc``.

    Provider failures often embed the whole JSON error body; the summary keeps
    the error type, the HTTP status when known, and the body's ``message``
    (e.g. Gemini's "You exceeded your current quota ..."), collapsed to one
    line and truncated to ``limit`` characters.
    """
    text = str(exc) or type(exc).__name__
    status = getattr(exc, "status_code", None)
    category = getattr(exc, "category", None)

    detail = text
    match = _JSON_MESSAGE.search(text)
    if match:
        try:
            detail = json.loads(match.group(1))
        except ValueError:
            detail = match.group(1).strip('"')
        # Keep the adapter's lead-in (model + kind) ahead of the body message.
        head = text[: text.find("{")].strip() if "{" in text else ""
        head = _LITELLM_PREFIX.sub("", head).rstrip(" -:")
        if head:
            detail = f"{head}: {detail}"
    else:
        detail = _LITELLM_PREFIX.sub("", detail)

    detail = " ".join(redact_secrets(str(detail)).split())
    labels = []
    if category and category != "other":
        labels.append(category.replace("_", " "))
    if status:
        labels.append(f"HTTP {status}")
    prefix = f"[{', '.join(labels)}] " if labels else ""
    return truncate(prefix + detail, limit)
