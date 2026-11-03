"""Configurations router (Reqs 4.2, 4.3, 5.1-5.7, 7.3).

The transport shell over the configuration lifecycle: list/create/get/update/
delete, duplicate (copy), artifact import/export, and artifact validation. It is
deliberately thin — every decision lives in :mod:`app.services.configs`, which
coordinates persistence (:class:`app.db.models.Configuration`) and the engine's
artifact schema / round-trip I/O (:mod:`mad.taxonomy`). Layering stays
``routers -> services -> engine/persistence`` (Req 12.2); this module never
imports the engine internals or touches the ORM directly beyond the injected
session.

Routes (mounted under ``/api`` by :func:`app.main.create_app`):

* ``GET  /configs``               — list with summary attributes (Req 5.1)
* ``POST /configs``               — create (defaults pre-filled) (Req 5.2)
* ``GET  /configs/{id}``          — full record (Req 5.3)
* ``PUT  /configs/{id}``          — update (Req 5.3)
* ``DELETE /configs/{id}``        — delete + execution-reference warning (Req 5.4)
* ``POST /configs/{id}/copy``     — duplicate into an independent config (Req 5.5)
* ``POST /configs/import``        — validate + persist an artifact (Req 4.2, 4.3)
* ``GET  /configs/{id}/export``   — download the JSON artifact (Req 4.3)
* ``POST /configs/validate``      — validate an artifact, structured errors (Req 4.2, 7.3)

``ConfigNotFound`` is translated to a 404 here (the service raises a
``ConfigValidationError`` subclass whose default mapping would be 422); all other
engine validation errors flow through the global structured handler.
"""

from __future__ import annotations

import json

from fastapi import APIRouter, Depends, HTTPException, Response, status
from sqlalchemy.orm import Session

from app.routers.dependencies import get_session
from app.schemas.configs import (
    ConfigCopyRequest,
    ConfigCreateRequest,
    ConfigDetail,
    ConfigImportRequest,
    ConfigSummary,
    ConfigUpdateRequest,
    DeleteResponse,
    ValidateRequest,
    ValidationResponse,
)
from app.services import configs as config_service
from app.services.configs import ConfigNotFound

router = APIRouter(prefix="/configs", tags=["configs"])


def _not_found(exc: ConfigNotFound) -> HTTPException:
    return HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc))


@router.get("", response_model=list[ConfigSummary], summary="List configurations")
def list_configs(session: Session = Depends(get_session)) -> list[ConfigSummary]:
    """List every saved configuration with its derived summary attributes."""
    return config_service.list_configs(session)


@router.post(
    "",
    response_model=ConfigDetail,
    status_code=status.HTTP_201_CREATED,
    summary="Create a configuration (defaults pre-filled)",
)
def create_config(
    body: ConfigCreateRequest,
    session: Session = Depends(get_session),
) -> ConfigDetail:
    """Create a configuration; omit ``artifact`` to start from valid defaults."""
    return config_service.create_config(
        session,
        name=body.name,
        description=body.description,
        artifact=body.artifact,
    )


@router.post(
    "/validate",
    response_model=ValidationResponse,
    summary="Validate a configuration artifact",
)
def validate_config(body: ValidateRequest) -> ValidationResponse:
    """Validate an artifact and return structured field errors (no persistence)."""
    return config_service.validate_artifact(body.artifact)


@router.post(
    "/import",
    response_model=ConfigDetail,
    status_code=status.HTTP_201_CREATED,
    summary="Import a configuration artifact from JSON",
)
def import_config(
    body: ConfigImportRequest,
    session: Session = Depends(get_session),
) -> ConfigDetail:
    """Validate an artifact and persist it as a new configuration."""
    return config_service.import_config_artifact(
        session,
        body.artifact,
        name=body.name,
        description=body.description,
    )


@router.get("/{config_id}", response_model=ConfigDetail, summary="Get a configuration")
def get_config(
    config_id: int,
    session: Session = Depends(get_session),
) -> ConfigDetail:
    """Return the full configuration record (metadata + artifact)."""
    try:
        return config_service.get_config(session, config_id)
    except ConfigNotFound as exc:
        raise _not_found(exc) from exc


@router.put("/{config_id}", response_model=ConfigDetail, summary="Update a configuration")
def update_config(
    config_id: int,
    body: ConfigUpdateRequest,
    session: Session = Depends(get_session),
) -> ConfigDetail:
    """Update name/description and/or replace the (re-validated) artifact."""
    try:
        return config_service.update_config(
            session,
            config_id,
            name=body.name,
            description=body.description,
            artifact=body.artifact,
        )
    except ConfigNotFound as exc:
        raise _not_found(exc) from exc


@router.delete(
    "/{config_id}",
    response_model=DeleteResponse,
    summary="Delete a configuration",
)
def delete_config(
    config_id: int,
    session: Session = Depends(get_session),
) -> DeleteResponse:
    """Delete a configuration; reports how many executions referenced it (Req 5.4)."""
    try:
        referencing = config_service.delete_config(session, config_id)
    except ConfigNotFound as exc:
        raise _not_found(exc) from exc
    return DeleteResponse(id=config_id, deleted=True, referencing_executions=referencing)


@router.post(
    "/{config_id}/copy",
    response_model=ConfigDetail,
    status_code=status.HTTP_201_CREATED,
    summary="Duplicate a configuration",
)
def copy_config(
    config_id: int,
    body: ConfigCopyRequest | None = None,
    session: Session = Depends(get_session),
) -> ConfigDetail:
    """Duplicate a configuration into an independent new one (Req 5.5)."""
    body = body or ConfigCopyRequest()
    try:
        return config_service.copy_config(
            session,
            config_id,
            name=body.name,
            description=body.description,
        )
    except ConfigNotFound as exc:
        raise _not_found(exc) from exc


@router.get(
    "/{config_id}/export",
    summary="Export a configuration as a JSON artifact",
    response_class=Response,
)
def export_config(
    config_id: int,
    session: Session = Depends(get_session),
) -> Response:
    """Return the configuration's JSON artifact as a downloadable file (Req 4.3)."""
    try:
        artifact = config_service.export_config_artifact(session, config_id)
    except ConfigNotFound as exc:
        raise _not_found(exc) from exc

    body = json.dumps(artifact, indent=2, ensure_ascii=False)
    filename = f"config-{config_id}.json"
    return Response(
        content=body,
        media_type="application/json",
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )


__all__ = ["router"]
