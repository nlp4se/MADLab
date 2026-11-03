"""Dataset service layer (Req 10.1, 10.3).

This service sits between the datasets router and the three things it must
coordinate:

* **storage** — the uploaded CSV bytes are written to a configurable storage
  directory (``Settings.dataset_storage_dir``); the stored path is persisted so
  a preview can re-load the file later;
* **persistence** — the :class:`app.db.models.Dataset` ORM row (name,
  original_filename, stored_path, columns, row_count);
* **engine** — the headless :class:`mad.input.dataset.Dataset` loader, which
  captures ``columns``/``row_count`` at upload time and resolves a template for
  a sample row at preview time (:meth:`~mad.input.dataset.Dataset.preview`),
  plus the configuration artifact's ``input_spec.template`` when a preview names
  a ``config_id``.

It owns all the business logic so the router stays a thin transport shell and
the engine/persistence layers stay web-agnostic (layering per Req 12.2:
``routers -> services -> engine/persistence``).

Responsibilities:

* **Upload** (Req 10.1): write the CSV to storage under a collision-free name,
  load it through the engine to capture columns + row_count, and persist the
  metadata row.
* **Get** (Req 10.1): return a dataset's captured metadata.
* **Preview** (Req 10.3): re-load the stored CSV, resolve the template (from a
  referenced configuration's ``input_spec.template`` or an inline template) for
  a sample row using a column→placeholder mapping, and return the resolved
  prompt plus the instance values used.
"""

from __future__ import annotations

import uuid
from pathlib import Path
from typing import Any, Optional

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.db.models import Configuration, Dataset as DatasetRow
from app.schemas.datasets import DatasetPreviewResponse, DatasetResponse
from app.services.configs import ConfigNotFound
from mad.errors import MADError, TemplateError
from mad.input.dataset import Dataset as EngineDataset


class DatasetNotFound(MADError):
    """Raised when a dataset id does not exist.

    Subclasses :class:`~mad.errors.MADError` so it flows through the domain
    error machinery; the router translates it to a 404 explicitly rather than
    relying on the default 500 mapping.
    """


class DatasetStorageError(MADError):
    """Raised when an uploaded dataset cannot be stored or loaded (Req 10.1)."""


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


def _to_response(row: DatasetRow) -> DatasetResponse:
    """Project a :class:`Dataset` row to the response shape."""
    return DatasetResponse(
        id=row.id,
        name=row.name,
        original_filename=row.original_filename,
        columns=list(row.columns or []),
        row_count=row.row_count,
        created_at=_iso(row.created_at),
        updated_at=_iso(row.updated_at),
    )


def _get_row(session: Session, dataset_id: int) -> DatasetRow:
    row = session.get(DatasetRow, dataset_id)
    if row is None:
        raise DatasetNotFound(f"dataset {dataset_id} not found")
    return row


def _safe_stem(filename: str) -> str:
    """Derive a filesystem-safe stem from an uploaded filename.

    Keeps alphanumerics, dashes, dots and underscores; collapses everything else
    to a single underscore so a crafted upload name cannot escape the storage
    directory or produce an awkward path. Empty results fall back to "dataset".
    """
    stem = Path(filename or "").name  # strip any directory components
    cleaned = "".join(c if (c.isalnum() or c in "-._") else "_" for c in stem)
    cleaned = cleaned.strip("._") or "dataset"
    return cleaned


# ---------------------------------------------------------------------------
# Upload (Req 10.1)
# ---------------------------------------------------------------------------


def create_dataset(
    session: Session,
    *,
    content: bytes,
    original_filename: str,
    storage_dir: Path,
    name: Optional[str] = None,
) -> DatasetResponse:
    """Store an uploaded CSV and persist its captured metadata (Req 10.1).

    The bytes are written to ``storage_dir`` under a collision-free name, then
    loaded through the engine :class:`~mad.input.dataset.Dataset` to capture the
    column names and row count. The metadata row (name, original filename,
    stored path, columns, row_count) is persisted and returned.

    Args:
        session: Active DB session.
        content: Raw uploaded file bytes.
        original_filename: The client-provided filename (used for display and to
            derive the stored name and the default dataset name).
        storage_dir: Directory to write the stored CSV into (created if absent).
        name: Optional display name; defaults to the uploaded file's stem.

    Raises:
        DatasetStorageError: When the file cannot be written, is empty, or cannot
            be parsed as CSV.
    """
    storage_dir.mkdir(parents=True, exist_ok=True)

    stem = _safe_stem(original_filename)
    # A short uuid prefix guarantees uniqueness so two uploads of the same file
    # name never clobber each other on disk.
    stored_name = f"{uuid.uuid4().hex[:12]}_{stem}"
    if not stored_name.lower().endswith(".csv"):
        stored_name = f"{stored_name}.csv"
    stored_path = storage_dir / stored_name

    try:
        stored_path.write_bytes(content)
    except OSError as exc:
        raise DatasetStorageError(
            f"Could not store uploaded dataset {original_filename!r}: {exc}"
        ) from exc

    # Load through the engine to capture columns + row_count. If parsing fails,
    # remove the just-written file so storage does not accumulate garbage.
    try:
        engine_dataset = EngineDataset.from_csv(stored_path)
        columns = engine_dataset.columns
        row_count = engine_dataset.row_count
    except (ValueError, FileNotFoundError) as exc:
        stored_path.unlink(missing_ok=True)
        raise DatasetStorageError(
            f"Uploaded dataset {original_filename!r} could not be loaded: {exc}"
        ) from exc

    display_name = name or Path(original_filename or stored_name).stem or stored_name

    row = DatasetRow(
        name=display_name,
        original_filename=original_filename or stored_name,
        stored_path=str(stored_path),
        columns=columns,
        row_count=row_count,
    )
    session.add(row)
    session.flush()
    return _to_response(row)


