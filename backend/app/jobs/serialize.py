"""Transcript → JSON projection for persistence and the history viewer.

The engine's :class:`~mad.engine.transcript.Transcript` is a dataclass graph
(messages, usage, decision, errors). The persistence layer stores it as JSON
(``execution_instances.transcript``) and the history viewer renders it, so this
module projects the dataclass into a plain, JSON-serializable dict.

Kept in the ``app.jobs`` layer (not the engine) so the engine stays unaware of
the web/DB JSON shape it is serialized into. It makes no model calls and imports
only the engine's data types plus the standard library.
"""

from __future__ import annotations

from typing import Any, Optional

from mad.engine.agreement import AgreementResult
from mad.engine.transcript import AgentMessage, Transcript, TranscriptError
from mad.providers.base import Usage


def usage_to_dict(usage: Usage) -> dict[str, Any]:
    """Project a :class:`Usage` to a JSON dict."""
    return {
        "prompt_tokens": usage.prompt_tokens,
        "completion_tokens": usage.completion_tokens,
        "total_tokens": usage.total_tokens,
        "cost_usd": usage.cost_usd,
        "latency_s": usage.latency_s,
    }


def message_to_dict(message: AgentMessage) -> dict[str, Any]:
    """Project one :class:`AgentMessage` to a JSON dict."""
    return {
        "node_id": message.node_id,
        "round_index": message.round_index,
        "role": message.role,
        "content": message.content,
        "usage": usage_to_dict(message.usage),
        "metadata": dict(message.metadata),
        "structured": message.structured,
    }


def error_to_dict(error: TranscriptError) -> dict[str, Any]:
    """Project one recoverable :class:`TranscriptError` to a JSON dict."""
    return {
        "node_id": error.node_id,
        "round_index": error.round_index,
        "message": error.message,
        "attempts": error.attempts,
    }


def decision_to_dict(decision: Optional[AgreementResult]) -> Optional[dict[str, Any]]:
    """Project the final :class:`AgreementResult` to a JSON dict, or ``None``."""
    if decision is None:
        return None
    return {
        "decision": decision.decision,
        "authority": decision.authority,
        "resolution": decision.resolution,
        "detail": decision.detail,
        "structured": decision.structured,
        "undecided": decision.undecided,
    }


def transcript_to_dict(transcript: Transcript) -> dict[str, Any]:
    """Project a full :class:`Transcript` to a JSON-serializable dict.

    The shape mirrors the dataclass: config identity, the resolved initial
    prompt, the executed round count, every message in activation order, the
    aggregate usage roll-up, the final decision, recoverable errors, and the
    human-readable notes bubbled up during the run.
    """
    return {
        "config_id": transcript.config_id,
        "config_name": transcript.config_name,
        "resolved_input": transcript.resolved_input,
        "rounds": transcript.rounds,
        "messages": [message_to_dict(m) for m in transcript.messages],
        "usage": usage_to_dict(transcript.usage),
        "decision": decision_to_dict(transcript.decision),
        "errors": [error_to_dict(e) for e in transcript.errors],
        "notes": list(transcript.notes),
    }


__all__ = [
    "usage_to_dict",
    "message_to_dict",
    "error_to_dict",
    "decision_to_dict",
    "transcript_to_dict",
]
