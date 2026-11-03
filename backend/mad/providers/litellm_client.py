"""LiteLLM-backed :class:`~mad.providers.base.ModelClient` implementation.

This adapter routes a single ``complete`` call to any supported provider through
`LiteLLM <https://docs.litellm.ai/>`_:

* **Closed-weight** APIs: OpenAI, Anthropic, Gemini, Mistral, DeepSeek.
* **Open-weight / local** OpenAI-compatible endpoints: Ollama, vLLM, LM Studio,
  and a generic ``openai_compatible`` kind for any custom gateway.

It implements the same :class:`~mad.providers.base.ModelClient` protocol as the
offline :class:`~mad.providers.base.MockModelClient`, so the engine is agnostic
to which one it holds.

Design (see design.md "Provider Abstraction & Credentials"):

* The client is decoupled from persistence: the constructor takes plain
  configuration (``kind``/``api_key``/``base_url``/defaults), not DB models. The
  registry (task 2.3) wires DB providers to this class.
* Provider routing is a pure function :func:`_resolve_model_and_kwargs` that maps
  ``(kind, model, base_url, api_key, params)`` to ``(litellm_model, call_kwargs)``
  following LiteLLM's conventions. It makes no network call and is the key unit
  tested offline.
* The actual LiteLLM invocation is isolated behind :meth:`LiteLLMClient._raw_completion`
  (which lazily imports :mod:`litellm`). Tests monkeypatch that single seam, so
  **no test performs a live network call** and importing this module never hard-
  requires litellm or credentials.
* Structured output: when a ``response_schema`` is supplied the adapter first
  attempts provider-native JSON-schema / JSON-object output
  (``structured_mode="native"``). If native structured output is unsupported or
  fails, it falls back to a JSON-mode approach — inject a schema instruction into
  the prompt, call normally, then parse the JSON from the text
  (``structured_mode="json_mode_fallback"``). If parsing still fails, a
  :class:`~mad.errors.ProviderError` is raised (see
  :ref:`structured-output-failure-handling`).
"""

from __future__ import annotations

import json
import time
from dataclasses import dataclass
from typing import Any, Optional

from mad.errors import ProviderError
from mad.providers.base import Message, ModelResponse, StructuredMode, Usage

# Supported provider kinds. ``vllm``/``openai_compatible`` (and LM Studio) all
# route through LiteLLM's OpenAI-compatible custom-endpoint path.
ProviderKind = str

_KNOWN_KINDS = frozenset(
    {
        "openai",
        "anthropic",
        "gemini",
        "mistral",
        "deepseek",
        "ollama",
        "vllm",
        "openai_compatible",
    }
)

# LiteLLM provider-prefix for closed-weight providers that take ``provider/model``.
# OpenAI is intentionally absent: its models are passed through unprefixed.
_PREFIX_BY_KIND = {
    "anthropic": "anthropic",
    "gemini": "gemini",
    "mistral": "mistral",
    "deepseek": "deepseek",
}

# Default Ollama endpoint when no base_url is configured.
_DEFAULT_OLLAMA_BASE_URL = "http://localhost:11434"

# Dummy key for local OpenAI-compatible servers that still require the field.
_LOCAL_DUMMY_API_KEY = "sk-no-key-required"


@dataclass
class _Resolved:
    """Result of :func:`_resolve_model_and_kwargs`.

    Attributes:
        model: The LiteLLM model string (e.g. ``"gpt-4o"``, ``"ollama/llama3"``).
        kwargs: Extra keyword arguments to pass to ``litellm.completion`` beyond
            ``model``/``messages`` (``api_key``, ``api_base``, ``temperature`` …).
    """

    model: str
    kwargs: dict[str, Any]


