"""Provider service layer (Req 8).

This service sits between the providers router and the three things it must
coordinate:

* **persistence** — the :class:`app.db.models.Provider` ORM model (metadata +
  the *encrypted* API key, never plaintext);
* **security** — :func:`app.security.crypto.encrypt_api_key` on save and
  :class:`~app.security.crypto.CredentialCipher` for decryption at call time
  (decryption happens only here, transiently, never in the router or response);
* **engine** — the provider :class:`~mad.providers.registry.ProviderRegistry`
  and its :meth:`~mad.providers.registry.ProviderRegistry.test_connection`, via
  a :class:`~mad.providers.registry.ProviderConfig` built from the stored row.

It owns all the business logic so the router stays a thin transport shell and
the engine/security layers stay web-agnostic (layering per Req 12.2: ``routers
-> services -> engine/persistence``).

Key invariant (Req 8.4): nothing returned by this service carries the API key.
Every read path produces a :class:`~app.schemas.providers.ProviderResponse`
whose only key-related field is ``has_key``. The plaintext key enters only
through create/update *requests*, is encrypted immediately, and the ciphertext
never leaves this layer except transiently inside :func:`test_connection`, where
it is decrypted in-process and handed to the engine for a single ping.

Responsibilities:

* **CRUD** (Req 8.1, 8.2, 8.3): list, create (encrypt the write-only key on
  save), get, update (write-only key: replace only when a new key is supplied;
  omitting it keeps the stored ciphertext; explicit ``null`` clears it), delete.
* **Connectivity test** (Req 8.5): build a :class:`ProviderConfig` (decrypting
  the stored key at call time) and run ``test_connection`` through the engine
  registry, reporting success or a clear error without raising.
"""

from __future__ import annotations

from typing import Any, Callable, Optional

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.db.models import Provider
from app.provider_family import check_family_for_kind, effective_family
from app.schemas.providers import (
    ProviderCreateRequest,
    ProviderResponse,
    ProviderTestResponse,
    ProviderUpdateRequest,
)
from app.security.crypto import CredentialError, decrypt_api_key, encrypt_api_key
from mad.errors import ConfigValidationError, ProviderError
from mad.providers.registry import ProviderConfig, ProviderRegistry
from mad.taxonomy.schema import MADConfig

# A factory that builds the engine registry used for connectivity tests. The
# default builds a plain :class:`ProviderRegistry` (which lazily constructs a
# real LiteLLM client only when it actually pings). Tests inject their own to
# substitute an offline client factory, so no network call is ever made.
RegistryFactory = Callable[[], ProviderRegistry]


def _default_registry_factory() -> ProviderRegistry:
    """Build a registry with the engine's default (LiteLLM) client factory."""
    return ProviderRegistry()


# Sentinel distinguishing "api_key omitted" (keep) from "api_key=None" (clear)
# when a caller passes the raw value rather than the request object.
_KEEP = object()


class ProviderNotFound(ProviderError):
    """Raised when a provider id does not exist.

    Subclasses :class:`~mad.errors.ProviderError` so it flows through the domain
    error machinery; the router translates it to a 404 explicitly rather than
    relying on the default 502 mapping.
    """


class InvalidProviderFamily(ConfigValidationError):
    """A requested family contradicts the provider's (fixed) kind (task 11.9).

    Subclasses :class:`~mad.errors.ConfigValidationError` so the global handler
    maps it to 422 with the structured envelope.
    """


# ---------------------------------------------------------------------------
# Row <-> response helpers
# ---------------------------------------------------------------------------


def _iso(value: Any) -> Optional[str]:
    """Render a datetime column as an ISO-8601 string, or ``None``."""
    if value is None:
        return None
    try:
        return value.isoformat()
    except AttributeError:  # pragma: no cover - defensive
        return str(value)


def _to_response(row: Provider) -> ProviderResponse:
    """Project a :class:`Provider` row to the key-free response shape (Req 8.4).

    The only key-derived value exposed is ``has_key``; neither the plaintext nor
    the stored ciphertext is read into the response.
    """
    return ProviderResponse(
        id=row.id,
        name=row.name,
        kind=row.kind,
        base_url=row.base_url,
        models=list(row.models or []),
        family=effective_family(row.kind, row.family),
        has_key=row.has_key,
        created_at=_iso(row.created_at),
        updated_at=_iso(row.updated_at),
    )


