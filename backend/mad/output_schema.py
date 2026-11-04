"""One normalizer for the agreement ``output_schema`` (task 11.13).

Users paste the decision schema in several shapes:

* a bare JSON Schema: ``{"type": "object", "properties": {...}}``;
* the OpenAI ``json_schema`` envelope: ``{"name", "description", "schema": {...},
  "strict"}`` (``data/prompts/coordinator/requirements-schema-binary.json``);
* the whole OpenAI ``response_format``: ``{"type": "json_schema",
  "json_schema": {<envelope>}}``.

Every consumer — the provider request (:mod:`mad.providers`), the judge-reply
validation (:mod:`mad.engine.agreement`), and label extraction
(:mod:`mad.evaluation.transcript_adapter`) — goes through
:func:`normalize_output_schema` so they all see the same JSON schema proper.
Before this, the envelope was validated as if it were the schema (it has no
``type``/``properties``, so any object passed) and was wrapped a second time in
the provider request (so no provider constrained the reply).

The frontend mirrors these rules in ``frontend/src/features/executions/
decisionDisplay.ts`` (``innerSchema``) and the designer's strictness check.

This module is dependency-free and lives at the package root so both the
providers and the engine can import it without an import cycle.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Any, Optional

__all__ = [
    "DEFAULT_SCHEMA_NAME",
    "NormalizedOutputSchema",
    "normalize_output_schema",
    "unwrap_output_schema",
    "is_strict_compatible",
    "declared_properties",
]

# Name used when the schema carries none (OpenAI requires a name).
DEFAULT_SCHEMA_NAME = "mad_structured_output"

# OpenAI: ``^[a-zA-Z0-9_-]{1,64}$``.
_NAME_INVALID = re.compile(r"[^a-zA-Z0-9_-]")
_NAME_MAX = 64


@dataclass(frozen=True)
class NormalizedOutputSchema:
    """The agreement ``output_schema`` reduced to its parts.

    Attributes:
        schema: The JSON schema proper (the envelope's ``schema``, or the input
            itself when it is a bare schema).
        name: A provider-safe schema name (the envelope's ``name`` sanitised,
            else :data:`DEFAULT_SCHEMA_NAME`).
        description: The envelope's ``description``, if any.
        strict: The envelope's explicit ``strict`` flag, or ``None``.
        enveloped: Whether the input was wrapped.
    """

    schema: dict[str, Any]
    name: str = DEFAULT_SCHEMA_NAME
    description: Optional[str] = None
    strict: Optional[bool] = None
    enveloped: bool = False

    @property
    def strict_compatible(self) -> bool:
        """Whether :attr:`schema` satisfies strict structured-output rules."""
        return is_strict_compatible(self.schema)

    @property
    def request_strict(self) -> bool:
        """Whether to ask the provider for strict mode.

        Only when the schema satisfies the strict rules (OpenAI rejects a
        strict request otherwise) and the envelope did not opt out.
        """
        return self.strict is not False and self.strict_compatible


def _is_envelope(value: dict[str, Any]) -> bool:
    """A ``{name?, description?, schema: {...}}`` wrapper, not a schema itself."""
    return (
        isinstance(value.get("schema"), dict)
        and "properties" not in value
        and "type" not in value
    )


def _safe_name(value: Any) -> str:
    if not isinstance(value, str):
        return DEFAULT_SCHEMA_NAME
    name = _NAME_INVALID.sub("_", value.strip())[:_NAME_MAX]
    return name or DEFAULT_SCHEMA_NAME


def normalize_output_schema(raw: Any) -> Optional[NormalizedOutputSchema]:
    """Normalise an agreement ``output_schema`` (bare, envelope, or response_format).

    Returns ``None`` when ``raw`` is not a JSON object (no schema).
    """
    if not isinstance(raw, dict):
        return None

    value = raw
    # The whole OpenAI response_format: {"type": "json_schema", "json_schema": {...}}.
    if value.get("type") == "json_schema" and isinstance(value.get("json_schema"), dict):
        value = value["json_schema"]

    if not _is_envelope(value):
        if value is raw:
            return NormalizedOutputSchema(schema=raw)
        # response_format whose json_schema is itself a bare schema.
        return NormalizedOutputSchema(schema=value, enveloped=True)

    description = value.get("description")
    strict = value.get("strict")
    return NormalizedOutputSchema(
        schema=value["schema"],
        name=_safe_name(value.get("name")),
        description=description if isinstance(description, str) and description else None,
        strict=strict if isinstance(strict, bool) else None,
        enveloped=True,
    )


def unwrap_output_schema(raw: Any) -> Optional[dict[str, Any]]:
    """The JSON schema proper of ``raw`` (see :func:`normalize_output_schema`)."""
    normalized = normalize_output_schema(raw)
    return normalized.schema if normalized is not None else None


def declared_properties(schema: Any) -> Optional[dict[str, Any]]:
    """The ``properties`` map of an object schema, or ``None``."""
    if not isinstance(schema, dict):
        return None
    props = schema.get("properties")
    return props if isinstance(props, dict) else None


def _is_object_schema(schema: dict[str, Any]) -> bool:
    kind = schema.get("type")
    if kind == "object" or (isinstance(kind, list) and "object" in kind):
        return True
    return "properties" in schema


def _subschemas(schema: dict[str, Any]) -> list[Any]:
    """Nested schemas that strict mode also constrains."""
    nested: list[Any] = []
    props = declared_properties(schema)
    if props:
        nested.extend(props.values())
    items = schema.get("items")
    if isinstance(items, dict):
        nested.append(items)
    elif isinstance(items, list):
        nested.extend(items)
    for key in ("anyOf", "oneOf", "allOf"):
        if isinstance(schema.get(key), list):
            nested.extend(schema[key])
    for key in ("$defs", "definitions"):
        if isinstance(schema.get(key), dict):
            nested.extend(schema[key].values())
    return nested


def _strict_ok(schema: Any) -> bool:
    if not isinstance(schema, dict):
        return True
    if _is_object_schema(schema):
        if schema.get("additionalProperties") is not False:
            return False
        props = declared_properties(schema) or {}
        required = schema.get("required")
        if not isinstance(required, list) or set(required) != set(props):
            return False
    return all(_strict_ok(sub) for sub in _subschemas(schema))


def is_strict_compatible(schema: Any) -> bool:
    """Whether ``schema`` meets strict structured-output rules.

    The root is an object schema, and every object schema in it sets
    ``additionalProperties: false`` and lists all its properties in
    ``required`` (OpenAI strict mode; Anthropic structured outputs also expect
    closed objects).
    """
    if not isinstance(schema, dict) or not _is_object_schema(schema):
        return False
    return _strict_ok(schema)