def _ensure_prefixed(model: str, prefix: str) -> str:
    """Prefix ``model`` with ``prefix/`` unless it already carries a provider tag.

    LiteLLM accepts either a bare model (``claude-3-5-sonnet``) that we prefix, or
    an already-qualified string (``anthropic/claude-3-5-sonnet``) that we leave
    untouched. A leading ``"<prefix>/"`` is treated as already-qualified.
    """
    if model.startswith(f"{prefix}/"):
        return model
    return f"{prefix}/{model}"


def _resolve_model_and_kwargs(
    kind: ProviderKind,
    model: str,
    base_url: Optional[str],
    api_key: Optional[str],
    params: Optional[dict] = None,
) -> _Resolved:
    """Map a provider ``kind`` + ``model`` to a LiteLLM model string and kwargs.

    Pure and network-free — the key unit tested offline. Follows LiteLLM
    conventions:

    * ``openai``: model as-is (``"gpt-4o"``); ``api_key`` passed through.
    * ``anthropic``/``gemini``/``mistral``/``deepseek``: ``"<prefix>/<model>"``
      (unless already prefixed); ``api_key`` passed through.
    * ``ollama``: ``"ollama/<model>"`` with ``api_base`` = ``base_url`` or the
      default ``http://localhost:11434``.
    * ``vllm``/``openai_compatible``: ``"openai/<model>"`` custom-endpoint routing
      with ``api_base`` = ``base_url`` and ``api_key`` (a dummy for keyless local
      servers).

    Args:
        kind: One of the supported provider kinds.
        model: The provider's model identifier.
        base_url: Optional endpoint override (local/compatible/custom gateways).
        api_key: Optional API key.
        params: Optional extra params (temperature, max_tokens, …) merged into the
            returned kwargs. ``response_format`` may be injected by the caller.

    Returns:
        A :class:`_Resolved` with the LiteLLM model string and call kwargs.

    Raises:
        ProviderError: If ``kind`` is not supported.
    """
    if kind not in _KNOWN_KINDS:
        raise ProviderError(
            f"Unsupported provider kind {kind!r}. "
            f"Expected one of: {', '.join(sorted(_KNOWN_KINDS))}."
        )

    kwargs: dict[str, Any] = {}
    # Merge caller params first so explicit routing (api_base etc.) wins below.
    if params:
        kwargs.update(params)

    if kind == "openai":
        resolved_model = model
        if api_key:
            kwargs["api_key"] = api_key
        if base_url:  # custom OpenAI gateway / Azure-style base.
            kwargs["api_base"] = base_url

    elif kind in _PREFIX_BY_KIND:
        resolved_model = _ensure_prefixed(model, _PREFIX_BY_KIND[kind])
        if api_key:
            kwargs["api_key"] = api_key
        if base_url:
            kwargs["api_base"] = base_url

    elif kind == "ollama":
        resolved_model = _ensure_prefixed(model, "ollama")
        kwargs["api_base"] = base_url or _DEFAULT_OLLAMA_BASE_URL
        if api_key:
            kwargs["api_key"] = api_key

    else:  # vllm / openai_compatible -> OpenAI-compatible custom endpoint.
        resolved_model = _ensure_prefixed(model, "openai")
        if base_url:
            kwargs["api_base"] = base_url
        # Local OpenAI-compatible servers still require a non-empty key field.
        kwargs["api_key"] = api_key or _LOCAL_DUMMY_API_KEY

    return _Resolved(model=resolved_model, kwargs=kwargs)


def _messages_to_litellm(messages: list[Message]) -> list[dict[str, str]]:
    """Translate :class:`Message` objects into LiteLLM's ``messages`` format."""
    return [{"role": m.role, "content": m.content} for m in messages]


def _schema_instruction(response_schema: dict) -> str:
    """Build a prompt instruction asking for JSON conforming to ``response_schema``.

    Used by the JSON-mode fallback when native structured output is unavailable.
    """
    schema_text = json.dumps(response_schema, ensure_ascii=False)
    return (
        "You must respond with a single JSON object that strictly conforms to the "
        "following JSON Schema. Output only the JSON object, with no surrounding "
        "prose, markdown, or code fences.\n\nJSON Schema:\n" + schema_text
    )


