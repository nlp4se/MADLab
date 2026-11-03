"""Artifact schema versioning + round-trip I/O for the MAD Configuration Artifact.

This module owns three concerns, all centred on the single versioned JSON
document defined by :class:`mad.taxonomy.schema.MADConfig`:

1. **Version source of truth.** The authoritative schema version is
   :data:`CURRENT_SCHEMA_VERSION`. To avoid a circular import, ``schema.py``
   keeps defining its own ``SCHEMA_VERSION`` module constant (it is imported by
   the Pydantic models as a field default) and this module imports *from*
   schema rather than the other way around. The two constants are asserted
   equal at import time, so they can never silently drift: there is one logical
   source of truth, enforced mechanically. Dependency direction is strictly
   ``version.py -> schema.py``.

2. **Forward migration.** A small registry maps a source version to a one-step
   upgrade function. :func:`migrate` applies registered steps in sequence until
   an artifact dict reaches :data:`CURRENT_SCHEMA_VERSION`. Today there is only
   version ``"1.0"`` (the terminal/current version, so it needs no migration),
   but the mechanism is in place: shipping a ``"1.0" -> "1.1"`` migration later
   is a single :func:`register_migration` call. Unknown or newer-than-supported
   versions raise :class:`mad.errors.ConfigValidationError`.

3. **Export / import / file I/O.** Serialize a :class:`MADConfig` to a
   JSON-ready dict or string, and import a dict or JSON string back into a
   validated :class:`MADConfig` (migrating first, then validating). Invalid
   artifacts are rejected with UI-friendly field errors.

The module stays importable without any web dependency: it uses only stdlib
(``json``, ``os``/``pathlib``), ``pydantic``, and the dependency-light
``mad.taxonomy.schema`` / ``mad.errors`` modules.
"""

from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Callable, Union

from pydantic import ValidationError

from mad.errors import ConfigValidationError
from mad.taxonomy import schema
from mad.taxonomy.schema import MADConfig, validation_error_to_fields

# ---------------------------------------------------------------------------
# Single source of truth for the schema version.
#
# ``schema.py`` defines ``SCHEMA_VERSION`` because its Pydantic models need the
# value as a field default, and making schema.py import from version.py would
# create a cycle (version.py already imports schema.py). We therefore let
# version.py re-export schema's constant as the authoritative name and assert
# the two agree, giving one logical source of truth with no circular import.
# ---------------------------------------------------------------------------
CURRENT_SCHEMA_VERSION: str = schema.SCHEMA_VERSION

assert CURRENT_SCHEMA_VERSION == schema.SCHEMA_VERSION, (
    "schema version drift: version.CURRENT_SCHEMA_VERSION "
    f"({CURRENT_SCHEMA_VERSION!r}) != schema.SCHEMA_VERSION "
    f"({schema.SCHEMA_VERSION!r})"
)


# ---------------------------------------------------------------------------
# Migration registry
#
# A migration is a function ``dict -> dict`` that upgrades an artifact *one
# step* forward. The registry is keyed by the source version it applies to, so
# ``_MIGRATIONS["1.0"]`` upgrades a 1.0 artifact toward the next version. Each
# migration MUST set the resulting dict's ``schema_version`` to its target so
# that :func:`migrate` can make progress and terminate.
# ---------------------------------------------------------------------------

Migration = Callable[[dict], dict]

_MIGRATIONS: dict[str, Migration] = {}


def register_migration(from_version: str, func: Migration) -> None:
    """Register a one-step forward migration from ``from_version``.

    Adding support for a future schema (e.g. ``"1.1"``) is a single call::

        register_migration("1.0", _migrate_1_0_to_1_1)

    where ``_migrate_1_0_to_1_1`` returns a dict whose ``schema_version`` is
    ``"1.1"``. Registering two migrations for the same source version is a
    programming error and raises :class:`ValueError`.
    """
    if from_version in _MIGRATIONS:
        raise ValueError(
            f"a migration from version {from_version!r} is already registered"
        )
    _MIGRATIONS[from_version] = func


# The set of versions this module understands: the current (terminal) version
# plus every version that has a registered forward migration.
def _known_versions() -> set[str]:
    return {CURRENT_SCHEMA_VERSION, *_MIGRATIONS.keys()}


