"""Request/response DTOs for the providers endpoints (Req 8).

The providers API is the CRUD + connectivity-test surface over configured model
backends (:class:`~app.db.models.Provider`). These Pydantic models are the
*transport contract*; the business logic (encryption, decryption-at-call-time,
registry wiring) lives in the service layer (:mod:`app.services.providers`) and
the engine/security layers, keeping the layering ``routers -> services ->
engine/persistence`` (Req 12.2).

The single most important invariant of this module (Req 8.4): **no response
shape carries the API key.** The create/update *requests* accept a write-only
``api_key`` (plaintext, in transit only); the *responses* expose provider
metadata plus a :pyattr:`ProviderResponse.has_key` boolean and nothing else —
never the key plaintext and never the stored ciphertext. There is deliberately
no response field that could ever serialize key material.

Shapes:

* :class:`ProviderResponse` — the only read shape: id, name, kind, base_url,
  models, timestamps, and ``has_key`` (Req 8.4). Shared by list/create/update/
  get responses so the key-never-returned guarantee holds everywhere.
* :class:`ProviderCreateRequest` — create payload. ``api_key`` is optional
  (local Ollama/vLLM endpoints need none) and write-only.
* :class:`ProviderUpdateRequest` — update payload. Every field is optional so a
  client can patch metadata without resending the key. ``api_key`` is write-only
  and *tri-state*: omit it to keep the stored key, send a non-empty string to
  replace it, or send ``null`` to clear it (see the service for semantics).
* :class:`ProviderTestRequest` / :class:`ProviderTestResponse` — run a
  connectivity check and report success or a clear error (Req 8.5).
* :class:`ProviderDeleteResponse` — delete acknowledgement.

Supported provider kinds (Req 8.2) are enumerated in :data:`PROVIDER_KINDS`;
requests are validated against it so an unsupported kind is rejected at the
transport edge with a clear error.
"""

from __future__ import annotations

from typing import Literal, Optional

from pydantic import BaseModel, Field, field_validator, model_validator

from app.provider_family import check_family_for_kind

FamilyValue = Literal["open_weight", "closed_weight"]

# Supported provider kinds (Req 8.2): closed-weight providers plus open-weight /
# local / generic OpenAI-compatible backends. Kept in sync with the kinds the
# engine's LiteLLM adapter routes.
PROVIDER_KINDS: tuple[str, ...] = (
    "openai",
    "anthropic",
    "gemini",
    "mistral",
    "deepseek",
    "ollama",
    "vllm",
    "openai_compatible",
)


class ProviderResponse(BaseModel):
    """The only provider read shape — metadata + ``has_key``, never the key (Req 8.4).

    This model is returned by every provider endpoint that yields a provider
    (list, create, get, update). It intentionally has **no** field for the API
    key plaintext or ciphertext: the sole key-related signal is ``has_key``, a
    boolean the service derives from whether ciphertext is stored.
    """

    id: int
    name: str
    kind: str = Field(description="Provider kind (see PROVIDER_KINDS).")
    base_url: Optional[str] = Field(
        default=None,
        description="Endpoint override for local/compatible/custom gateways.",
    )
    models: list[str] = Field(
        default_factory=list,
        description="Available model keys for this provider (Req 8.3).",
    )
    family: FamilyValue = Field(
        description=(
            "Effective base-model family: fixed by kind, or the stored choice "
            "(else the kind default) for mixed kinds (mistral, openai_compatible)."
        ),
    )
    has_key: bool = Field(
        description="Whether an API key is configured (the only key info exposed).",
    )
    created_at: Optional[str] = None
    updated_at: Optional[str] = None