def _inject_schema_instruction(
    messages: list[dict[str, str]], response_schema: dict
) -> list[dict[str, str]]:
    """Append the JSON-mode schema instruction to the message list.

    The instruction is appended to the trailing system message when present,
    otherwise added as a new system message at the end so it is not lost.
    """
    instruction = _schema_instruction(response_schema)
    out = [dict(m) for m in messages]
    for m in reversed(out):
        if m.get("role") == "system":
            m["content"] = f"{m['content']}\n\n{instruction}"
            return out
    out.append({"role": "system", "content": instruction})
    return out


def _extract_json(text: str) -> Optional[dict]:
    """Best-effort extraction of a JSON object from model ``text``.

    Tries a direct parse first, then strips common ``` fences, then falls back to
    the first ``{...}`` span. Returns the parsed ``dict`` or ``None`` on failure.
    """
    if text is None:
        return None

    candidate = text.strip()

    # Strip a leading/trailing markdown code fence if present.
    if candidate.startswith("```"):
        lines = candidate.splitlines()
        # Drop the opening fence (possibly ```json) and a trailing fence.
        if lines and lines[0].startswith("```"):
            lines = lines[1:]
        if lines and lines[-1].strip() == "```":
            lines = lines[:-1]
        candidate = "\n".join(lines).strip()

    parsed = _try_json(candidate)
    if isinstance(parsed, dict):
        return parsed

    # Fall back to the first balanced-looking {...} span.
    start = candidate.find("{")
    end = candidate.rfind("}")
    if start != -1 and end != -1 and end > start:
        parsed = _try_json(candidate[start : end + 1])
        if isinstance(parsed, dict):
            return parsed

    return None


def _try_json(text: str) -> Any:
    """Parse ``text`` as JSON; return ``None`` on failure."""
    try:
        return json.loads(text)
    except (ValueError, TypeError):
        return None


