"""Providers router (Req 8).

The transport shell over the provider lifecycle: list/create/get/update/delete
plus a connectivity test. It is deliberately thin — every decision (encryption
on save, the write-only key semantics, decryption-at-call-time, registry wiring)
lives in :mod:`app.services.providers`, which coordinates persistence
(:class:`app.db.models.Provider`), security (:mod:`app.security.crypto`), and the
engine provider registry (:mod:`mad.providers.registry`). Layering stays
``routers -> services -> engine/persistence`` (Req 12.2); this module never
imports the engine internals or touches the ORM directly beyond the injected
session.

Routes (mounted under ``/api`` by :func:`app.main.create_app`):

* ``GET    /providers``            — list providers (metadata + has_key) (Req 8.1)
* ``POST   /providers``            — create; write-only api_key encrypted on save (Req 8.1-8.4)
* ``GET    /providers/{id}``       — get one provider (Req 8.1)
* ``PUT    /providers/{id}``       — update; api_key is write-only (Req 8.1, 8.3, 8.4)
* ``DELETE /providers/{id}``       — delete (Req 8.1)
* ``POST   /providers/{id}/test``  — connectivity check (Req 8.5)

Every response is a :class:`~app.schemas.providers.ProviderResponse` (or test/
delete acknowledgement): the API returns provider metadata and a ``has_key``
boolean only, never the key plaintext or ciphertext (Req 8.4).

``ProviderNotFound`` is translated to a 404 here (the service raises a
``ProviderError`` subclass whose default mapping would be 502); all other
provider errors flow through the global structured handler.
"""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from app.routers.dependencies import get_session
from app.schemas.providers import (
    ProviderCreateRequest,
    ProviderDeleteResponse,
    ProviderResponse,
    ProviderTestRequest,
    ProviderTestResponse,
    ProviderUpdateRequest,
)
from app.services import providers as provider_service
from app.services.providers import ProviderNotFound

router = APIRouter(prefix="/providers", tags=["providers"])


def _not_found(exc: ProviderNotFound) -> HTTPException:
    return HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc))


@router.get("", response_model=list[ProviderResponse], summary="List providers")
def list_providers(session: Session = Depends(get_session)) -> list[ProviderResponse]:
    """List every configured provider (metadata + ``has_key`` only, Req 8.4)."""
    return provider_service.list_providers(session)


@router.post(
    "",
    response_model=ProviderResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Create a provider",
)
def create_provider(
    body: ProviderCreateRequest,
    session: Session = Depends(get_session),
) -> ProviderResponse:
    """Create a provider; the write-only ``api_key`` is encrypted on save (Req 8.4)."""
    return provider_service.create_provider(session, body)


@router.get(
    "/{provider_id}",
    response_model=ProviderResponse,
    summary="Get a provider",
)
def get_provider(
    provider_id: int,
    session: Session = Depends(get_session),
) -> ProviderResponse:
    """Return a single provider (metadata + ``has_key``)."""
    try:
        return provider_service.get_provider(session, provider_id)
    except ProviderNotFound as exc:
        raise _not_found(exc) from exc


@router.put(
    "/{provider_id}",
    response_model=ProviderResponse,
    summary="Update a provider",
)
def update_provider(
    provider_id: int,
    body: ProviderUpdateRequest,
    session: Session = Depends(get_session),
) -> ProviderResponse:
    """Update a provider; ``api_key`` is write-only (omit to keep it, Req 8.4)."""
    try:
        return provider_service.update_provider(session, provider_id, body)
    except ProviderNotFound as exc:
        raise _not_found(exc) from exc


@router.delete(
    "/{provider_id}",
    response_model=ProviderDeleteResponse,
    summary="Delete a provider",
)
def delete_provider(
    provider_id: int,
    session: Session = Depends(get_session),
) -> ProviderDeleteResponse:
    """Delete a provider."""
    try:
        provider_service.delete_provider(session, provider_id)
    except ProviderNotFound as exc:
        raise _not_found(exc) from exc
    return ProviderDeleteResponse(id=provider_id, deleted=True)


@router.post(
    "/{provider_id}/test",
    response_model=ProviderTestResponse,
    summary="Test provider connectivity",
)
def test_provider(
    provider_id: int,
    body: ProviderTestRequest | None = None,
    session: Session = Depends(get_session),
) -> ProviderTestResponse:
    """Run a connectivity check and report success or a clear error (Req 8.5)."""
    body = body or ProviderTestRequest()
    try:
        return provider_service.test_provider(session, provider_id, model=body.model)
    except ProviderNotFound as exc:
        raise _not_found(exc) from exc


__all__ = ["router"]
