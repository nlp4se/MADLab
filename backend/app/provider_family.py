"""Provider kind -> base-model family mapping (task 11.9, Req 1.7, 8.2).

The base-model *family* (``open_weight`` / ``closed_weight``) is not a free
participant parameter: it is a property of the provider a participant is bound
to. This module is the single source of truth for that derivation and is reused
by the provider schemas/service (validation + effective value), the
configuration/execution services (artifact normalization), and mirrored by the
frontend (``src/api/providerFamily.ts``).

* **Fixed kinds** always map to one family; a stored value is ignored and a
  contradicting request value is rejected.
* **Mixed kinds** (a vendor offering both open- and closed-weight models, or a
  generic OpenAI-compatible gateway) take the stored value, falling back to a
  per-kind default.
"""

from __future__ import annotations

from typing import Optional

OPEN_WEIGHT = "open_weight"
CLOSED_WEIGHT = "closed_weight"
FAMILIES: tuple[str, ...] = (OPEN_WEIGHT, CLOSED_WEIGHT)

# Kinds whose family is fixed by the kind itself.
FIXED_KIND_FAMILY: dict[str, str] = {
    "openai": CLOSED_WEIGHT,
    "anthropic": CLOSED_WEIGHT,
    "gemini": CLOSED_WEIGHT,
    "ollama": OPEN_WEIGHT,
    "vllm": OPEN_WEIGHT,
    "deepseek": OPEN_WEIGHT,
}

# Kinds whose family is user-selectable, with the default used when unset.
MIXED_KIND_DEFAULT_FAMILY: dict[str, str] = {
    "mistral": CLOSED_WEIGHT,
    "openai_compatible": OPEN_WEIGHT,
}


def is_mixed_kind(kind: str) -> bool:
    """Whether ``kind`` lets the user choose the family."""
    return kind in MIXED_KIND_DEFAULT_FAMILY


def default_family(kind: str) -> str:
    """The family a provider of ``kind`` has when no value is stored."""
    if kind in FIXED_KIND_FAMILY:
        return FIXED_KIND_FAMILY[kind]
    return MIXED_KIND_DEFAULT_FAMILY.get(kind, CLOSED_WEIGHT)


def effective_family(kind: str, stored: Optional[str]) -> str:
    """The family a provider actually has: fixed by kind, else stored, else default."""
    if kind in FIXED_KIND_FAMILY:
        return FIXED_KIND_FAMILY[kind]
    if stored in FAMILIES:
        return stored  # type: ignore[return-value]
    return default_family(kind)


def check_family_for_kind(kind: str, family: Optional[str]) -> Optional[str]:
    """Validate a requested ``family`` for ``kind`` and return the value to store.

    * ``None`` -> ``None`` (use the kind's default).
    * Unknown family -> :class:`ValueError`.
    * Fixed kind: a matching value is accepted as a no-op (``None`` stored); a
      contradicting value raises :class:`ValueError`.
    * Mixed kind: the value is stored as-is.
    """
    if family is None:
        return None
    if family not in FAMILIES:
        raise ValueError(
            f"Unsupported family {family!r}. Supported families: {', '.join(FAMILIES)}."
        )
    fixed = FIXED_KIND_FAMILY.get(kind)
    if fixed is not None:
        if family != fixed:
            raise ValueError(
                f"Provider kind {kind!r} is always {fixed}; family {family!r} "
                "cannot be set for it (only mistral and openai_compatible "
                "providers have a selectable family)."
            )
        return None
    return family


__all__ = [
    "OPEN_WEIGHT",
    "CLOSED_WEIGHT",
    "FAMILIES",
    "FIXED_KIND_FAMILY",
    "MIXED_KIND_DEFAULT_FAMILY",
    "is_mixed_kind",
    "default_family",
    "effective_family",
    "check_family_for_kind",
]