class LiteLLMClient:
    """A :class:`~mad.providers.base.ModelClient` backed by LiteLLM.

    One instance represents one configured provider (a ``kind`` plus optional
    credentials/endpoint and default params). The engine calls :meth:`complete`
    with per-call ``model``/``params``; constructor defaults are merged underneath
    those per-call params.

    Args:
        kind: Provider kind (``openai``/``anthropic``/``gemini``/``mistral``/
            ``deepseek``/``ollama``/``vllm``/``openai_compatible``).
        api_key: Optional API key (decrypted upstream by the registry).
        base_url: Optional endpoint override for local/compatible/custom gateways.
        default_params: Optional default call params (e.g. ``{"temperature": 0.2}``)
            merged beneath per-call ``params``.

    Raises:
        ProviderError: If ``kind`` is unsupported.
    """

    def __init__(
        self,
        kind: ProviderKind,
        api_key: Optional[str] = None,
        base_url: Optional[str] = None,
        default_params: Optional[dict] = None,
    ) -> None:
        if kind not in _KNOWN_KINDS:
            raise ProviderError(
                f"Unsupported provider kind {kind!r}. "
                f"Expected one of: {', '.join(sorted(_KNOWN_KINDS))}."
            )
        self.kind = kind
        self.api_key = api_key
        self.base_url = base_url
        self.default_params: dict[str, Any] = dict(default_params or {})

    # -- public protocol method ------------------------------------------------

    def complete(
        self,
        messages: list[Message],
        model: str,
        params: Optional[dict] = None,
        response_schema: Optional[dict] = None,
    ) -> ModelResponse:
        """See :meth:`~mad.providers.base.ModelClient.complete`.

        Translates messages, resolves routing, invokes LiteLLM via
        :meth:`_raw_completion`, and normalizes the reply into a
        :class:`ModelResponse`. When ``response_schema`` is given, structured
        output is attempted natively first and falls back to JSON-mode; the path
        taken is recorded in :attr:`ModelResponse.structured_mode`.

        Raises:
            ProviderError: On routing failure, network/provider exception (wrapped
                with the original as ``__cause__``), or an unrecoverable
                structured-output parse failure.
        """
        merged_params: dict[str, Any] = dict(self.default_params)
        if params:
            merged_params.update(params)

        litellm_messages = _messages_to_litellm(messages)

        if response_schema is None:
            response = self._call(litellm_messages, model, merged_params)
            return response

        return self._complete_structured(
            litellm_messages, model, merged_params, response_schema
        )

    # -- structured-output orchestration --------------------------------------

    def _complete_structured(
        self,
        litellm_messages: list[dict[str, str]],
        model: str,
        params: dict[str, Any],
        response_schema: dict,
    ) -> ModelResponse:
        """Attempt native structured output, then fall back to JSON-mode.

        Decision (:ref:`structured-output-failure-handling`): because downstream
        judges require machine-readable output, an unrecoverable structured-output
        failure raises :class:`ProviderError` rather than silently returning
        ``structured=None``.
        """
        native_params = dict(params)
        native_params["response_format"] = {
            "type": "json_schema",
            "json_schema": {
                "name": "mad_structured_output",
                "schema": response_schema,
                "strict": True,
            },
        }

        # 1) Native JSON-schema structured output.
        try:
            response = self._call(litellm_messages, model, native_params)
            parsed = _extract_json(response.text)
            if parsed is not None:
                response.structured = parsed
                response.structured_mode = "native"
                return response
            # Native call succeeded but produced no parseable JSON -> fall back.
        except ProviderError:
            # Native response_format unsupported/rejected by the provider -> fall back.
            pass

        # 2) JSON-mode fallback: instruct the model, parse the text.
        fallback_messages = _inject_schema_instruction(litellm_messages, response_schema)
        response = self._call(fallback_messages, model, params)
        parsed = _extract_json(response.text)
        if parsed is not None:
            response.structured = parsed
            response.structured_mode = "json_mode_fallback"
            return response

        # 3) Unrecoverable: judges need structured output, so fail loudly.
        raise ProviderError(
            "Failed to obtain structured output for model "
            f"{model!r} (kind={self.kind!r}): neither native JSON-schema nor the "
            "JSON-mode fallback produced parseable JSON."
        )

    # -- single invocation + normalization ------------------------------------

    def _call(
        self,
        litellm_messages: list[dict[str, str]],
        model: str,
        params: dict[str, Any],
    ) -> ModelResponse:
        """Resolve routing, invoke LiteLLM, and normalize into a ModelResponse.

        Wraps any provider/network exception in :class:`ProviderError`, preserving
        the original as ``__cause__``.
        """
        resolved = _resolve_model_and_kwargs(
            kind=self.kind,
            model=model,
            base_url=self.base_url,
            api_key=self.api_key,
            params=params,
        )

        call_kwargs = dict(resolved.kwargs)
        call_kwargs["model"] = resolved.model
        call_kwargs["messages"] = litellm_messages

        start = time.perf_counter()
        try:
            raw = self._raw_completion(**call_kwargs)
        except ProviderError:
            raise
        except Exception as exc:  # noqa: BLE001 - normalize all provider errors.
            raise ProviderError(
                f"Model call failed for {resolved.model!r} (kind={self.kind!r}): {exc}"
            ) from exc
        latency_s = time.perf_counter() - start

        return self._to_model_response(raw, resolved.model, latency_s)

    def _to_model_response(
        self, raw: Any, litellm_model: str, latency_s: float
    ) -> ModelResponse:
        """Normalize a LiteLLM response object/dict into a :class:`ModelResponse`."""
        text = _response_text(raw)
        usage = _usage_from_raw(raw, litellm_model, latency_s)
        return ModelResponse(
            text=text,
            usage=usage,
            raw=_raw_as_dict(raw),
        )

    # -- the single monkeypatchable network seam -------------------------------

    def _raw_completion(self, **kwargs: Any) -> Any:
        """Invoke ``litellm.completion(**kwargs)``; the sole network seam.

        :mod:`litellm` is imported lazily here so importing this module never
        hard-requires the dependency or credentials. Tests monkeypatch this method
        (or the module-level :func:`_litellm_completion`) to run fully offline.

        Raises:
            ProviderError: If :mod:`litellm` is not importable.
        """
        return _litellm_completion(**kwargs)


