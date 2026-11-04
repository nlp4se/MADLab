"""Design-assistant service layer (task 11.1).

This service turns a chat request into a structured design envelope. It sits
between the assistant router and three collaborators, mirroring the providers /
executions services (layering per Req 12.2: ``routers -> services ->
engine/persistence``):

* **providers / security** — the engine
  :class:`~mad.providers.registry.ProviderRegistry` built from the stored
  providers via :func:`app.services.providers.build_registry` (keys are
  decrypted only there, at call time). The router passes the registry in as a
  dependency so tests override it with a :class:`~mad.providers.base.MockModelClient`-backed
  registry and run fully offline.
* **prompt** — :func:`app.services.assistant_prompt.build_system_prompt` teaches
  the taxonomy, the exact ``MADConfig`` schema, the ask-first behaviour, and the
  response envelope.
* **engine schema** — :func:`mad.taxonomy.version.import_config` validates any
  proposed artifact before it is returned, so the designer never receives a
  broken config.

The single entry point is :func:`design`. Its contract:

* Resolve ``provider_id`` + ``model`` through the registry. A missing provider
  raises :class:`ProviderNotFoundError` (the router maps it to 404).
* Call the model with a low temperature and a bounded ``max_tokens``.
* Parse the envelope robustly (strip code fences, extract the first balanced
  JSON object). On parse failure, fall back to a free-text ``question`` so the
  chat keeps working.
* For a ``proposal``, validate the artifact through the engine. Invalid →
  downgrade to a ``question`` explaining what is wrong (never leak a broken
  proposal). Valid → populate ``under_development`` from
  :meth:`MADConfig.under_development_values`.
* Any provider/runtime failure (unscoped key, unknown model, network) is caught
  and returned as a clear ``question`` — it never 500s the request. Genuine
  "provider not found" stays a 404.
"""

from __future__ import annotations

import json
from typing import Any, Optional

from sqlalchemy.orm import Session

from app.schemas.assistant import (
    AssistantDesignRequest,
    AssistantDesignResponse,
    AssistantMessage,
)
from app.services.assistant_prompt import build_system_prompt
from mad.errors import ConfigValidationError, MADError
from mad.providers.base import Message
from mad.providers.registry import ProviderRegistry
from mad.taxonomy.schema import MADConfig
from mad.taxonomy.version import import_config

# Bounded generation: enough for a full artifact + explanation, low temperature
# so the structured envelope stays stable across calls.
_MAX_TOKENS = 2000
_TEMPERATURE = 0.1


class ProviderNotFoundError(MADError):
    """Raised when the requested provider id is not registered.

    The router maps this to a 404 (a genuinely missing provider is a client
    error), distinct from a *runtime* provider failure which is reported inline
    as a ``question`` so the chat keeps working.
    """


def design(
    session: Session,
    body: AssistantDesignRequest,
    *,
    registry: ProviderRegistry,
) -> AssistantDesignResponse:
    """Produce a clarifying question or a validated proposal for ``body``.

    Args:
        session: Request-scoped DB session (unused directly here, but kept for
            symmetry with the other services and future persistence needs).
        body: The chat request (message + history + current artifact + the
            per-request provider/model binding).
        registry: The engine provider registry (built from stored providers by
            the router dependency; overridden with a mock in tests).

    Returns:
        An :class:`AssistantDesignResponse` envelope — ``question`` or validated
        ``proposal``.

    Raises:
        ProviderNotFoundError: If ``body.provider_id`` is not registered (→ 404).
    """
    provider_id = str(body.provider_id)
    if not registry.has(provider_id):
        raise ProviderNotFoundError(
            f"provider {body.provider_id} not found"
        )

    client = registry.get_client(provider_id)
    messages = _compose_messages(body)

    # Call the model. A provider/runtime failure is reported inline (never 500).
    try:
        response = client.complete(
            messages=messages,
            model=body.model,
            params={"temperature": _TEMPERATURE, "max_tokens": _MAX_TOKENS},
        )
    except Exception as exc:  # noqa: BLE001 - provider failures become questions.
        return AssistantDesignResponse(
            mode="question",
            message=(
                f"The model call failed: {exc}. Check the provider key/model and "
                "try again."
            ),
            artifact=None,
        )

    return _envelope_from_text(response.text or "")


# ---------------------------------------------------------------------------
# Message composition
# ---------------------------------------------------------------------------


def _compose_messages(body: AssistantDesignRequest) -> list[Message]:
    """Build the chat message list: system prompt + history + new user turn.

    The current artifact is embedded in the system prompt (so the model edits it
    in place); the running conversation is replayed verbatim, then the new user
    message is appended.
    """
    messages: list[Message] = [
        Message(role="system", content=build_system_prompt(body.artifact))
    ]
    for turn in body.history:
        messages.append(Message(role=turn.role, content=turn.content))
    messages.append(Message(role="user", content=body.message))
    return messages


