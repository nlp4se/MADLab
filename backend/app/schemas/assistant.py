"""Request/response DTOs for the AI design assistant (task 11.1).

The assistant is a *chat-to-configure* seam over the designer: the user
describes a Multi-Agent Debate (MAD) setup in natural language and the model
either asks a clarifying question or proposes a full, validated
:class:`~mad.taxonomy.schema.MADConfig` artifact.

These Pydantic models are the wire contract for ``POST /api/assistant/design``:

* :class:`AssistantMessage` — one chat turn (``user`` / ``assistant``).
* :class:`AssistantDesignRequest` — the new user message plus the running
  conversation ``history``, the current MAD ``artifact`` being edited (``None``
  for a fresh design), and the per-request ``provider_id`` + ``model`` the user
  picked in the chat panel (the model is never called from the browser).
* :class:`AssistantDesignResponse` — a structured envelope that is *either* a
  free-text clarifying question (``mode="question"``, ``artifact`` null) *or* a
  short explanation accompanied by a validated full artifact
  (``mode="proposal"``). ``under_development`` lists any non-executable taxonomy
  selections in a proposed artifact so the UI can badge them.

The models deliberately mirror the chat/LLM shapes rather than the richer
internal engine types; the service layer (:mod:`app.services.assistant`) owns
the translation to/from :class:`MADConfig`.
"""

from __future__ import annotations

from typing import Any, Literal, Optional

from pydantic import BaseModel, Field


class AssistantMessage(BaseModel):
    """A single chat turn exchanged with the design assistant."""

    role: Literal["user", "assistant"]
    content: str


class AssistantDesignRequest(BaseModel):
    """A design request: the new message + conversation + current artifact.

    Attributes:
        provider_id: DB id of the configured provider to call (per request).
        model: Model key to use on that provider (per request; never hardcoded).
        message: The new user message.
        history: The prior conversation turns, oldest first.
        artifact: The MAD config currently being edited, or ``None``/empty for a
            brand-new design.
    """

    provider_id: int
    model: str
    message: str
    history: list[AssistantMessage] = Field(default_factory=list)
    artifact: Optional[dict[str, Any]] = None


class AssistantDesignResponse(BaseModel):
    """The structured envelope returned to the chat panel.

    Attributes:
        mode: ``"question"`` when the model needs clarification (``artifact`` is
            null) or ``"proposal"`` when ``message`` is a short explanation and
            ``artifact`` is a full, validated :class:`MADConfig` JSON.
        message: The assistant's free-text reply (question or explanation).
        artifact: The proposed full MAD config (only for ``mode="proposal"``).
        under_development: Keys of any non-executable taxonomy selections in a
            proposed artifact, so the UI can badge them.
    """

    mode: Literal["question", "proposal"]
    message: str
    artifact: Optional[dict[str, Any]] = None
    under_development: list[str] = Field(default_factory=list)


__all__ = [
    "AssistantMessage",
    "AssistantDesignRequest",
    "AssistantDesignResponse",
]