def migrate(data: dict) -> dict:
    """Apply registered migrations until ``data`` is at the current version.

    Accepts an artifact dict, reads its ``schema_version`` (defaulting to the
    current version when absent — a bare config authored in-process is treated
    as current), and applies one-step migrations in sequence until the dict's
    version equals :data:`CURRENT_SCHEMA_VERSION`.

    Returns a (possibly new) dict stamped with the current version. The input
    dict is not mutated. Raises :class:`mad.errors.ConfigValidationError` if the
    artifact declares a version that is unknown or newer than supported, or if
    the migration chain cannot reach the current version.
    """
    if not isinstance(data, dict):
        raise ConfigValidationError(
            "cannot migrate artifact: expected a mapping/dict, got "
            f"{type(data).__name__}"
        )

    current = dict(data)  # shallow copy; migrations return fresh dicts anyway
    version = current.get("schema_version", CURRENT_SCHEMA_VERSION)

    if version == CURRENT_SCHEMA_VERSION:
        # Already current: ensure the stamp is present and exact (no-op path).
        current["schema_version"] = CURRENT_SCHEMA_VERSION
        return current

    seen: list[str] = []
    while version != CURRENT_SCHEMA_VERSION:
        if version in seen:
            raise ConfigValidationError(
                f"migration cycle detected while upgrading from {seen[0]!r}: "
                f"revisited version {version!r}"
            )
        seen.append(version)

        step = _MIGRATIONS.get(version)
        if step is None:
            known = ", ".join(sorted(_known_versions()))
            raise ConfigValidationError(
                f"unsupported schema_version {version!r}: no migration path to "
                f"{CURRENT_SCHEMA_VERSION!r}. Known versions: [{known}]. The "
                f"artifact may have been produced by a newer version of the "
                f"software."
            )
        current = step(current)
        version = current.get("schema_version")

    current["schema_version"] = CURRENT_SCHEMA_VERSION
    return current


# ---------------------------------------------------------------------------
# Export
# ---------------------------------------------------------------------------


def export_config(config: MADConfig) -> dict:
    """Serialize a :class:`MADConfig` to a JSON-ready dict.

    Uses ``model_dump(mode="json")`` so every value is a JSON-native type. The
    result is stamped with :data:`CURRENT_SCHEMA_VERSION` to guarantee the
    exported artifact records the current schema version (Req 4.5).
    """
    data = config.model_dump(mode="json")
    data["schema_version"] = CURRENT_SCHEMA_VERSION
    return data


def export_config_json(config: MADConfig, *, indent: int | None = 2) -> str:
    """Serialize a :class:`MADConfig` to a JSON string.

    ``indent`` is forwarded to :func:`json.dumps` (default 2 for human-readable
    files; pass ``None`` for the most compact output). Keys are preserved in
    model order; ``ensure_ascii`` is disabled so unicode content stays readable.
    """
    return json.dumps(export_config(config), indent=indent, ensure_ascii=False)


# ---------------------------------------------------------------------------
# Import
# ---------------------------------------------------------------------------


def import_config(data: Union[dict, str]) -> MADConfig:
    """Import a configuration artifact into a validated :class:`MADConfig`.

    Accepts either a dict or a JSON string. The flow is:

    1. Parse JSON if given a string (malformed JSON raises
       :class:`ConfigValidationError` with the parse error).
    2. Run :func:`migrate` to bring the artifact to the current version
       (unknown/newer versions raise :class:`ConfigValidationError`).
    3. Validate via :meth:`MADConfig.model_validate`; on failure raise
       :class:`ConfigValidationError` whose ``.fields`` payload carries the
       UI-friendly field errors from :func:`validation_error_to_fields`.
    """
    if isinstance(data, str):
        try:
            parsed = json.loads(data)
        except json.JSONDecodeError as exc:
            raise ConfigValidationError(
                f"could not import configuration: malformed JSON ({exc})"
            ) from exc
        if not isinstance(parsed, dict):
            raise ConfigValidationError(
                "could not import configuration: top-level JSON value must be an "
                f"object, got {type(parsed).__name__}"
            )
        payload = parsed
    elif isinstance(data, dict):
        payload = data
    else:
        raise ConfigValidationError(
            "could not import configuration: expected a dict or JSON string, got "
            f"{type(data).__name__}"
        )

    migrated = migrate(payload)

    try:
        return MADConfig.model_validate(migrated)
    except ValidationError as exc:
        fields = validation_error_to_fields(exc)
        summary = "; ".join(
            f"{f['field'] or '<root>'}: {f['message']}" for f in fields
        )
        error = ConfigValidationError(
            f"configuration artifact failed validation: {summary}"
        )
        # Attach the structured, UI-friendly field errors so the API layer can
        # surface them without re-parsing the message.
        error.fields = fields  # type: ignore[attr-defined]
        raise error from exc


# ---------------------------------------------------------------------------
# File I/O convenience wrappers (engine-level; acceptable here per design note)
# ---------------------------------------------------------------------------


def save_config(config: MADConfig, path: Union[str, os.PathLike[str]]) -> Path:
    """Write ``config`` to ``path`` as a pretty-printed ``.json`` file.

    Parent directories are created if needed. Returns the resolved
    :class:`~pathlib.Path` that was written.
    """
    p = Path(path)
    if p.parent and not p.parent.exists():
        p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(export_config_json(config), encoding="utf-8")
    return p


def load_config(path: Union[str, os.PathLike[str]]) -> MADConfig:
    """Read a configuration artifact from ``path`` and return a :class:`MADConfig`.

    Delegates to :func:`import_config`, so the same migration + validation rules
    apply. A missing file raises :class:`FileNotFoundError`; a malformed or
    invalid artifact raises :class:`ConfigValidationError`.
    """
    text = Path(path).read_text(encoding="utf-8")
    return import_config(text)


__all__ = [
    "CURRENT_SCHEMA_VERSION",
    "Migration",
    "register_migration",
    "migrate",
    "export_config",
    "export_config_json",
    "import_config",
    "save_config",
    "load_config",
]