class ProviderCreateRequest(BaseModel):
    """Create a new provider (Req 8.1, 8.2, 8.3).

    ``api_key`` is write-only and optional: closed-weight providers need a key,
    while local OpenAI-compatible backends (Ollama, vLLM) typically do not. When
    supplied it is encrypted on save and never echoed back (Req 8.4).
    """

    name: str = Field(min_length=1, description="Human-readable provider label.")
    kind: str = Field(description="Provider kind (see PROVIDER_KINDS).")
    base_url: Optional[str] = Field(
        default=None, description="Optional endpoint override (Req 8.3)."
    )
    models: list[str] = Field(
        default_factory=list,
        description="Available model keys for this provider (Req 8.3).",
    )
    api_key: Optional[str] = Field(
        default=None,
        description="Write-only API key; encrypted at rest, never returned (Req 8.4).",
    )
    family: Optional[FamilyValue] = Field(
        default=None,
        description=(
            "Base-model family; selectable only for mixed kinds (mistral, "
            "openai_compatible). For fixed kinds a matching value is a no-op and "
            "a contradicting one is rejected (422). Omit to use the kind default."
        ),
    )

    @field_validator("kind")
    @classmethod
    def _known_kind(cls, value: str) -> str:
        """Reject unsupported provider kinds at the transport edge (Req 8.2)."""
        if value not in PROVIDER_KINDS:
            supported = ", ".join(PROVIDER_KINDS)
            raise ValueError(
                f"Unsupported provider kind {value!r}. Supported kinds: {supported}."
            )
        return value

    @model_validator(mode="after")
    def _family_matches_kind(self) -> "ProviderCreateRequest":
        """Reject a family that contradicts a fixed kind (task 11.9)."""
        check_family_for_kind(self.kind, self.family)
        return self


class ProviderUpdateRequest(BaseModel):
    """Update an existing provider (Req 8.1, 8.3, 8.4).

    All fields are optional so a client can patch metadata without touching the
    key. ``api_key`` is **write-only and tri-state**:

    * **field omitted** — keep the stored key unchanged (the common case);
    * **non-empty string** — replace the stored key (re-encrypted on save);
    * **explicit ``null``** — clear the stored key.

    Omitting the key is the default so saving an edited provider never requires
    re-entering the secret, and the plaintext is never returned (Req 8.4).
    """

    name: Optional[str] = Field(default=None, min_length=1)
    kind: Optional[str] = None
    base_url: Optional[str] = None
    models: Optional[list[str]] = None
    api_key: Optional[str] = Field(
        default=None,
        description=(
            "Write-only: omit to keep the existing key, send a new key to "
            "replace it, or send null to clear it (Req 8.4)."
        ),
    )
    family: Optional[FamilyValue] = Field(
        default=None,
        description=(
            "Base-model family for mixed kinds. Omit to keep it (or re-derive "
            "when the kind changes), send null to reset to the kind default. "
            "Validated against the resulting kind (422 on contradiction)."
        ),
    )

    # Distinguishes "api_key omitted" (keep) from "api_key: null" (clear). The
    # service inspects the parsed fields to decide; see app.services.providers.
    model_config = {"extra": "forbid"}

    @field_validator("kind")
    @classmethod
    def _known_kind(cls, value: Optional[str]) -> Optional[str]:
        if value is None:
            return value
        if value not in PROVIDER_KINDS:
            supported = ", ".join(PROVIDER_KINDS)
            raise ValueError(
                f"Unsupported provider kind {value!r}. Supported kinds: {supported}."
            )
        return value


class ProviderTestRequest(BaseModel):
    """Optionally target a specific model for the connectivity test (Req 8.5)."""

    model: Optional[str] = Field(
        default=None,
        description="Model key to ping; defaults to the provider's first model.",
    )


class ProviderTestResponse(BaseModel):
    """Outcome of a provider connectivity test (Req 8.5).

    Mirrors the engine's ``ConnectionResult``: ``ok`` plus a human-readable
    ``message`` (success summary or a clear error), with the pinged ``model`` and
    measured ``latency_s`` when available. Never carries key material.
    """

    ok: bool
    message: str
    model: Optional[str] = None
    latency_s: Optional[float] = None


class ProviderDeleteResponse(BaseModel):
    """Acknowledgement for a provider delete."""

    id: int
    deleted: bool = True


__all__ = [
    "PROVIDER_KINDS",
    "ProviderResponse",
    "ProviderCreateRequest",
    "ProviderUpdateRequest",
    "ProviderTestRequest",
    "ProviderTestResponse",
    "ProviderDeleteResponse",
]
