"""Provider registry: resolve participant model bindings to usable clients.

This module turns a participant's ``(provider_id, model_key)`` binding into a
concrete :class:`~mad.providers.base.ModelClient` that the engine can call, and
offers a lightweight :meth:`ProviderRegistry.test_connection` connectivity check
for the UI (Req 8.5).

Design (see design.md "Provider Abstraction & Credentials"):

* **Decoupled from persistence.** The registry holds plain
  :class:`ProviderConfig` structures, not DB models. The app layer wires DB
  providers into configs later; nothing here imports web/DB dependencies.
* **Heterogeneous models in one debate (Req 9.2)** fall out naturally: each
  node's :class:`~mad.taxonomy.schema.BaseModelSpec` resolves independently, so
  different nodes can resolve to different providers/clients within a single
  debate.
* **Lazy, injectable client construction.** A :class:`LiteLLMClient` is built on
  demand and cached per provider. The ``client_factory`` seam lets tests (and the
  gold-case engine tests, task 3.6) substitute a
  :class:`~mad.providers.base.MockModelClient`, so importing this module and
  building a registry stay fully offline — no litellm import, no network.

Execution-time validation of model bindings lives here: the artifact schema
allows ``provider_id``/``model_key`` to be ``None`` at author time, and
:meth:`ProviderRegistry.resolve` is where that nullability is checked and
rejected with a clear :class:`~mad.errors.ProviderError` at run time.
"""

from __future__ import annotations

import time
from dataclasses import dataclass, field
from typing import Any, Callable, Optional, Union

from mad.errors import ProviderError
from mad.providers.base import Message, ModelClient
from mad.providers.litellm_client import LiteLLMClient

# A factory that builds a :class:`ModelClient` from a :class:`ProviderConfig`.
# Defaults to constructing a real :class:`LiteLLMClient`; tests inject their own
# to substitute a :class:`~mad.providers.base.MockModelClient`.
ClientFactory = Callable[["ProviderConfig"], ModelClient]

# Accepted by :meth:`ProviderRegistry.test_connection`: either a known provider
# id (resolved from the registry) or an ad-hoc :class:`ProviderConfig` (used by
# the UI to test a provider before it is saved).
ProviderRef = Union[str, "ProviderConfig"]


@dataclass
class ProviderConfig:
    """Plain, persistence-free description of one configured provider.

    Attributes:
        id: Stable provider identifier used by participants' model bindings.
        name: Human-readable label for the UI.
        kind: Provider kind routed by :class:`LiteLLMClient` (``openai``/
            ``anthropic``/``gemini``/``mistral``/``deepseek``/``ollama``/``vllm``/
            ``openai_compatible``).
        api_key: Optional API key (decrypted upstream by the app layer). Local
            OpenAI-compatible servers may leave this ``None``.
        base_url: Optional endpoint override for local/compatible/custom gateways.
        models: Available model keys for this provider; the first is used as the
            default connectivity-test target.
        default_params: Optional default call params merged beneath per-call
            params by the underlying client.
    """

    id: str
    name: str
    kind: str
    api_key: Optional[str] = None
    base_url: Optional[str] = None
    models: list[str] = field(default_factory=list)
    default_params: dict[str, Any] = field(default_factory=dict)


@dataclass
class ConnectionResult:
    """Outcome of a :meth:`ProviderRegistry.test_connection` call.

    Never raised — connectivity failures are reported as ``ok=False`` with a
    human-readable ``message`` so the UI can surface them without exception
    handling.

    Attributes:
        ok: Whether the minimal ping call succeeded.
        message: Success summary or the error message on failure.
        latency_s: Round-trip latency in seconds when measured, else ``None``.
        model: The model key that was pinged, when known.
    """

    ok: bool
    message: str
    latency_s: Optional[float] = None
    model: Optional[str] = None


def _default_client_factory(config: ProviderConfig) -> ModelClient:
    """Build a real :class:`LiteLLMClient` from ``config`` (lazy by construction).

    Importing :mod:`mad.providers.litellm_client` does not import litellm; the
    dependency is only touched when the client actually makes a call. Building a
    client here therefore stays offline.
    """
    return LiteLLMClient(
        kind=config.kind,
        api_key=config.api_key,
        base_url=config.base_url,
        default_params=config.default_params,
    )