# ---------------------------------------------------------------------------
# Envelope parsing + artifact validation
# ---------------------------------------------------------------------------


def _envelope_from_text(text: str) -> AssistantDesignResponse:
    """Parse the model's reply into a validated response envelope.

    Robustness ladder:
    1. Extract a JSON object from the reply (handles code fences and leading /
       trailing prose by scanning for the first balanced ``{...}``).
    2. If none parses, treat the whole reply as a free-text ``question``.
    3. If it parses but ``mode`` is ``proposal``, validate the artifact; invalid
       → downgrade to a ``question`` with the validation summary.
    """
    envelope = _extract_json_object(text)
    if envelope is None:
        # No machine-readable envelope — keep the chat working with free text.
        return AssistantDesignResponse(
            mode="question",
            message=text.strip() or "Could you tell me more about the debate you want to design?",
            artifact=None,
        )

    mode = envelope.get("mode")
    message = str(envelope.get("message") or "").strip()
    artifact = envelope.get("artifact")

    if mode == "proposal" and isinstance(artifact, dict):
        return _validate_proposal(message, artifact)

    # Anything else (explicit "question", unknown mode, or a proposal without a
    # usable artifact) is surfaced as a question so nothing broken leaks.
    if mode == "proposal":
        message = message or "I need a bit more detail before I can propose a configuration."
    return AssistantDesignResponse(
        mode="question",
        message=message or "Could you tell me more about the debate you want to design?",
        artifact=None,
    )


def _validate_proposal(
    message: str, artifact: dict[str, Any]
) -> AssistantDesignResponse:
    """Validate a proposed artifact; downgrade to a question when invalid.

    A valid artifact is returned as a ``proposal`` with ``under_development``
    populated from the engine. An invalid one is NOT returned as a proposal —
    instead a ``question`` explains what is missing/invalid so the designer
    never receives a broken config.
    """
    try:
        config: MADConfig = import_config(artifact)
    except ConfigValidationError as exc:
        return AssistantDesignResponse(
            mode="question",
            message=(
                (message + "\n\n" if message else "")
                + "I couldn't build a valid configuration yet: "
                + str(exc)
                + " Could you clarify so I can fix it?"
            ),
            artifact=None,
        )

    return AssistantDesignResponse(
        mode="proposal",
        message=message or "Here is a proposed configuration.",
        artifact=config.model_dump(mode="json"),
        under_development=config.under_development_values(),
    )


def _extract_json_object(text: str) -> Optional[dict[str, Any]]:
    """Extract the first balanced JSON object from ``text``, or ``None``.

    Handles the common provider outputs: a bare JSON object, an object wrapped
    in ```` ```json ```` fences, or an object preceded/followed by prose. The
    scan respects string literals and escapes so braces inside strings do not
    throw off the balance count.
    """
    if not text:
        return None

    stripped = _strip_code_fences(text)

    # Fast path: the whole thing is valid JSON.
    parsed = _try_json(stripped)
    if isinstance(parsed, dict):
        return parsed

    # Scan for the first balanced top-level object.
    start = stripped.find("{")
    while start != -1:
        candidate = _balanced_object_at(stripped, start)
        if candidate is not None:
            parsed = _try_json(candidate)
            if isinstance(parsed, dict):
                return parsed
        start = stripped.find("{", start + 1)
    return None


def _strip_code_fences(text: str) -> str:
    """Remove a single surrounding Markdown code fence, if present."""
    s = text.strip()
    if s.startswith("```"):
        # Drop the opening fence line (``` or ```json) and the trailing fence.
        newline = s.find("\n")
        if newline != -1:
            s = s[newline + 1 :]
        if s.rstrip().endswith("```"):
            s = s.rstrip()[: -3]
    return s.strip()


def _balanced_object_at(text: str, start: int) -> Optional[str]:
    """Return the balanced ``{...}`` substring starting at ``start``, or ``None``.

    Tracks string state so braces inside JSON strings are ignored.
    """
    depth = 0
    in_string = False
    escape = False
    for i in range(start, len(text)):
        ch = text[i]
        if in_string:
            if escape:
                escape = False
            elif ch == "\\":
                escape = True
            elif ch == '"':
                in_string = False
            continue
        if ch == '"':
            in_string = True
        elif ch == "{":
            depth += 1
        elif ch == "}":
            depth -= 1
            if depth == 0:
                return text[start : i + 1]
    return None


def _try_json(text: str) -> Any:
    """Best-effort JSON parse; returns ``None`` on failure."""
    try:
        return json.loads(text)
    except (ValueError, TypeError):
        return None


__all__ = ["design", "ProviderNotFoundError"]
