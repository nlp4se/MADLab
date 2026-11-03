"""Unified model-invocation abstraction for the MAD engine.

This module defines the single contract every model provider must satisfy, the
response/usage value types the engine consumes, and a deterministic, offline
:class:`MockModelClient` used by engine tests and gold-case fixtures (phases
3-4 depend on it).

Design constraints (see design.md "Provider abstraction"):

* Keep this module dependency-light: plain :mod:`dataclasses` + stdlib only.
  In particular it must import and run with **zero** third-party provider deps
  (no ``litellm``, no network) so the headless engine tests run fully offline.
  The real provider is the LiteLLM-backed adapter (task 2.2); it implements the
  same :class:`ModelClient` protocol in a separate module.
* The catalog uses dataclasses and the artifact schema uses pydantic. Provider
  I/O is low-level plumbing, so dataclasses are used here to avoid pulling
  pydantic into the hot path and to keep ``base.py`` importable anywhere.
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from typing import Any, Callable, Literal, Optional, Protocol, Sequence, runtime_checkable

# A chat role. ``system``/``user``/``assistant`` are the core set; ``tool`` is
# allowed for providers/flows that surface tool/function results as messages.
Role = Literal["system", "user", "assistant", "tool"]

# How a structured (JSON-schema) response was produced. Set by the real adapter
# (task 2.2); recorded on the response type so callers can reason about it.
StructuredMode = Literal["native", "json_mode_fallback"]


@dataclass
class Message:
    """A single chat message exchanged with a model.

    Attributes:
        role: One of ``system``/``user``/``assistant`` (core) or ``tool``.
        content: The message text.
    """

    role: Role
    content: str


@dataclass
class Usage:
    """Token-usage and cost/latency signals for one model call.

    All fields default to zero/``None`` so a client may populate only what the
    underlying provider reports. ``cost_usd`` and ``latency_s`` are optional
    because not every provider returns them.
    """

    prompt_tokens: int = 0
    completion_tokens: int = 0
    total_tokens: int = 0
    cost_usd: Optional[float] = None
    latency_s: Optional[float] = None


@dataclass
class ModelResponse:
    """The normalized result of a single :meth:`ModelClient.complete` call.

    Attributes:
        text: The model's textual completion.
        usage: Token/cost/latency signals for this call.
        raw: Optional provider-native payload, passed through untouched for
            debugging/inspection. ``None`` when not retained.
        structured: Parsed structured output when a ``response_schema`` was
            requested and the client could produce a JSON object. ``None``
            otherwise.
        structured_mode: How the structured output was produced
            (``"native"`` or ``"json_mode_fallback"``), or ``None`` when no
            structured output was requested/produced. Set by the real adapter
            (task 2.2); defined here because it belongs on the response type.
    """

    text: str
    usage: Usage = field(default_factory=Usage)
    raw: Optional[dict] = None
    structured: Optional[dict] = None
    structured_mode: Optional[StructuredMode] = None


@runtime_checkable
class ModelClient(Protocol):
    """Structural contract for any model provider used by the engine.

    A client maps a chat-style message list to a :class:`ModelResponse`. It is a
    :func:`typing.runtime_checkable` :class:`~typing.Protocol`, so any object
    exposing a compatible ``complete`` method satisfies it (tests may
    ``isinstance``-check against it).
    """

    def complete(
        self,
        messages: list[Message],
        model: str,
        params: Optional[dict] = None,
        response_schema: Optional[dict] = None,
    ) -> ModelResponse:
        """Produce a completion for ``messages`` using ``model``.

        Args:
            messages: Ordered chat messages (system/user/assistant/tool).
            model: Provider-qualified model identifier (e.g. ``"gpt-4o"``).
            params: Optional provider parameters (temperature, max_tokens, ...).
            response_schema: Optional JSON Schema. When provided, the client
                should attempt structured output and populate
                :attr:`ModelResponse.structured` and
                :attr:`ModelResponse.structured_mode`.

        Returns:
            A :class:`ModelResponse`. When ``response_schema`` was supplied and
            the client produced a JSON object, ``structured`` is populated and
            ``structured_mode`` records how.
        """
        ...


# Type of a user-supplied responder callable for the mock.
Responder = Callable[
    [list[Message], str, Optional[dict], Optional[dict]],
    "str | ModelResponse",
]


@dataclass
class _Call:
    """A recorded :meth:`MockModelClient.complete` invocation."""

    messages: list[Message]
    model: str
    params: Optional[dict]
    response_schema: Optional[dict]


class MockModelClient:
    """Deterministic, offline implementation of :class:`ModelClient` for tests.

    The mock never touches the network and has no third-party dependencies, so
    engine and gold-case tests are fully reproducible.

    Response source (first match wins):

    1. ``responder`` — a callable ``(messages, model, params, response_schema)
       -> str | ModelResponse`` driving the reply dynamically. A returned
       :class:`ModelResponse` is used as-is; a returned ``str`` becomes the
       response ``text`` (and seeds structured parsing, see below).
    2. ``scripted`` — a list of canned replies consumed in order. Each entry may
       be a ``str`` (used as ``text``) or a :class:`ModelResponse`. Once
       exhausted the mock falls back to the default echo.
    3. default echo — a deterministic string derived from the last user message
       and the model id, so identical inputs always yield identical output.

    Usage numbers are derived deterministically from message/response lengths so
    metrics tests are stable across runs.

    Structured output: when ``complete`` is called with a ``response_schema``,
    the mock returns a ``structured`` dict and sets ``structured_mode="native"``
    (it pretends to be a native structured provider). The dict is taken from the
    reply text when that text is valid JSON; otherwise it is derived
    deterministically from the schema (first ``enum`` value / type default per
    property). This makes it easy to drive judge tests (e.g. an RE binary judge
    expecting ``{"class": "F"|"NF"}``) via ``responder`` or a scripted JSON
    reply.
    """

    def __init__(
        self,
        scripted: Optional[Sequence["str | ModelResponse"]] = None,
        responder: Optional[Responder] = None,
    ) -> None:
        self._responder = responder
        self._scripted: list["str | ModelResponse"] = list(scripted or [])
        self._script_index = 0
        self.calls: list[_Call] = []

    # -- public protocol method ------------------------------------------------

    def complete(
        self,
        messages: list[Message],
        model: str,
        params: Optional[dict] = None,
        response_schema: Optional[dict] = None,
    ) -> ModelResponse:
        """See :meth:`ModelClient.complete`. Deterministic and offline."""
        self.calls.append(
            _Call(
                messages=list(messages),
                model=model,
                params=params,
                response_schema=response_schema,
            )
        )

        reply = self._next_reply(messages, model, params, response_schema)

        if isinstance(reply, ModelResponse):
            response = reply
        else:
            response = ModelResponse(
                text=reply,
                usage=self._usage_for(messages, reply),
            )

        if response_schema is not None and response.structured is None:
            response.structured = self._structured_from(response.text, response_schema)
            response.structured_mode = "native"

        return response

    # -- call-log helpers ------------------------------------------------------

    @property
    def call_count(self) -> int:
        """Number of :meth:`complete` invocations recorded so far."""
        return len(self.calls)

    def reset(self) -> None:
        """Clear the call log and rewind the scripted-reply cursor."""
        self.calls.clear()
        self._script_index = 0

    # -- internals -------------------------------------------------------------

    def _next_reply(
        self,
        messages: list[Message],
        model: str,
        params: Optional[dict],
        response_schema: Optional[dict],
    ) -> "str | ModelResponse":
        if self._responder is not None:
            return self._responder(messages, model, params, response_schema)

        if self._script_index < len(self._scripted):
            reply = self._scripted[self._script_index]
            self._script_index += 1
            return reply

        return self._echo(messages, model)

    @staticmethod
    def _echo(messages: list[Message], model: str) -> str:
        """Deterministic echo of the last user message + model id."""
        last_user = ""
        for message in reversed(messages):
            if message.role == "user":
                last_user = message.content
                break
        return f"[mock:{model}] {last_user}"

    @staticmethod
    def _usage_for(messages: list[Message], text: str) -> Usage:
        """Derive stable token counts from message and response lengths.

        A simple whitespace word count is used as a proxy for tokens so the
        numbers are deterministic and do not depend on any tokenizer library.
        """
        prompt_tokens = sum(len(m.content.split()) for m in messages)
        completion_tokens = len(text.split())
        return Usage(
            prompt_tokens=prompt_tokens,
            completion_tokens=completion_tokens,
            total_tokens=prompt_tokens + completion_tokens,
            cost_usd=0.0,
            latency_s=0.0,
        )

    @staticmethod
    def _structured_from(text: str, schema: dict) -> dict:
        """Return a structured dict for ``schema``.

        Prefer parsing ``text`` as JSON (so scripted/responder JSON replies flow
        through verbatim). When that fails, synthesize a deterministic object
        from the schema's ``properties`` (first ``enum`` value, else a
        type-appropriate default).
        """
        parsed = _try_parse_json(text)
        if isinstance(parsed, dict):
            return parsed
        return _default_object_from_schema(schema)


def _try_parse_json(text: str) -> Any:
    """Best-effort JSON parse; returns ``None`` on failure."""
    try:
        return json.loads(text)
    except (ValueError, TypeError):
        return None


def _default_object_from_schema(schema: dict) -> dict:
    """Build a deterministic object instance from a JSON Schema fragment.

    For each property pick the first ``enum`` value when present, otherwise a
    stable default for its declared ``type``. Unknown shapes yield ``{}``.
    """
    properties = schema.get("properties")
    if not isinstance(properties, dict):
        return {}

    result: dict[str, Any] = {}
    for name, spec in properties.items():
        result[name] = _default_value_from_schema(spec if isinstance(spec, dict) else {})
    return result


def _default_value_from_schema(spec: dict) -> Any:
    """Pick a deterministic value for a single property schema."""
    enum = spec.get("enum")
    if isinstance(enum, list) and enum:
        return enum[0]

    json_type = spec.get("type")
    if json_type == "integer" or json_type == "number":
        return 0
    if json_type == "boolean":
        return False
    if json_type == "array":
        return []
    if json_type == "object":
        return _default_object_from_schema(spec)
    # Default / "string" / unspecified.
    return ""
