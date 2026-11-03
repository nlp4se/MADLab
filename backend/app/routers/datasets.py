"""Datasets router (Req 10.1, 10.3).

The transport shell over the dataset lifecycle: upload a CSV, read its captured
metadata, and preview the resolved input template for a sample row. It is
deliberately thin — storing the upload, loading it through the engine to capture
columns + row_count, and resolving a template (from a referenced configuration
or an inline string) all live in :mod:`app.services.datasets`, which coordinates
storage, persistence (:class:`app.db.models.Dataset`), and the engine input
layer (:mod:`mad.input.dataset`). Layering stays ``routers -> services ->
engine/persistence`` (Req 12.2); this module never touches the ORM directly
beyond the injected session.

Routes (mounted under ``/api`` by :func:`app.main.create_app`):

* ``POST /datasets``              — upload a CSV; captures columns + row_count (Req 10.1)
* ``GET  /datasets/{id}``         — get a dataset's metadata (Req 10.1)
* ``POST /datasets/{id}/preview`` — resolve the input template for a sample row (Req 10.3)

The preview uses ``POST`` because it carries a column→placeholder mapping (and a
template source) in a JSON body; the design lists it under
``GET /api/datasets/{id}/preview`` conceptually, but the body-bearing preview is
modelled as a POST so the mapping/template/row selectors are expressed cleanly.

``DatasetNotFound`` / ``ConfigNotFound`` are translated to 404 here; template and
storage errors flow through the global structured handler (422 / 500).
"""

from __future__ import annotations

from typing import Optional

from fastapi import APIRouter, Depends, File, Form, HTTPException, UploadFile, status
from sqlalchemy.orm import Session

from app.config import Settings, get_settings
from app.routers.dependencies import get_session
from app.schemas.datasets import (
    DatasetPreviewRequest,
    DatasetPreviewResponse,
    DatasetResponse,
)
from app.services import datasets as dataset_service
from app.services.configs import ConfigNotFound
from app.services.datasets import DatasetNotFound

router = APIRouter(prefix="/datasets", tags=["datasets"])


def _not_found(message: str) -> HTTPException:
    return HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=message)


@router.post(
    "",
    response_model=DatasetResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Upload a CSV dataset",
)
async def upload_dataset(
    file: UploadFile = File(..., description="CSV file; one row per instance."),
    name: Optional[str] = Form(
        default=None, description="Optional display name; defaults to the file stem."
    ),
    session: Session = Depends(get_session),
    settings: Settings = Depends(get_settings),
) -> DatasetResponse:
    """Upload a CSV dataset (Req 10.1).

    The file is stored under the configured storage directory, loaded through
    the engine to capture its columns and row count, and persisted as dataset
    metadata.
    """
    content = await file.read()
    return dataset_service.create_dataset(
        session,
        content=content,
        original_filename=file.filename or "dataset.csv",
        storage_dir=settings.dataset_storage_dir,
        name=name,
    )


@router.get(
    "/{dataset_id}",
    response_model=DatasetResponse,
    summary="Get a dataset",
)
def get_dataset(
    dataset_id: int,
    session: Session = Depends(get_session),
) -> DatasetResponse:
    """Return a single dataset's captured metadata (Req 10.1)."""
    try:
        return dataset_service.get_dataset(session, dataset_id)
    except DatasetNotFound as exc:
        raise _not_found(str(exc)) from exc


@router.post(
    "/{dataset_id}/preview",
    response_model=DatasetPreviewResponse,
    summary="Preview the resolved input for a sample row",
)
def preview_dataset(
    dataset_id: int,
    body: DatasetPreviewRequest,
    session: Session = Depends(get_session),
) -> DatasetPreviewResponse:
    """Resolve the input template for a sample row given a mapping (Req 10.3)."""
    try:
        return dataset_service.preview_dataset(
            session,
            dataset_id,
            mapping=body.mapping,
            config_id=body.config_id,
            template=body.template,
            row_index=body.row_index,
        )
    except (DatasetNotFound, ConfigNotFound) as exc:
        raise _not_found(str(exc)) from exc


__all__ = ["router"]