def _litellm_completion(**kwargs: Any) -> Any:
    """Module-level wrapper around ``litellm.completion`` with a lazy import.

    Kept at module scope so it is trivially monkeypatchable and so the lazy import
    guard lives in exactly one place.

    Raises:
        ProviderError: If :mod:`litellm` cannot be imported.
    """
    try:
        import litellm  # type: ignore import-not-found
    except Exception as exc:  # noqa: BLE001
        raise ProviderError(
            "The 'litellm' package is required to make model calls but could not "
            f"be imported: {exc}. Install it with `pip install litellm`."
        ) from exc
    return litellm.completion(**kwargs)


# ---------------------------------------------------------------------------
# Response normalization helpers (tolerant of object- or dict-shaped payloads)
# ---------------------------------------------------------------------------


def _get(obj: Any, key: str, default: Any = None) -> Any:
    """Read ``key`` from a mapping or an attribute off an object."""
    if obj is None:
        return default
    if isinstance(obj, dict):
        return obj.get(key, default)
    return getattr(obj, key, default)


def _response_text(raw: Any) -> str:
    """Extract the assistant text from a LiteLLM-shaped response."""
    choices = _get(raw, "choices") or []
    if not choices:
        return ""
    first = choices[0]
    message = _get(first, "message")
    content = _get(message, "content")
    if content is None:
        # Some providers surface text directly on the choice.
        content = _get(first, "text")
    return content or ""


def _usage_from_raw(raw: Any, litellm_model: str, latency_s: float) -> Usage:
    """Build a :class:`Usage` from a LiteLLM response's usage block + cost/latency."""
    usage_obj = _get(raw, "usage")
    prompt_tokens = int(_get(usage_obj, "prompt_tokens", 0) or 0)
    completion_tokens = int(_get(usage_obj, "completion_tokens", 0) or 0)
    total_tokens = int(
        _get(usage_obj, "total_tokens", prompt_tokens + completion_tokens)
        or (prompt_tokens + completion_tokens)
    )

    return Usage(
        prompt_tokens=prompt_tokens,
        completion_tokens=completion_tokens,
        total_tokens=total_tokens,
        cost_usd=_completion_cost(raw),
        latency_s=latency_s,
    )


def _completion_cost(raw: Any) -> Optional[float]:
    """Best-effort cost via ``litellm.completion_cost``; ``None`` if unavailable."""
    try:
        import litellm  # type: ignore import-not-found

        cost = litellm.completion_cost(completion_response=raw)
        return float(cost) if cost is not None else None
    except Exception:  # noqa: BLE001 - cost is purely best-effort.
        return None


def _raw_as_dict(raw: Any) -> Optional[dict]:
    """Return a plain ``dict`` view of ``raw`` for the response's ``raw`` field.

    LiteLLM responses are often pydantic-ish objects exposing ``model_dump`` /
    ``dict``; fall back to ``None`` when no cheap dict view is available so the
    normalized :class:`ModelResponse` stays JSON-serializable-friendly.
    """
    if raw is None:
        return None
    if isinstance(raw, dict):
        return raw
    for attr in ("model_dump", "dict"):
        method = getattr(raw, attr, None)
        if callable(method):
            try:
                result = method()
                if isinstance(result, dict):
                    return result
            except Exception:  # noqa: BLE001
                continue
    return None
