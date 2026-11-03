"""Request/response DTOs for the configurations endpoints (Reqs 4, 5, 7.3).

The configurations API is the CRUD + copy + import/export + validate surface
over the saved :class:`~mad.taxonomy.schema.MADConfig` artifact. These Pydantic
models are the *transport contract* for that surface; the heavy lifting
(validation, migration, round-trip I/O, gold-case seeding) lives in the engine
(:mod:`mad.taxonomy`) and the service layer (:mod:`app.services.configs`),
keeping the layering ``routers -> services -> engine/persistence`` (Req 12.2).

Shapes:

* :class:`ConfigSummary` — a list-row view (Req 5.1): id/name/description,
  timestamps, and a compact :class:`ConfigSummaryAttributes` block (participant
  count, topology, protocol, authority, resolution, under-development flag) so
  the list view can render summary chips without downloading every artifact.
* :class:`ConfigDetail` — the full record: metadata + the embedded ``artifact``
  (the full ``MADConfig`` JSON) + the under-development selections.
* :class:`ConfigCreateRequest` / :class:`ConfigUpdateRequest` — create/update
  payloads. ``artifact`` is optional on create: when omitted the service
  pre-fills a defaults-driven artifact so a new config is immediately valid
  (Req 5.2, 7.1).
* :class:`ConfigCopyRequest` — optional new name/description for a duplicate
  (Req 5.5).
* :class:`ConfigImportRequest` — an artifact (and optional name/description) to
  validate-and-persist (Req 4.2, 4.3).
* :class:`ValidateRequest` / :class:`ValidationResponse` — validate an artifact
  and return structured, UI-friendly field errors (Req 4.2, 7.3).
* :class:`DeleteResponse` — delete acknowledgement carrying the count of
  executions that referenced the deleted config (Req 5.4 warning signal).

Artifacts are carried as free-form JSON objects (``dict[str, Any]``) at this
layer; the engine's ``MADConfig`` schema is the authoritative validator, so the
DTOs do not re-declare every taxonomy field (that would duplicate the schema
and drift). The service validates artifacts through the engine before they are
ever persisted.
"""

from __future__ import annotations

from typing import Any, Optional

from pydantic import BaseModel, Field


class ConfigSummaryAttributes(BaseModel):
    """Compact, list-friendly summary of a configuration's key attributes.

    Derived from the artifact by the service so the list view can render chips
    (Req 5.1) without each client re-deriving them from the full artifact.
    """

    participant_count: int = Field(
        description="Number of participant nodes in the configuration."
    )
    topology_structure: str = Field(
        description="Topology structure (fully_connected / grouped / structured_network)."
    )
    topology_pattern: Optional[str] = Field(
        default=None,
        description="Structured-network pattern (chain/ring/...), if any.",
    )
    protocol_mechanism: str = Field(
        description="Protocol mechanism (sequential / simultaneous / hybrid)."
    )
    authority: str = Field(description="Agreement authority.")
    resolution: str = Field(description="Agreement resolution strategy.")
    under_development: bool = Field(
        description="Whether the configuration selects any non-executable value."
    )


class ConfigSummary(BaseModel):
    """A single row in the configurations list (Req 5.1)."""

    id: int
    name: str
    description: Optional[str] = None
    schema_version: str
    created_at: Optional[str] = None
    updated_at: Optional[str] = None
    is_builtin: bool = Field(
        default=False,
        description="Whether this is a built-in gold/template config (Req 5.7).",
    )
    attributes: ConfigSummaryAttributes


class ConfigDetail(BaseModel):
    """The full configuration record: metadata + embedded artifact."""

    id: int
    name: str
    description: Optional[str] = None
    schema_version: str
    created_at: Optional[str] = None
    updated_at: Optional[str] = None
    is_builtin: bool = False
    artifact: dict[str, Any] = Field(
        description="The full MADConfig JSON artifact for this configuration."
    )
    under_development: list[str] = Field(
        default_factory=list,
        description="Keys of non-executable values selected by the artifact.",
    )


class ConfigCreateRequest(BaseModel):
    """Create a new configuration (Req 5.2).

    ``artifact`` is optional: when omitted the service pre-fills a
    defaults-driven artifact so the new config is immediately valid and
    executable (Req 7.1). ``name``/``description`` override the artifact's own
    name/description when provided.
    """

    name: Optional[str] = Field(
        default=None, description="Configuration name (defaults to the artifact's)."
    )
    description: Optional[str] = None
    artifact: Optional[dict[str, Any]] = Field(
        default=None,
        description="Full MADConfig artifact; omit to start from defaults.",
    )


class ConfigUpdateRequest(BaseModel):
    """Update an existing configuration (Req 5.3).

    All fields optional so clients can patch name/description without resending
    the artifact; a supplied ``artifact`` is validated and replaces the stored
    one.
    """

    name: Optional[str] = None
    description: Optional[str] = None
    artifact: Optional[dict[str, Any]] = None


class ConfigCopyRequest(BaseModel):
    """Duplicate a configuration into an independent new one (Req 5.5)."""

    name: Optional[str] = Field(
        default=None,
        description="Name for the copy (defaults to 'Copy of <name>').",
    )
    description: Optional[str] = None


class ConfigImportRequest(BaseModel):
    """Import a configuration artifact from JSON and persist it (Req 4.2, 4.3)."""

    artifact: dict[str, Any] = Field(
        description="Full MADConfig artifact to validate and persist."
    )
    name: Optional[str] = None
    description: Optional[str] = None


class ValidateRequest(BaseModel):
    """Validate an artifact without persisting it (Req 4.2, 7.3)."""

    artifact: dict[str, Any] = Field(
        description="Full MADConfig artifact to validate."
    )


class FieldError(BaseModel):
    """One UI-friendly field-level validation error."""

    field: str = Field(description="Dotted path to the offending field, '' for root.")
    message: str = Field(description="Actionable, human-readable error message.")


class ValidationResponse(BaseModel):
    """Structured result of validating an artifact (Req 4.2, 7.3)."""

    valid: bool
    errors: list[FieldError] = Field(default_factory=list)
    under_development: list[str] = Field(
        default_factory=list,
        description="Non-executable selections (present only when valid).",
    )


class DeleteResponse(BaseModel):
    """Acknowledgement for a delete, carrying the execution-reference warning."""

    id: int
    deleted: bool = True
    referencing_executions: int = Field(
        default=0,
        description="Executions that referenced this config (Req 5.4 warning).",
    )


__all__ = [
    "ConfigSummaryAttributes",
    "ConfigSummary",
    "ConfigDetail",
    "ConfigCreateRequest",
    "ConfigUpdateRequest",
    "ConfigCopyRequest",
    "ConfigImportRequest",
    "ValidateRequest",
    "FieldError",
    "ValidationResponse",
    "DeleteResponse",
]
