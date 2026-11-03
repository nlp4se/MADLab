"""Offline unit tests for the provider registry (task 2.3).

Every test here runs fully offline: the registry is constructed with an injected
``client_factory`` that yields :class:`~mad.providers.base.MockModelClient`
instances, so no real :class:`~mad.providers.LiteLLMClient` is ever built and no
network call is made.

Validates: Requirements 8.5, 8.6, 9.2
"""

from __future__ import annotations

import pytest

from mad.errors import ProviderError
from mad.providers import (
    ConnectionResult,
    Message,
    ModelResponse,
    MockModelClient,
    ProviderConfig,
    ProviderRegistry,
    Usage,
)


# ---------------------------------------------------------------------------
# Helpers / fixtures
# ---------------------------------------------------------------------------


class _Spec:
    """Minimal structural stand-in for schema.BaseModelSpec."""

    def __init__(self, provider_id=None, model_key=None):
        self.provider_id = provider_id
        self.model_key = model_key


def _mock_factory():
    """A client_factory that builds a distinct MockModelClient per provider.

    Returns the factory plus a dict mapping provider id -> the built mock, so
    tests can assert caching and inspect recorded calls.
    """
    built: dict[str, MockModelClient] = {}

    def factory(config: ProviderConfig) -> MockModelClient:
        client = MockModelClient()
        built[config.id] = client
        return client

    return factory, built


def _openai_config(provider_id="openai", models=None) -> ProviderConfig:
    return ProviderConfig(
        id=provider_id,
        name="OpenAI",
        kind="openai",
        api_key="sk-test",
        models=models if models is not None else ["gpt-4o"],
    )


def _ollama_config(provider_id="ollama") -> ProviderConfig:
    return ProviderConfig(
        id=provider_id,
        name="Local Ollama",
        kind="ollama",
        base_url="http://localhost:11434",
        models=["llama3"],
    )


# ---------------------------------------------------------------------------
# Registration helpers: add / get_config / list / remove / has
# ---------------------------------------------------------------------------


def test_add_get_list_remove_has():
    factory, _ = _mock_factory()
    registry = ProviderRegistry(client_factory=factory)

    assert registry.has("openai") is False
    assert registry.list_providers() == []

    config = _openai_config()
    registry.add(config)

    assert registry.has("openai") is True
    assert registry.get_config("openai") is config
    assert [c.id for c in registry.list_providers()] == ["openai"]

    registry.remove("openai")
    assert registry.has("openai") is False
    assert registry.list_providers() == []


def test_add_via_constructor():
    factory, _ = _mock_factory()
    registry = ProviderRegistry(
        providers=[_openai_config(), _ollama_config()],
        client_factory=factory,
    )
    assert {c.id for c in registry.list_providers()} == {"openai", "ollama"}


def test_remove_unknown_is_noop():
    factory, _ = _mock_factory()
    registry = ProviderRegistry(client_factory=factory)
    registry.remove("does-not-exist")  # should not raise
    assert registry.list_providers() == []


def test_add_replaces_and_invalidates_cached_client():
    factory, built = _mock_factory()
    registry = ProviderRegistry(providers=[_openai_config()], client_factory=factory)

    first = registry.get_client("openai")
    # Re-add (replace) the provider; the cached client must be dropped.
    registry.add(_openai_config(models=["gpt-4o-mini"]))
    second = registry.get_client("openai")

    assert first is not second


# ---------------------------------------------------------------------------
# get_client: unknown id, caching
# ---------------------------------------------------------------------------


def test_get_client_unknown_raises_provider_error():
    factory, _ = _mock_factory()
    registry = ProviderRegistry(client_factory=factory)
    with pytest.raises(ProviderError) as exc:
        registry.get_client("nope")
    assert "nope" in str(exc.value)


def test_get_client_caches_instance():
    factory, _ = _mock_factory()
    registry = ProviderRegistry(providers=[_openai_config()], client_factory=factory)
    first = registry.get_client("openai")
    second = registry.get_client("openai")
    assert first is second


def test_client_factory_injection_is_used():
    factory, built = _mock_factory()
    registry = ProviderRegistry(providers=[_openai_config()], client_factory=factory)
    client = registry.get_client("openai")
    # The injected factory produced the client (never a real LiteLLMClient).
    assert isinstance(client, MockModelClient)
    assert built["openai"] is client


# ---------------------------------------------------------------------------
# resolve(BaseModelSpec)
# ---------------------------------------------------------------------------


