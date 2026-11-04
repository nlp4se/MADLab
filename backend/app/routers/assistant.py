"""AI design-assistant router (task 11.1).

The transport shell over the chat-to-configure assistant: one endpoint,
``POST /api/assistant/design``, that accepts the user message, the running
conversation, the current MAD artifact, and a per-request provider/model
binding, and returns a structured envelope (a clarifying question or a
validated ``MADConfig`` proposal).

It is deliberately thin — the prompt, the model call, envelope parsing, and
artifact validation all live in :mod:`app.services.assistant` /
:mod:`app.services.assistant_prompt`, keeping the layering ``routers ->
services -> engine/persistence`` (Req 12.2). The model is ALWAYS called from the
backend through the existing LiteLLM provider layer (keys decrypted at call
time) — never from the browser.

The provider registry is exposed as the :func:`get_registry` dependency (built
from the stored providers via :func:`app.services.providers.build_registry`),
so tests override it with a :class:`~mad.providers.base.MockModelClient`-backed
registry for offline, deterministic runs — mirroring the executions router.

``ProviderNotFoundError`` (a genuinely missing provider) is translated to a 404
here; a *runtime* provider failure is handled in the service and returned inline
as a ``question`` so the chat never 500s.
"""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from app.routers.dependencies import get_session
from app.schemas.assistant import AssistantDesignRequest, AssistantDesignResponse
from app.services import assistant as assistant_service
from app.services.assistant import ProviderNotFoundError
from app.services.providers import build_registry
from mad.providers.registry import ProviderRegistry

router = APIRouter(prefix="/assistant", tags=["assistant"])


def get_registry(session: Session = Depends(get_session)) -> ProviderRegistry:
    """Build the engine provider registry from the stored providers (Req 8, 9.2).

    Decrypts each stored key at call time (:func:`build_registry`). Exposed as a
    dependency so tests override it with a mock-backed registry
    (:class:`~mad.providers.base.MockModelClient`) for offline, deterministic
    runs; production uses the real LiteLLM-backed clients.
    """
    return build_registry(session)


@router.post(
    "/design",
    response_model=AssistantDesignResponse,
    summary="Chat-to-configure a MAD design",
)
def design(
    body: AssistantDesignRequest,
    session: Session = Depends(get_session),
    registry: ProviderRegistry = Depends(get_registry),
) -> AssistantDesignResponse:
    """Return a clarifying question or a validated MAD config proposal (task 11.1).

    The model is called through the stored provider identified by
    ``body.provider_id`` using ``body.model``. An unknown provider is a 404;
    runtime provider failures come back as a ``question`` with a clear message.
    """
    try:
        return assistant_service.design(session, body, registry=registry)
    except ProviderNotFoundError as exc:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail=str(exc)
        ) from exc


__all__ = ["router", "get_registry"]
