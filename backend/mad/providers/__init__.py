"""Unified multi-provider model invocation (LiteLLM-backed).

The base protocol and value types (:class:`ModelClient`, :class:`ModelResponse`,
:class:`Message`, :class:`Usage`) plus a deterministic :class:`MockModelClient`
for offline tests live in :mod:`mad.providers.base`. The LiteLLM client lives in
:mod:`mad.providers.litellm_client`; the provider registry (resolution +
connectivity test) lives in :mod:`mad.providers.registry`.
"""

from __future__ import annotations

from mad.providers.base import (
    Message,
    ModelClient,
    ModelResponse,
    MockModelClient,
    Role,
    StructuredMode,
    Usage,
)
from mad.providers.litellm_client import LiteLLMClient
from mad.providers.registry import (
    ClientFactory,
    ConnectionResult,
    ProviderConfig,
    ProviderRegistry,
)

__all__ = [
    "Message",
    "ModelClient",
    "ModelResponse",
    "MockModelClient",
    "Role",
    "StructuredMode",
    "Usage",
    "LiteLLMClient",
    "ClientFactory",
    "ConnectionResult",
    "ProviderConfig",
    "ProviderRegistry",
]
