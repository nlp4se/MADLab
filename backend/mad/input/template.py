"""Input template resolution (task 4.1).

An *input template* is a structured text string with ``{{placeholder}}`` tags
that map instance fields (ad-hoc form values or mapped CSV columns) into the
debate's initial prompt (Req 10.2). This module is the richer, standalone
resolver that the engine's orchestrator and the web/CLI layers build on:

* :func:`extract_placeholders` lists the tags referenced by a template.
* :func:`resolve_template` substitutes tag values from an instance dict,
  reporting missing placeholders as a :class:`~mad.errors.TemplateError`.
* :func:`validate_template` checks a template against a set of available
  fields *before* a run so a misconfiguration surfaces with an actionable
  message rather than at execution time.

The module has no web/framework dependency: it imports only the standard
library and the domain error type, keeping it usable headlessly.
"""

from __future__ import annotations

import re
from typing import Any, Iterable, Mapping

from mad.errors import TemplateError

__all__ = [
    "PLACEHOLDER_PATTERN",
    "extract_placeholders",
    "resolve_template",
    "validate_template",
]

# A placeholder is ``{{name}}`` where ``name`` is a non-empty run of word
# characters, dots, hyphens, or spaces (so ad-hoc field keys and CSV column
# headers both map cleanly). Surrounding whitespace inside the braces is
# ignored: ``{{ requirement }}`` and ``{{requirement}}`` are the same tag.
PLACEHOLDER_PATTERN: re.Pattern[str] = re.compile(r"\{\{\s*([\w.\- ]+?)\s*\}\}")


def extract_placeholders(template: str) -> list[str]:
    """Return the distinct placeholder names referenced by ``template``.

    Names are returned in first-appearance order with duplicates removed so a
    UI can list each required field exactly once.

    Args:
        template: The raw template text (may be empty).

    Returns:
        The ordered, de-duplicated list of placeholder names. An empty or
        tag-free template yields an empty list.
    """
    if not template:
        return []
    seen: dict[str, None] = {}
    for match in PLACEHOLDER_PATTERN.finditer(template):
        seen.setdefault(match.group(1).strip(), None)
    return list(seen)


def resolve_template(
    template: str,
    instance: Mapping[str, Any],
    *,
    strict: bool = True,
) -> str:
    """Resolve ``{{placeholder}}`` tags in ``template`` against ``instance``.

    Each ``{{name}}`` tag is replaced with ``str(instance[name])``. Field keys
    are matched exactly; whitespace inside the braces is ignored.

    Args:
        template: The template text. An empty template resolves to ``""``.
        instance: A mapping of field name -> value (ad-hoc form values or a
            mapped CSV row).
        strict: When ``True`` (default), any placeholder with no corresponding
            key in ``instance`` raises :class:`~mad.errors.TemplateError`.
            When ``False``, unknown tags are left verbatim so a
            misconfiguration stays visible without aborting.

    Returns:
        The template with every resolvable tag substituted.

    Raises:
        TemplateError: In strict mode, when one or more placeholders are not
            present in ``instance``.
    """
    if not template:
        return ""

    if strict:
        missing = sorted(set(extract_placeholders(template)) - set(instance.keys()))
        if missing:
            names = ", ".join(missing)
            raise TemplateError(
                f"Template references placeholder(s) not present in the instance: "
                f"{names}. Available fields: {', '.join(sorted(map(str, instance.keys()))) or '(none)'}."
            )

    def _replace(match: re.Match[str]) -> str:
        name = match.group(1).strip()
        if name in instance:
            return str(instance[name])
        # Non-strict path: leave the raw tag untouched.
        return match.group(0)

    return PLACEHOLDER_PATTERN.sub(_replace, template)


def validate_template(template: str, available_fields: Iterable[str]) -> list[str]:
    """Validate ``template`` against the fields that will be available at run time.

    This is the pre-flight check for the run launcher and dataset column
    mapping (Req 10.2, 10.3): it does not substitute anything, it only confirms
    every placeholder the template needs can be supplied.

    Args:
        template: The template text to validate.
        available_fields: The field names that will be provided per instance
            (ad-hoc field keys, or the columns a dataset maps to placeholders).

    Returns:
        The list of placeholder names that are *not* covered by
        ``available_fields``, in template order. An empty list means the
        template is fully satisfiable.

    Raises:
        TemplateError: When one or more placeholders are not covered by
            ``available_fields``. The message names the unmet placeholders.
    """
    available = set(available_fields)
    missing = [p for p in extract_placeholders(template) if p not in available]
    if missing:
        names = ", ".join(missing)
        raise TemplateError(
            f"Template placeholder(s) have no matching field: {names}. "
            f"Available fields: {', '.join(sorted(map(str, available))) or '(none)'}."
        )
    return missing