def test_resolve_returns_client_and_model_key():
    factory, built = _mock_factory()
    registry = ProviderRegistry(providers=[_openai_config()], client_factory=factory)

    client, model_key = registry.resolve(_Spec(provider_id="openai", model_key="gpt-4o"))

    assert client is registry.get_client("openai")
    assert model_key == "gpt-4o"


def test_resolve_missing_provider_id_raises():
    factory, _ = _mock_factory()
    registry = ProviderRegistry(client_factory=factory)
    with pytest.raises(ProviderError) as exc:
        registry.resolve(_Spec(provider_id=None, model_key="gpt-4o"))
    assert "provider_id" in str(exc.value)


def test_resolve_missing_model_key_raises():
    factory, _ = _mock_factory()
    registry = ProviderRegistry(providers=[_openai_config()], client_factory=factory)
    with pytest.raises(ProviderError) as exc:
        registry.resolve(_Spec(provider_id="openai", model_key=None))
    assert "model_key" in str(exc.value)


def test_resolve_unknown_provider_raises():
    factory, _ = _mock_factory()
    registry = ProviderRegistry(client_factory=factory)
    with pytest.raises(ProviderError) as exc:
        registry.resolve(_Spec(provider_id="ghost", model_key="gpt-4o"))
    assert "ghost" in str(exc.value)


def test_resolve_heterogeneous_two_providers_two_clients():
    factory, _ = _mock_factory()
    registry = ProviderRegistry(
        providers=[_openai_config(), _ollama_config()],
        client_factory=factory,
    )

    client_a, key_a = registry.resolve(_Spec(provider_id="openai", model_key="gpt-4o"))
    client_b, key_b = registry.resolve(_Spec(provider_id="ollama", model_key="llama3"))

    assert client_a is not client_b
    assert key_a == "gpt-4o"
    assert key_b == "llama3"


# ---------------------------------------------------------------------------
# test_connection: success / failure / unknown / explicit model / ad-hoc config
# ---------------------------------------------------------------------------


def test_test_connection_success_reports_ok_latency_model():
    def factory(config: ProviderConfig) -> MockModelClient:
        # Return a canned response carrying a latency signal.
        return MockModelClient(
            responder=lambda *_: ModelResponse(
                text="OK",
                usage=Usage(latency_s=0.012),
            )
        )

    registry = ProviderRegistry(providers=[_openai_config()], client_factory=factory)
    result = registry.test_connection("openai")

    assert isinstance(result, ConnectionResult)
    assert result.ok is True
    assert result.model == "gpt-4o"
    assert result.latency_s == 0.012
    assert "openai" in result.message


def test_test_connection_failure_captured_not_raised():
    class _Boom(MockModelClient):
        def complete(self, *args, **kwargs):  # noqa: D401 - test double
            raise RuntimeError("network down")

    registry = ProviderRegistry(
        providers=[_openai_config()],
        client_factory=lambda config: _Boom(),
    )
    result = registry.test_connection("openai")

    assert result.ok is False
    assert "network down" in result.message
    assert result.model == "gpt-4o"


def test_test_connection_unknown_provider_returns_not_ok():
    factory, _ = _mock_factory()
    registry = ProviderRegistry(client_factory=factory)
    result = registry.test_connection("nope")
    assert result.ok is False
    assert "nope" in result.message


def test_test_connection_no_models_returns_not_ok():
    factory, _ = _mock_factory()
    registry = ProviderRegistry(
        providers=[_openai_config(models=[])],
        client_factory=factory,
    )
    result = registry.test_connection("openai")
    assert result.ok is False
    assert "no configured models" in result.message


def test_test_connection_explicit_model_overrides_default():
    captured = {}

    def factory(config: ProviderConfig) -> MockModelClient:
        def responder(messages, model, params, schema):
            captured["model"] = model
            return "OK"

        return MockModelClient(responder=responder)

    registry = ProviderRegistry(providers=[_openai_config()], client_factory=factory)
    result = registry.test_connection("openai", model="gpt-4o-mini")

    assert result.ok is True
    assert result.model == "gpt-4o-mini"
    assert captured["model"] == "gpt-4o-mini"


def test_test_connection_adhoc_config_not_registered():
    factory, built = _mock_factory()
    registry = ProviderRegistry(client_factory=factory)

    adhoc = _openai_config(provider_id="unsaved")
    result = registry.test_connection(adhoc)

    assert result.ok is True
    assert result.model == "gpt-4o"
    # The ad-hoc test must not register or cache the provider.
    assert registry.has("unsaved") is False
