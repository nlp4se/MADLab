"""Offline unit tests for the LiteLLM-backed provider adapter (task 2.2).

Every test here is network-free: the single ``litellm.completion`` seam is
monkeypatched (via ``LiteLLMClient._raw_completion`` or the module-level
``_litellm_completion``) and the pure routing function is tested directly. No
test performs a live LiteLLM call.

Validates: Requirements 8.2, 9.1, 9.3, 9.4
"""

import json

import pytest

from mad.errors import ProviderError
from mad.providers import LiteLLMClient, Message, ModelResponse, Usage
from mad.providers.litellm_client import (
    _DEFAULT_OLLAMA_BASE_URL,
    _resolve_model_and_kwargs,
)


# ---------------------------------------------------------------------------
# Helpers: a canned LiteLLM-shaped response object
# ---------------------------------------------------------------------------


class _FakeMessage:
    def __init__(self, content):
        self.content = content


class _FakeChoice:
    def __init__(self, content):
        self.message = _FakeMessage(content)


class _FakeUsage:
    def __init__(self, prompt_tokens, completion_tokens, total_tokens):
        self.prompt_tokens = prompt_tokens
        self.completion_tokens = completion_tokens
        self.total_tokens = total_tokens


class _FakeResponse:
    """Minimal object mimicking a LiteLLM ``ModelResponse`` (attribute access)."""

    def __init__(self, content, usage=None):
        self.choices = [_FakeChoice(content)]
        self.usage = usage

    def model_dump(self):
        return {"choices": [{"message": {"content": self.choices[0].message.content}}]}


def _messages():
    return [
        Message(role="system", content="You are a classifier."),
        Message(role="user", content="Is this a security requirement?"),
    ]


def _stub_raw(client, response, recorder=None):
    """Monkeypatch ``client._raw_completion`` to return ``response``.

    If ``recorder`` is a list, each call's kwargs are appended to it.
    """

    def _raw(**kwargs):
        if recorder is not None:
            recorder.append(kwargs)
        if isinstance(response, Exception):
            raise response
        return response

    client._raw_completion = _raw  # type: ignore[assignment]


# ---------------------------------------------------------------------------
# _resolve_model_and_kwargs — provider routing (pure, no network)
# ---------------------------------------------------------------------------


def test_resolve_openai_passes_model_as_is_with_key():
    r = _resolve_model_and_kwargs("openai", "gpt-4o", None, "sk-abc", None)
    assert r.model == "gpt-4o"
    assert r.kwargs["api_key"] == "sk-abc"
    assert "api_base" not in r.kwargs


def test_resolve_openai_with_base_url_sets_api_base():
    r = _resolve_model_and_kwargs("openai", "gpt-4o", "https://gw.example", "k", None)
    assert r.model == "gpt-4o"
    assert r.kwargs["api_base"] == "https://gw.example"


@pytest.mark.parametrize(
    "kind,model,expected",
    [
        ("anthropic", "claude-3-5-sonnet", "anthropic/claude-3-5-sonnet"),
        ("gemini", "gemini-1.5-pro", "gemini/gemini-1.5-pro"),
        ("mistral", "mistral-large-latest", "mistral/mistral-large-latest"),
        ("deepseek", "deepseek-chat", "deepseek/deepseek-chat"),
    ],
)
def test_resolve_closed_weight_prefixes_model(kind, model, expected):
    r = _resolve_model_and_kwargs(kind, model, None, "key-123", None)
    assert r.model == expected
    assert r.kwargs["api_key"] == "key-123"


def test_resolve_does_not_double_prefix_already_qualified_model():
    r = _resolve_model_and_kwargs(
        "anthropic", "anthropic/claude-3-5-sonnet", None, "k", None
    )
    assert r.model == "anthropic/claude-3-5-sonnet"


def test_resolve_ollama_default_base_url():
    r = _resolve_model_and_kwargs("ollama", "llama3", None, None, None)
    assert r.model == "ollama/llama3"
    assert r.kwargs["api_base"] == _DEFAULT_OLLAMA_BASE_URL