def _get_row(session: Session, provider_id: int) -> Provider:
    row = session.get(Provider, provider_id)
    if row is None:
        raise ProviderNotFound(f"provider {provider_id} not found")
    return row


def _encrypt_optional(api_key: Optional[str]) -> Optional[str]:
    """Encrypt a non-empty key, or return ``None`` for a missing/empty key.

    An empty or missing key means "no key" and is stored as ``NULL`` ciphertext
    rather than an encrypted empty string (the cipher rejects empty plaintext).
    """
    if not api_key:
        return None
    return encrypt_api_key(api_key)


# ---------------------------------------------------------------------------
# CRUD
# ---------------------------------------------------------------------------


def list_providers(session: Session) -> list[ProviderResponse]:
    """Return all providers as key-free response rows (Req 8.1), by id ascending."""
    rows = session.scalars(select(Provider).order_by(Provider.id.asc())).all()
    return [_to_response(row) for row in rows]


def get_provider(session: Session, provider_id: int) -> ProviderResponse:
    """Return a single provider (metadata + ``has_key``), or raise ``ProviderNotFound``."""
    return _to_response(_get_row(session, provider_id))


def create_provider(session: Session, body: ProviderCreateRequest) -> ProviderResponse:
    """Create a provider, encrypting the write-only API key on save (Req 8.1-8.4).

    The plaintext key (if any) is encrypted immediately via the security layer;
    only the ciphertext is persisted and the response never carries either.
    """
    row = Provider(
        name=body.name,
        kind=body.kind,
        base_url=body.base_url,
        models=list(body.models or []),
        encrypted_api_key=_encrypt_optional(body.api_key),
        # Already validated against the kind by the request model; a fixed
        # kind's (matching) value is stored as NULL since it is derived.
        family=check_family_for_kind(body.kind, body.family),
    )
    session.add(row)
    session.flush()
    return _to_response(row)


def update_provider(
    session: Session,
    provider_id: int,
    body: ProviderUpdateRequest,
) -> ProviderResponse:
    """Update a provider (Req 8.1, 8.3, 8.4).

    Metadata fields are patched when present. The API key is **write-only** and
    tri-state, decided from whether ``api_key`` was present in the request body:

    * omitted      -> keep the stored ciphertext unchanged (never re-encrypted);
    * non-empty    -> replace the stored ciphertext with the new encrypted key;
    * explicit null -> clear the stored key.

    Presence is read from ``body.model_fields_set`` so a client can patch
    metadata without resending (and thus without ever exposing) the key.
    """
    row = _get_row(session, provider_id)

    # Family (task 11.9), validated against the *resulting* kind before any
    # field is touched so a rejected request leaves the row unchanged:
    # * present (value or null) -> validate + store (null = kind default);
    # * omitted and the kind changes -> reset to the new kind's default;
    # * omitted, same kind -> keep the stored choice.
    new_kind = body.kind if body.kind is not None else row.kind
    kind_changed = new_kind != row.kind
    if "family" in body.model_fields_set:
        try:
            new_family = check_family_for_kind(new_kind, body.family)
        except ValueError as exc:
            raise InvalidProviderFamily(str(exc)) from exc
    elif kind_changed:
        new_family = None
    else:
        new_family = row.family

    if body.name is not None:
        row.name = body.name
    if body.kind is not None:
        row.kind = body.kind
    row.family = new_family
    if "base_url" in body.model_fields_set:
        row.base_url = body.base_url
    if body.models is not None:
        row.models = list(body.models)

    if "api_key" in body.model_fields_set:
        # Present in the payload: null clears, a value replaces. Omission (the
        # else branch) leaves the stored ciphertext untouched.
        row.encrypted_api_key = _encrypt_optional(body.api_key)

    session.flush()
    return _to_response(row)


def provider_families(session: Session) -> dict[str, str]:
    """Map each stored provider's id (as a string, the artifact binding) to its family."""
    rows = session.scalars(select(Provider)).all()
    return {str(row.id): effective_family(row.kind, row.family) for row in rows}


