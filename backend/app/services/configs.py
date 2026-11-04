"""Configuration service layer (Reqs 4, 5, 7.3).

This service sits between the configurations router and the two things it must
coordinate — the persistence layer (:class:`app.db.models.Configuration`) and
the engine's artifact schema / round-trip I/O (:mod:`mad.taxonomy`). It owns all
the business logic so the router stays a thin transport shell and the engine
stays web-agnostic (layering per Req 12.2: ``routers -> services ->
engine/persistence``).

Responsibilities:

* **CRUD** (Req 5.1-5.3, 5.6): list configs with derived summary attributes,
  fetch one, create (defaults pre-filled when no artifact is supplied, Req 5.2/
  7.1), update (artifact re-validated), and delete.
* **Delete warning** (Req 5.4): deleting returns the count of executions that
  referenced the config so the UI can warn; history survives via the
  ``ON DELETE SET NULL`` FK on executions.
* **Copy** (Req 5.5): duplicate into an independent config with a fresh artifact
  ``id`` so the two never share identity.
* **Import / export** (Req 4.2, 4.3): import validates the artifact through the
  engine (:func:`mad.taxonomy.version.import_config`) before persisting and
  rejects invalid artifacts with actionable errors; export returns the exact,
  schema-stamped JSON artifact (:func:`mad.taxonomy.version.export_config`).
* **Validate** (Req 4.2, 7.3): validate an artifact and return structured field
  errors without persisting; on success also report the under-development
  (non-executable) selections.
* **Seeding** (Req 5.7): idempotently seed the built-in gold/template configs
  (RE binary debate, ChatEval S1/S2/S3) on first run.

Every artifact that enters persistence is first validated through the engine, so
the database never holds a structurally invalid configuration.
"""

from __future__ import annotations

from typing import Any, Optional

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.db.models import Configuration, Execution
from app.schemas.configs import (
    ConfigDetail,
    ConfigSummary,
    ConfigSummaryAttributes,
    FieldError,
    ValidationResponse,
)
from app.services.providers import normalize_base_model_families
from mad.errors import ConfigValidationError
from mad.taxonomy import templates
from mad.taxonomy.schema import MADConfig
from mad.taxonomy.version import export_config, import_config

# The built-in gold/template configs seeded on first run (Req 5.7). Keyed by the
# engine gold-case factory key; the value is the canonical display name used
# both for seeding and for the ``is_builtin`` derivation on read.
_BUILTIN_GOLD_KEYS: tuple[str, ...] = (
    "re_binary_debate",
    "chateval_s1",
    "chateval_s2",
    "chateval_s3",
)


def _builtin_names() -> set[str]:
    """Return the set of display names used by the built-in gold configs."""
    return {templates.build_gold_case(key).name for key in _BUILTIN_GOLD_KEYS}


class ConfigNotFound(ConfigValidationError):
    """Raised when a configuration id does not exist.

    Subclasses :class:`ConfigValidationError` purely so the existing domain
    error machinery is reused; the router translates it to a 404 explicitly
    rather than relying on the default 422 mapping.
    """


# ---------------------------------------------------------------------------
# Artifact <-> model helpers
# ---------------------------------------------------------------------------


def _validate_artifact(artifact: dict[str, Any]) -> MADConfig:
    """Validate and normalise an artifact dict into a :class:`MADConfig`.

    Delegates to :func:`mad.taxonomy.version.import_config`, which migrates to
    the current schema version and validates, raising
    :class:`mad.errors.ConfigValidationError` (with a ``.fields`` payload) on
    failure.
    """
    return import_config(artifact)


def _summary_attributes(artifact: dict[str, Any]) -> ConfigSummaryAttributes:
    """Derive the list-view summary attributes from a stored artifact.

    Reads the artifact defensively (it is always a validated ``MADConfig`` dump,
    but we avoid assuming optional keys are present) and re-parses it to compute
    the under-development flag via the schema's gating hook.
    """
    participants = artifact.get("participants", {}) or {}
    interaction = artifact.get("interaction", {}) or {}
    agreement = artifact.get("agreement", {}) or {}
    topology = interaction.get("topology", {}) or {}
    protocol = interaction.get("protocol", {}) or {}

    try:
        under_dev = bool(MADConfig.model_validate(artifact).under_development_values())
    except Exception:  # pragma: no cover - stored artifacts are pre-validated
        under_dev = False

    return ConfigSummaryAttributes(
        participant_count=len(participants.get("nodes", []) or []),
        topology_structure=topology.get("structure", "fully_connected"),
        topology_pattern=topology.get("pattern"),
        protocol_mechanism=protocol.get("mechanism", "sequential"),
        authority=agreement.get("authority", "collective"),
        resolution=agreement.get("resolution", "majority_vote"),
        under_development=under_dev,
    )