# ---------------------------------------------------------------------------
# Get (Req 10.1)
# ---------------------------------------------------------------------------


def get_dataset(session: Session, dataset_id: int) -> DatasetResponse:
    """Return a single dataset's captured metadata, or raise ``DatasetNotFound``."""
    return _to_response(_get_row(session, dataset_id))


# ---------------------------------------------------------------------------
# Preview (Req 10.3)
# ---------------------------------------------------------------------------


def _resolve_template_source(
    session: Session,
    *,
    config_id: Optional[int],
    template: Optional[str],
) -> str:
    """Return the template string to resolve for a preview (Req 10.3).

    When ``config_id`` is given, the template comes from that configuration's
    ``input_spec.template``; otherwise the inline ``template`` is used. The
    schema already guarantees exactly one source is present.
    """
    if config_id is not None:
        row = session.get(Configuration, config_id)
        if row is None:
            raise ConfigNotFound(f"configuration {config_id} not found")
        artifact = row.artifact or {}
        input_spec = artifact.get("input_spec", {}) or {}
        return str(input_spec.get("template", "") or "")
    return template or ""


def preview_dataset(
    session: Session,
    dataset_id: int,
    *,
    mapping: dict[str, str],
    config_id: Optional[int] = None,
    template: Optional[str] = None,
    row_index: int = 0,
) -> DatasetPreviewResponse:
    """Resolve the input template for a sample row of a dataset (Req 10.3).

    Re-loads the stored CSV through the engine, resolves the template (from the
    referenced configuration's ``input_spec.template`` or the inline template)
    for the ``row_index`` sample row using the column→placeholder ``mapping``,
    and returns the resolved prompt plus the instance values used.

    Raises:
        DatasetNotFound: When the dataset id does not exist.
        ConfigNotFound: When ``config_id`` is given but does not exist.
        DatasetStorageError: When the stored CSV can no longer be loaded.
        TemplateError: When the mapping does not cover the template's
            placeholders, references a missing column, or the row index is out
            of range.
    """
    row = _get_row(session, dataset_id)
    resolved_template = _resolve_template_source(
        session, config_id=config_id, template=template
    )

    try:
        engine_dataset = EngineDataset.from_csv(row.stored_path)
    except (ValueError, FileNotFoundError) as exc:
        raise DatasetStorageError(
            f"Stored dataset for id {dataset_id} could not be loaded: {exc}"
        ) from exc

    try:
        resolved_input = engine_dataset.preview(
            resolved_template, mapping, index=row_index
        )
        instance = engine_dataset.instance(row_index, mapping)
    except IndexError as exc:
        # Normalise an out-of-range row index into a domain TemplateError so the
        # web layer maps it to a 422 rather than a 500.
        raise TemplateError(
            f"Row index {row_index} out of range for dataset with "
            f"{engine_dataset.row_count} row(s)."
        ) from exc

    return DatasetPreviewResponse(
        row_index=row_index,
        resolved_input=resolved_input,
        instance={k: _jsonable(v) for k, v in instance.items()},
    )


def _jsonable(value: Any) -> Any:
    """Coerce a pandas/NumPy cell value into a JSON-serializable scalar."""
    # pandas scalars (numpy types) expose ``item()`` to unwrap to a Python scalar.
    item = getattr(value, "item", None)
    if callable(item):
        try:
            return item()
        except (ValueError, TypeError):  # pragma: no cover - defensive
            return str(value)
    return value


__all__ = [
    "DatasetNotFound",
    "DatasetStorageError",
    "create_dataset",
    "get_dataset",
    "preview_dataset",
]