class ProviderRegistry:
    """Resolve model bindings to clients and run connectivity checks.

    Holds a set of :class:`ProviderConfig` keyed by ``id`` and caches one
    :class:`ModelClient` per provider (built lazily on first use). Supports
    heterogeneous models within a single debate: distinct ``provider_id`` values
    resolve to distinct cached clients.

    Args:
        providers: Optional initial provider configs to register.
        client_factory: Builds a :class:`ModelClient` from a
            :class:`ProviderConfig`. Defaults to constructing a real
            :class:`LiteLLMClient`; inject a factory returning a
            :class:`~mad.providers.base.MockModelClient` to run fully offline.
    """

    def __init__(
        self,
        providers: Optional[list[ProviderConfig]] = None,
        client_factory: Optional[ClientFactory] = None,
    ) -> None:
        self._client_factory: ClientFactory = client_factory or _default_client_factory
        self._providers: dict[str, ProviderConfig] = {}
        self._clients: dict[str, ModelClient] = {}
        for config in providers or []:
            self.add(config)

    # -- registration helpers --------------------------------------------------

    def add(self, config: ProviderConfig) -> None:
        """Register (or replace) ``config`` and drop any cached client for its id.

        Replacing a provider invalidates its cached client so subsequent
        :meth:`get_client` calls reflect the new configuration.
        """
        self._providers[config.id] = config
        self._clients.pop(config.id, None)

    def remove(self, provider_id: str) -> None:
        """Remove the provider ``provider_id`` and its cached client, if present.

        Idempotent: removing an unknown id is a no-op.
        """
        self._providers.pop(provider_id, None)
        self._clients.pop(provider_id, None)

    def has(self, provider_id: str) -> bool:
        """Return whether ``provider_id`` is registered."""
        return provider_id in self._providers

    def list_providers(self) -> list[ProviderConfig]:
        """Return the registered provider configs (insertion order)."""
        return list(self._providers.values())

    def get_config(self, provider_id: str) -> ProviderConfig:
        """Return the :class:`ProviderConfig` for ``provider_id``.

        Raises:
            ProviderError: If ``provider_id`` is not registered.
        """
        try:
            return self._providers[provider_id]
        except KeyError:
            raise ProviderError(self._unknown_message(provider_id)) from None

    # -- client resolution -----------------------------------------------------

    def get_client(self, provider_id: str) -> ModelClient:
        """Return the cached client for ``provider_id``, building it on first use.

        The client is constructed via the injected ``client_factory`` and cached,
        so repeated calls return the same instance.

        Raises:
            ProviderError: If ``provider_id`` is not registered.
        """
        cached = self._clients.get(provider_id)
        if cached is not None:
            return cached

        config = self.get_config(provider_id)
        client = self._client_factory(config)
        self._clients[provider_id] = client
        return client

    def resolve(self, spec: Any) -> tuple[ModelClient, str]:
        """Resolve a :class:`~mad.taxonomy.schema.BaseModelSpec` to ``(client, model_key)``.

        This is the execution-time validation point for model bindings: the
        schema permits ``provider_id``/``model_key`` to be ``None`` at author
        time, and they are rejected here with a clear message when missing or
        unknown.

        Args:
            spec: An object exposing ``provider_id`` and ``model_key`` (a
                :class:`~mad.taxonomy.schema.BaseModelSpec`). Accepted
                structurally to avoid importing the pydantic schema here.

        Returns:
            A ``(client, model_key)`` pair ready for ``client.complete(...)``.

        Raises:
            ProviderError: If ``provider_id`` or ``model_key`` is missing, or if
                ``provider_id`` is not registered.
        """
        provider_id = getattr(spec, "provider_id", None)
        model_key = getattr(spec, "model_key", None)

        if not provider_id:
            raise ProviderError(
                "Cannot resolve model binding: no provider_id is set on the "
                "base-model spec. Bind the participant to a configured provider "
                "before running the debate."
            )
        if not model_key:
            raise ProviderError(
                f"Cannot resolve model binding for provider {provider_id!r}: no "
                "model_key is set on the base-model spec. Select a model before "
                "running the debate."
            )
        if not self.has(provider_id):
            raise ProviderError(self._unknown_message(provider_id))

        return self.get_client(provider_id), model_key

    # -- connectivity check ----------------------------------------------------

    def test_connection(
        self, provider: ProviderRef, model: Optional[str] = None
    ) -> ConnectionResult:
        """Issue a minimal ping and report connectivity without raising.

        Resolves ``provider`` (a registered id or an ad-hoc
        :class:`ProviderConfig`) to a client and issues a tiny one-token
        completion. Any failure — unknown provider, missing model, or a provider
        exception — is captured and returned as ``ok=False`` with the error
        message; this method never raises.

        Args:
            provider: A registered provider id or an ad-hoc
                :class:`ProviderConfig` (lets the UI test an unsaved provider).
            model: Optional model key to ping. Defaults to the provider's first
                configured model.

        Returns:
            A :class:`ConnectionResult` describing the outcome.
        """
        try:
            client, config = self._client_and_config_for(provider)
        except ProviderError as exc:
            return ConnectionResult(ok=False, message=str(exc))

        ping_model = model or (config.models[0] if config.models else None)
        if not ping_model:
            return ConnectionResult(
                ok=False,
                message=(
                    f"Provider {config.id!r} has no configured models to test. "
                    "Add a model key or pass an explicit model."
                ),
            )

        messages = [
            Message(role="user", content="Reply with 'OK' and nothing else."),
        ]
        params = {"max_tokens": 1}

        start = time.perf_counter()
        try:
            response = client.complete(messages=messages, model=ping_model, params=params)
        except Exception as exc:  # noqa: BLE001 - connectivity never raises upward.
            latency_s = time.perf_counter() - start
            return ConnectionResult(
                ok=False,
                message=f"Connection to provider {config.id!r} failed: {exc}",
                latency_s=latency_s,
                model=ping_model,
            )
        latency_s = time.perf_counter() - start

        reported_latency = (
            response.usage.latency_s
            if response.usage is not None and response.usage.latency_s is not None
            else latency_s
        )
        return ConnectionResult(
            ok=True,
            message=f"Connected to provider {config.id!r} (model {ping_model!r}).",
            latency_s=reported_latency,
            model=ping_model,
        )

    # -- internals -------------------------------------------------------------

    def _client_and_config_for(
        self, provider: ProviderRef
    ) -> tuple[ModelClient, ProviderConfig]:
        """Return ``(client, config)`` for a registered id or an ad-hoc config.

        Ad-hoc configs are built through the injected factory but not cached, so a
        pre-save UI test does not mutate the registry.
        """
        if isinstance(provider, ProviderConfig):
            return self._client_factory(provider), provider
        config = self.get_config(provider)
        return self.get_client(provider), config

    def _unknown_message(self, provider_id: str) -> str:
        """Build an actionable 'unknown provider' message listing known ids."""
        known = ", ".join(sorted(self._providers)) or "none"
        return (
            f"Unknown provider id {provider_id!r}. "
            f"Registered providers: {known}."
        )