def _iso(value: Any) -> Optional[str]:
    """Render a datetime column as an ISO-8601 string, or ``None``."""
    if value is None:
        return None
    try:
        return value.isoformat()
    except AttributeError:  # pragma: no cover - defensive
        return str(value)


def _to_summary(row: Configuration, builtin_names: set[str]) -> ConfigSummary:
    return ConfigSummary(
        id=row.id,
        name=row.name,
        description=row.description,
        schema_version=row.schema_version,
        created_at=_iso(row.created_at),
        updated_at=_iso(row.updated_at),
        is_builtin=row.name in builtin_names,
        attributes=_summary_attributes(row.artifact),
    )


def _to_detail(row: Configuration, builtin_names: set[str]) -> ConfigDetail:
    try:
        under_dev = MADConfig.model_validate(row.artifact).under_development_values()
    except Exception:  # pragma: no cover - stored artifacts are pre-validated
        under_dev = []
    return ConfigDetail(
        id=row.id,
        name=row.name,
        description=row.description,
        schema_version=row.schema_version,
        created_at=_iso(row.created_at),
        updated_at=_iso(row.updated_at),
        is_builtin=row.name in builtin_names,
        artifact=row.artifact,
        under_development=under_dev,
    )


def _get_row(session: Session, config_id: int) -> Configuration:
    row = session.get(Configuration, config_id)
    if row is None:
        raise ConfigNotFound(f"configuration {config_id} not found")
    return row


# ---------------------------------------------------------------------------
# CRUD
# ---------------------------------------------------------------------------


def list_configs(session: Session) -> list[ConfigSummary]:
    """Return all configurations as summary rows (Req 5.1), newest id first."""
    builtins = _builtin_names()
    rows = session.scalars(
        select(Configuration).order_by(Configuration.id.asc())
    ).all()
    return [_to_summary(row, builtins) for row in rows]


def get_config(session: Session, config_id: int) -> ConfigDetail:
    """Return the full configuration record (Req 5.3)."""
    row = _get_row(session, config_id)
    return _to_detail(row, _builtin_names())


def create_config(
    session: Session,
    *,
    name: Optional[str] = None,
    description: Optional[str] = None,
    artifact: Optional[dict[str, Any]] = None,
) -> ConfigDetail:
    """Create a configuration (Req 5.2).

    When ``artifact`` is omitted a defaults-driven :class:`MADConfig` is built so
    the new config is immediately valid (Req 7.1). A supplied artifact is
    validated through the engine. ``name``/``description`` override the
    artifact's own values when provided.
    """
    if artifact is None:
        model = MADConfig(name=name or "New configuration", description=description or "")
    else:
        model = _validate_artifact(artifact)
        if name is not None:
            model.name = name
        if description is not None:
            model.description = description

    return _persist_new(session, model)


def _persist_new(session: Session, model: MADConfig) -> ConfigDetail:
    """Persist a validated :class:`MADConfig` as a new row and return its detail.

    Bound nodes' ``base_model.family`` is first derived from their provider
    (task 11.9), so create/copy/import never persist a stale family.
    """
    normalize_base_model_families(session, model)
    dump = export_config(model)
    row = Configuration(
        name=model.name,
        description=model.description or None,
        artifact=dump,
        schema_version=model.schema_version,
    )
    session.add(row)
    session.flush()
    return _to_detail(row, _builtin_names())


def update_config(
    session: Session,
    config_id: int,
    *,
    name: Optional[str] = None,
    description: Optional[str] = None,
    artifact: Optional[dict[str, Any]] = None,
) -> ConfigDetail:
    """Update a configuration (Req 5.3). A supplied artifact is re-validated."""
    row = _get_row(session, config_id)

    if artifact is not None:
        model = normalize_base_model_families(session, _validate_artifact(artifact))
        # Keep name/description in sync: explicit args win, else the artifact's.
        model.name = name if name is not None else model.name
        if description is not None:
            model.description = description
        row.artifact = export_config(model)
        row.schema_version = model.schema_version
        row.name = model.name
        row.description = model.description or None
    else:
        if name is not None:
            row.name = name
            row.artifact = {**row.artifact, "name": name}
        if description is not None:
            row.description = description or None
            row.artifact = {**row.artifact, "description": description}

    session.flush()
    return _to_detail(row, _builtin_names())