def test_resolve_ollama_respects_explicit_base_url():
    r = _resolve_model_and_kwargs("ollama", "llama3", "http://host:9999", None, None)
    assert r.model == "ollama/llama3"
    assert r.kwargs["api_base"] == "http://host:9999"


def test_resolve_vllm_uses_openai_routing_with_base_and_dummy_key():
    r = _resolve_model_and_kwargs("vllm", "my-model", "http://localhost:8000/v1", None, None)
    assert r.model == "openai/my-model"
    assert r.kwargs["api_base"] == "http://localhost:8000/v1"
    # Keyless local server still gets a non-empty key field.
    assert r.kwargs["api_key"]


def test_resolve_openai_compatible_passes_real_key_when_given():
    r = _resolve_model_and_kwargs(
        "openai_compatible", "m", "http://gw/v1", "real-key", None
    )
    assert r.model == "openai/m"
    assert r.kwargs["api_base"] == "http://gw/v1"
    assert r.kwargs["api_key"] == "real-key"


def test_resolve_merges_params():
    r = _resolve_model_and_kwargs(
        "openai", "gpt-4o", None, "k", {"temperature": 0.3, "max_tokens": 128}
    )
    assert r.kwargs["temperature"] == 0.3
    assert r.kwargs["max_tokens"] == 128


def test_resolve_unknown_kind_raises_provider_error():
    with pytest.raises(ProviderError):
        _resolve_model_and_kwargs("not-a-kind", "m", None, None, None)


def test_constructor_rejects_unknown_kind():
    with pytest.raises(ProviderError):
        LiteLLMClient(kind="bogus")


# ---------------------------------------------------------------------------
# complete() — happy path + usage
# ---------------------------------------------------------------------------


def test_complete_happy_path_text_and_usage():
    client = LiteLLMClient(kind="openai", api_key="sk-x")
    raw = _FakeResponse(
        "It is a security requirement.",
        usage=_FakeUsage(prompt_tokens=11, completion_tokens=5, total_tokens=16),
    )
    recorder = []
    _stub_raw(client, raw, recorder)

    resp = client.complete(_messages(), model="gpt-4o", params={"temperature": 0.0})

    assert isinstance(resp, ModelResponse)
    assert resp.text == "It is a security requirement."
    assert isinstance(resp.usage, Usage)
    assert resp.usage.prompt_tokens == 11
    assert resp.usage.completion_tokens == 5
    assert resp.usage.total_tokens == 16
    assert resp.usage.latency_s is not None

    # Routing/kwargs reached the seam correctly.
    assert len(recorder) == 1
    sent = recorder[0]
    assert sent["model"] == "gpt-4o"
    assert sent["api_key"] == "sk-x"
    assert sent["temperature"] == 0.0
    assert sent["messages"] == [
        {"role": "system", "content": "You are a classifier."},
        {"role": "user", "content": "Is this a security requirement?"},
    ]


def test_default_params_merged_under_call_params():
    client = LiteLLMClient(kind="openai", api_key="k", default_params={"temperature": 0.9})
    recorder = []
    _stub_raw(client, _FakeResponse("ok"), recorder)

    client.complete(_messages(), model="gpt-4o", params={"temperature": 0.1})
    assert recorder[0]["temperature"] == 0.1  # per-call wins

    client.complete(_messages(), model="gpt-4o")
    assert recorder[1]["temperature"] == 0.9  # default applies when not overridden


def test_usage_absent_defaults_to_zero():
    client = LiteLLMClient(kind="openai", api_key="k")
    _stub_raw(client, _FakeResponse("no usage block", usage=None))
    resp = client.complete(_messages(), model="gpt-4o")
    assert resp.usage.prompt_tokens == 0
    assert resp.usage.total_tokens == 0


# ---------------------------------------------------------------------------
# Structured output — native path
# ---------------------------------------------------------------------------


_SCHEMA = {
    "type": "object",
    "properties": {"class": {"type": "string", "enum": ["F", "NF"]}},
    "required": ["class"],
}


