"""Request/response DTOs for the datasets endpoints (Req 10.1, 10.3).

A *dataset* is an uploaded CSV where each row becomes one debate instance
(Req 10.1). The datasets API lets a user upload a CSV, inspect its captured
metadata (columns + row count), and preview the resolved input template for a
single sample row given a column→placeholder mapping (Req 10.3).

These Pydantic models are the *transport contract* only; the business logic
(storing the file, loading it through the engine :class:`~mad.input.dataset.Dataset`,
resolving a template from a referenced configuration) lives in the service layer
(:mod:`app.services.datasets`), keeping the layering ``routers -> services ->
engine/persistence`` (Req 12.2).

Shapes:

* :class:`DatasetResponse` — the read shape for a dataset: id, name,
  original_filename, columns, row_count, timestamps. Shared by the upload and
  get endpoints.
* :class:`DatasetPreviewRequest` — the preview inputs: a column→placeholder
  mapping plus either a ``config_id`` (resolve the template from that
  configuration's ``input_spec.template``) or an inline ``template`` string, and
  an optional ``row_index`` sample selector (Req 10.3).
* :class:`DatasetPreviewResponse` — the resolved prompt for the sample row, plus
  the row index and the raw instance values used to resolve it.

The multipart upload itself (the ``file`` field) is handled by the router via
FastAPI's :class:`~fastapi.UploadFile`; ``name`` is an optional form field, so
the upload request has no dedicated Pydantic body model.
"""

from __future__ import annotations

from typing import Any, Optional

from pydantic import BaseModel, Field, model_validator


class DatasetResponse(BaseModel):
    """The dataset read shape — captured metadata, never the file bytes (Req 10.1).

    Returned by the upload (``POST /api/datasets``) and get
    (``GET /api/datasets/{id}``) endpoints. ``columns`` and ``row_count`` are
    captured at upload time by loading the CSV through the engine dataset loader.
    """

    id: int
    name: str
    original_filename: str
    columns: list[str] = Field(
        default_factory=list,
        description="Column names captured from the CSV header, in file order.",
    )
    row_count: int = Field(description="Number of data rows (excluding the header).")
    created_at: Optional[str] = None
    updated_at: Optional[str] = None


class DatasetPreviewRequest(BaseModel):
    """Inputs for resolving a sample-row input preview (Req 10.3).

    The caller supplies a ``mapping`` of dataset column name → template
    placeholder name, and specifies the template to resolve in one of two ways:

    * ``config_id`` — resolve the template from that configuration's
      ``input_spec.template`` (the common path from the run launcher); or
    * ``template`` — an inline template string (ad-hoc preview).

    Exactly one of ``config_id`` / ``template`` must be provided. ``row_index``
    selects which row to preview (defaults to the first row).
    """

    mapping: dict[str, str] = Field(
        description="Dataset column name → template placeholder name (Req 10.3).",
    )
    config_id: Optional[int] = Field(
        default=None,
        description="Configuration whose input_spec.template is resolved.",
    )
    template: Optional[str] = Field(
        default=None,
        description="Inline template to resolve (alternative to config_id).",
    )
    row_index: int = Field(
        default=0,
        ge=0,
        description="Zero-based row to preview; defaults to the first row.",
    )

    @model_validator(mode="after")
    def _one_template_source(self) -> "DatasetPreviewRequest":
        """Require exactly one of ``config_id`` / ``template`` (Req 10.3)."""
        has_config = self.config_id is not None
        has_template = self.template is not None
        if has_config and has_template:
            raise ValueError(
                "Provide either config_id or template, not both."
            )
        if not has_config and not has_template:
            raise ValueError(
                "A template source is required: provide config_id or template."
            )
        return self


class DatasetPreviewResponse(BaseModel):
    """The resolved input preview for one sample row (Req 10.3).

    ``resolved_input`` is the exact prompt that would be produced for the sample
    row; ``instance`` carries the placeholder→value pairs used to resolve it so
    the UI can show what each tag was filled with.
    """

    row_index: int
    resolved_input: str
    instance: dict[str, Any] = Field(default_factory=dict)


__all__ = [
    "DatasetResponse",
    "DatasetPreviewRequest",
    "DatasetPreviewResponse",
]