def delete_config(session: Session, config_id: int) -> int:
    """Delete a configuration and return the number of referencing executions.

    Executions keep their immutable ``config_snapshot`` and have ``config_id``
    nulled by the FK (Req 5.4, 11.3); the returned count lets the UI warn before
    (or acknowledge after) deletion.
    """
    row = _get_row(session, config_id)
    referencing = session.scalar(
        select(func.count())
        .select_from(Execution)
        .where(Execution.config_id == config_id)
    )
    session.delete(row)
    session.flush()
    return int(referencing or 0)


def copy_config(
    session: Session,
    config_id: int,
    *,
    name: Optional[str] = None,
    description: Optional[str] = None,
) -> ConfigDetail:
    """Duplicate a configuration into an independent new one (Req 5.5).

    The copy gets a fresh artifact ``id`` so the two configurations never share
    identity, and a ``"Copy of <name>"`` default name unless overridden.
    """
    row = _get_row(session, config_id)
    model = _validate_artifact(row.artifact)

    # Fresh identity for the copy (new uuid; MADConfig assigns one on construct).
    duplicated = model.model_copy(deep=True)
    duplicated.id = MADConfig(name="_").id  # borrow a fresh uuid default
    duplicated.name = name if name is not None else f"Copy of {model.name}"
    if description is not None:
        duplicated.description = description

    return _persist_new(session, duplicated)


# ---------------------------------------------------------------------------
# Import / export / validate
# ---------------------------------------------------------------------------


def import_config_artifact(
    session: Session,
    artifact: dict[str, Any],
    *,
    name: Optional[str] = None,
    description: Optional[str] = None,
) -> ConfigDetail:
    """Validate an artifact and persist it as a new configuration (Req 4.2, 4.3).

    Invalid artifacts raise :class:`mad.errors.ConfigValidationError` (carrying a
    ``.fields`` payload) before anything is written.
    """
    model = _validate_artifact(artifact)
    # An imported artifact becomes a new, independently-owned config: give it a
    # fresh id so importing the same file twice yields two distinct configs.
    model.id = MADConfig(name="_").id
    if name is not None:
        model.name = name
    if description is not None:
        model.description = description
    return _persist_new(session, model)


def export_config_artifact(session: Session, config_id: int) -> dict[str, Any]:
    """Return the exact, schema-stamped JSON artifact for a config (Req 4.3)."""
    row = _get_row(session, config_id)
    # Re-export through the engine so the artifact is guaranteed current + stamped.
    model = _validate_artifact(row.artifact)
    return export_config(model)


def validate_artifact(artifact: dict[str, Any]) -> ValidationResponse:
    """Validate an artifact and return structured results (Req 4.2, 7.3).

    Never raises for a merely-invalid artifact: validation failures are returned
    as :class:`~app.schemas.configs.FieldError` entries with ``valid=False`` so
    the UI can surface them inline. On success, the under-development selections
    are reported so the UI can warn before execution (Req 7.5).
    """
    try:
        model = _validate_artifact(artifact)
    except ConfigValidationError as exc:
        fields = getattr(exc, "fields", None)
        if fields:
            errors = [
                FieldError(field=f.get("field", ""), message=f.get("message", ""))
                for f in fields
            ]
        else:
            errors = [FieldError(field="", message=str(exc))]
        return ValidationResponse(valid=False, errors=errors)

    return ValidationResponse(
        valid=True,
        errors=[],
        under_development=model.under_development_values(),
    )


# ---------------------------------------------------------------------------
# Seeding (Req 5.7)
# ---------------------------------------------------------------------------


def seed_builtin_configs(session: Session) -> int:
    """Idempotently seed the built-in gold/template configs (Req 5.7).

    Seeds RE binary debate and ChatEval S1/S2/S3 on first run. Seeding is keyed
    by the gold-case display name: a built-in is (re)created only when no config
    with that name already exists, so calling this repeatedly (every startup) is
    safe and never duplicates. Returns the number of configs inserted this call.
    """
    existing_names = set(
        session.scalars(select(Configuration.name)).all()
    )

    inserted = 0
    for key in _BUILTIN_GOLD_KEYS:
        model = templates.build_gold_case(key)
        if model.name in existing_names:
            continue
        dump = export_config(model)
        session.add(
            Configuration(
                name=model.name,
                description=model.description or None,
                artifact=dump,
                schema_version=model.schema_version,
            )
        )
        existing_names.add(model.name)
        inserted += 1

    if inserted:
        session.flush()
    return inserted


__all__ = [
    "ConfigNotFound",
    "list_configs",
    "get_config",
    "create_config",
    "update_config",
    "delete_config",
    "copy_config",
    "import_config_artifact",
    "export_config_artifact",
    "validate_artifact",
    "seed_builtin_configs",
]