def test_structured_native_path():
    client = LiteLLMClient(kind="openai", api_key="k")
    raw = _FakeResponse(json.dumps({"class": "NF"}))
    recorder = []
    _stub_raw(client, raw, recorder)

    resp = client.complete(_messages(), model="gpt-4o", response_schema=_SCHEMA)

    assert resp.structured == {"class": "NF"}
    assert resp.structured_mode == "native"
    # Native attempt sends response_format to the provider.
    assert recorder[0]["response_format"]["type"] == "json_schema"


# ---------------------------------------------------------------------------
# Structured output — JSON-mode fallback path
# ---------------------------------------------------------------------------


def test_structured_fallback_when_native_call_raises():
    """First (native) call raises; second (fallback) call returns JSON text."""
    client = LiteLLMClient(kind="ollama", base_url="http://localhost:11434")

    calls = []

    def _raw(**kwargs):
        calls.append(kwargs)
        if "response_format" in kwargs:
            raise RuntimeError("response_format not supported by this provider")
        return _FakeResponse(json.dumps({"class": "F"}))

    client._raw_completion = _raw  # type: ignore[assignment]

    resp = client.complete(_messages(), model="llama3", response_schema=_SCHEMA)

    assert resp.structured == {"class": "F"}
    assert resp.structured_mode == "json_mode_fallback"
    assert len(calls) == 2
    # Fallback call must NOT carry response_format and must inject a JSON instruction.
    assert "response_format" not in calls[1]
    system_msgs = [m for m in calls[1]["messages"] if m["role"] == "system"]
    assert any("JSON" in m["content"] for m in system_msgs)


def test_structured_fallback_when_native_returns_unparseable_text():
    """Native call succeeds but yields no JSON; fallback recovers it."""
    client = LiteLLMClient(kind="openai", api_key="k")

    responses = [
        _FakeResponse("Sorry, I cannot comply."),  # native, no JSON
        _FakeResponse("```json\n{\"class\": \"NF\"}\n```"),  # fallback, fenced JSON
    ]
    calls = []

    def _raw(**kwargs):
        calls.append(kwargs)
        return responses[len(calls) - 1]

    client._raw_completion = _raw  # type: ignore[assignment]

    resp = client.complete(_messages(), model="gpt-4o", response_schema=_SCHEMA)
    assert resp.structured == {"class": "NF"}
    assert resp.structured_mode == "json_mode_fallback"
    assert len(calls) == 2


def test_structured_unrecoverable_raises_provider_error():
    client = LiteLLMClient(kind="openai", api_key="k")
    # Both native and fallback return non-JSON text.
    _stub_raw(client, _FakeResponse("absolutely no json here"))

    with pytest.raises(ProviderError) as exc:
        client.complete(_messages(), model="gpt-4o", response_schema=_SCHEMA)
    assert "structured output" in str(exc.value).lower()


# ---------------------------------------------------------------------------
# Error wrapping
# ---------------------------------------------------------------------------


def test_provider_exception_wrapped_in_provider_error():
    client = LiteLLMClient(kind="openai", api_key="k")
    boom = ConnectionError("network down")
    _stub_raw(client, boom)

    with pytest.raises(ProviderError) as exc:
        client.complete(_messages(), model="gpt-4o")
    assert isinstance(exc.value.__cause__, ConnectionError)
    assert "gpt-4o" in str(exc.value)


def test_missing_litellm_raises_provider_error(monkeypatch):
    """The lazy-import guard surfaces a ProviderError, not an ImportError."""
    import builtins

    from mad.providers import litellm_client as mod

    real_import = builtins.__import__

    def _fake_import(name, *args, **kwargs):
        if name == "litellm":
            raise ImportError("no litellm")
        return real_import(name, *args, **kwargs)

    monkeypatch.setattr(builtins, "__import__", _fake_import)

    with pytest.raises(ProviderError):
        mod._litellm_completion(model="gpt-4o", messages=[])


# ---------------------------------------------------------------------------
# Module imports without litellm / credentials
# ---------------------------------------------------------------------------


def test_module_imports_without_network_or_credentials():
    # Importing and constructing must not touch litellm or the network.
    from mad.providers import litellm_client as mod

    client = mod.LiteLLMClient(kind="deepseek", api_key="k")
    assert client.kind == "deepseek"