def normalize_base_model_families(session: Session, config: MADConfig) -> MADConfig:
    """Set every bound node's ``base_model.family`` from its provider (task 11.9).

    The family is a property of the provider, not a free parameter, so on save/
    import/snapshot each participant bound to an existing provider gets that
    provider's effective family. Unbound nodes (or nodes bound to a provider id
    that no longer exists) keep their stored value. Mutates and returns
    ``config``.
    """
    families = provider_families(session)
    for node in config.participants.nodes:
        family = families.get(node.base_model.provider_id or "")
        if family is not None:
            node.base_model.family = family  # type: ignore[assignment]
    return config


def delete_provider(session: Session, provider_id: int) -> None:
    """Delete a provider, or raise ``ProviderNotFound`` if it does not exist."""
    row = _get_row(session, provider_id)
    session.delete(row)
    session.flush()


# ---------------------------------------------------------------------------
# Connectivity test (Req 8.5)
# ---------------------------------------------------------------------------


def _provider_config_for(row: Provider) -> ProviderConfig:
    """Build an engine :class:`ProviderConfig`, decrypting the key at call time.

    Decryption happens **here**, transiently, and the plaintext lives only on the
    returned config handed straight to the engine for a single ping — it is never
    persisted, logged, or returned to the client (Req 8.4). A decryption failure
    (wrong server secret, corrupted ciphertext) surfaces as a clear message so
    the test reports it rather than crashing.
    """
    api_key: Optional[str] = None
    if row.encrypted_api_key:
        try:
            api_key = decrypt_api_key(row.encrypted_api_key)
        except CredentialError as exc:
            raise ProviderError(
                f"Cannot test provider {row.name!r}: stored API key could not be "
                f"decrypted ({exc})."
            ) from exc

    return ProviderConfig(
        id=str(row.id),
        name=row.name,
        kind=row.kind,
        api_key=api_key,
        base_url=row.base_url,
        models=list(row.models or []),
    )


def build_registry(session: Session) -> ProviderRegistry:
    """Build an engine :class:`ProviderRegistry` from every stored provider.

    Each persisted :class:`Provider` is projected to a
    :class:`~mad.providers.registry.ProviderConfig` (decrypting its API key at
    call time via :func:`_provider_config_for`) and registered under its string
    id, so a debate's participant bindings (``provider_id`` = the DB row id as a
    string) resolve against the configured backends. Providers whose stored key
    cannot be decrypted are skipped rather than aborting the whole build, so one
    broken credential never blocks an otherwise-runnable execution; the missing
    provider surfaces as a clear ``ProviderError`` only if a participant
    actually binds to it at resolve time.

    This is the execution-side counterpart to :func:`test_provider`'s ad-hoc
    registry: the job runner (task 6.6) calls it to wire the engine from the
    stored providers. The default (real LiteLLM) client factory is used, so
    tests inject a registry built with a :class:`MockModelClient` factory
    instead (the runner takes a registry, not a session, for exactly this
    reason).
    """
    registry = ProviderRegistry()
    rows = session.scalars(select(Provider).order_by(Provider.id.asc())).all()
    for row in rows:
        try:
            registry.add(_provider_config_for(row))
        except ProviderError:
            # Skip providers whose key cannot be decrypted; see docstring.
            continue
    return registry


def test_provider(
    session: Session,
    provider_id: int,
    *,
    model: Optional[str] = None,
    registry_factory: Optional[RegistryFactory] = None,
) -> ProviderTestResponse:
    """Run a connectivity check for a stored provider (Req 8.5).

    Decrypts the key at call time (inside :func:`_provider_config_for`), builds
    an ad-hoc :class:`ProviderConfig`, and runs the engine registry's
    ``test_connection``, which issues a minimal call and never raises —
    connectivity failures come back as ``ok=False`` with a clear message. A
    decryption failure is likewise reported as ``ok=False`` rather than raised.
    """
    row = _get_row(session, provider_id)

    try:
        config = _provider_config_for(row)
    except ProviderError as exc:
        return ProviderTestResponse(ok=False, message=str(exc), model=model)

    registry = (registry_factory or _default_registry_factory)()
    result = registry.test_connection(config, model=model)
    return ProviderTestResponse(
        ok=result.ok,
        message=result.message,
        model=result.model,
        latency_s=result.latency_s,
    )


__all__ = [
    "ProviderNotFound",
    "InvalidProviderFamily",
    "RegistryFactory",
    "provider_families",
    "normalize_base_model_families",
    "list_providers",
    "get_provider",
    "create_provider",
    "update_provider",
    "delete_provider",
    "test_provider",
    "build_registry",
]
