"""Format layer: assemble each agent's input context ``M(t)`` and transform it.

This module sits between the *running debate history* and each model call. Given
a :class:`~mad.taxonomy.schema.Format` spec (syntax / content / memory), the
transcript-so-far, and the target agent, it produces the ordered list of
:class:`~mad.providers.base.Message` objects to send to that agent's model.

It is the engine's realisation of three taxonomy sub-dimensions of
*Interaction → Format* (requirements 2.6-2.8):

* **syntax** (2.6) — ``natural_language`` is the executable path; ``embeddings``
  is gated as under development.
* **content** (2.7) — the message-content transform ``m̃ = f(m)``:
  ``verbatim`` (identity), ``summarized`` (compress via an injected summarizer),
  or ``other`` (gated under development unless a transform is registered).
  Metadata signals (confidence, uncertainty, verifier/judge scores, …) attach to
  the rendered context when configured.
* **memory** (2.8) — the scope of context an agent can access. ``short_term`` is
  the executable default (THIS debate's visible history only); ``long_term`` /
  ``knowledge_retrieval`` / ``parametric`` are gated as under development.

Design choices
--------------
* **Pure, offline, no provider construction.** Like :mod:`mad.engine.graph` and
  :mod:`mad.engine.protocol`, this module imports no web dependencies and makes
  no model calls of its own. The *only* side-effecting hook is an **optional,
  injected summarizer callable** the orchestrator wires to a summarizer agent;
  the format layer never constructs a provider/client itself.

* **System prompt is an input.** Persona composition lives with the orchestrator
  (task 3.5). This layer takes the already-composed ``system_prompt`` string and
  stays focused on MEMORY + CONTENT. It never reaches into a node's persona.

* **Short-term memory = this debate's visible history, topology-filtered.** The
  agent sees only messages authored by its **direct predecessors** in the graph
  (incoming edges). An agent never sees its own prior messages echoed back as
  "incoming" context (they are its own turns, not received arguments). This is
  deliberately kept to *direct* predecessors for this layer; any transitive
  propagation happens because a predecessor incorporated upstream content into
  its own message, which then flows forward naturally round by round.

* **History representation (decoupled from task 3.5).** The transcript model
  arrives *after* this task, so a minimal, self-contained
  :class:`HistoryRecord` is defined here: ``{node_id, round_index, content,
  metadata}``. ``assemble_context`` consumes an ordered ``list[HistoryRecord]``.
  Task 3.5's richer transcript can adopt / adapt this shape (or expose records
  convertible to it) without this module depending on it.

* **Summarized fallback is non-fatal.** When ``content.strategy == "summarized"``
  but no ``summarizer`` callable is injected, the layer does **not** crash: it
  falls back to ``verbatim`` and records a human-readable note (see
  :class:`AssembledContext.notes`). Rationale: a misconfigured "summarized"
  debate should still *run* (producing a slightly larger prompt) rather than
  hard-fail; the recorded note surfaces the misconfiguration to the orchestrator
  / UI. When a summarizer *is* provided, the whole visible-history block is
  replaced by its single summary message.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Callable, Optional

from mad.engine.graph import DebateGraph
from mad.errors import UnderDevelopment
from mad.providers.base import Message
from mad.taxonomy.schema import Format

# A summarizer maps the visible history messages to a single summary string. The
# orchestrator wires this to a summarizer-role agent; the format layer only
# calls it, never builds it.
Summarizer = Callable[[list[Message]], str]


@dataclass
class HistoryRecord:
    """One authored turn in the debate-so-far.

    A minimal, provider-agnostic record of a single agent message. This is the
    decoupled history shape the format layer consumes until task 3.5 defines the
    full transcript model (which may adopt or wrap this structure).

    Attributes:
        node_id: Id of the participant that authored this turn.
        round_index: 0-based round in which the turn was produced.
        content: The authored message text.
        metadata: Optional attached signals keyed by metadata-signal name
            (e.g. ``{"confidence": 0.8}``). Rendered into context only when the
            format's ``content.metadata_signals`` requests them.
    """

    node_id: str
    round_index: int
    content: str
    metadata: dict[str, object] = field(default_factory=dict)


@dataclass
class AssembledContext:
    """Result of :func:`assemble_context`: the messages + diagnostic notes.

    Attributes:
        messages: The ordered :class:`~mad.providers.base.Message` list ready for
            :meth:`~mad.providers.base.ModelClient.complete`.
        notes: Human-readable diagnostics recorded during assembly (e.g. the
            summarized→verbatim fallback). Empty when nothing noteworthy
            happened. Kept so the orchestrator/UI can surface misconfigurations
            without the layer crashing.
    """

    messages: list[Message]
    notes: list[str] = field(default_factory=list)


# ---------------------------------------------------------------------------
# Gating helpers (requirements 2.6 & 2.8)
# ---------------------------------------------------------------------------


def _gate_syntax(format_spec: Format) -> None:
    """Raise :class:`UnderDevelopment` for non-executable syntax."""
    if format_spec.syntax == "embeddings":
        raise UnderDevelopment(
            "Embeddings message syntax is not yet executable: the engine "
            "exchanges natural-language messages only. Use 'natural_language' "
            "syntax to run this configuration (the embeddings selection can "
            "still be saved)."
        )


def _gate_memory(format_spec: Format) -> None:
    """Raise :class:`UnderDevelopment` for non-executable memory scopes."""
    memory = format_spec.memory
    if memory == "short_term":
        return
    reasons = {
        "long_term": (
            "Long-term memory is not yet executable: there is no cross-debate "
            "persistent store to assemble context from."
        ),
        "knowledge_retrieval": (
            "Knowledge-retrieval memory is not yet executable: the engine has no "
            "external retrieval backend to query."
        ),
        "parametric": (
            "Parametric memory is not yet executable: embedding a debate into "
            "model parameters requires a training pipeline the engine does not "
            "provide."
        ),
    }
    detail = reasons.get(memory, f"Memory scope '{memory}' is not yet executable.")
    raise UnderDevelopment(
        f"{detail} Use 'short_term' memory to run this configuration (the "
        f"'{memory}' selection can still be saved)."
    )


# ---------------------------------------------------------------------------
# Metadata signal rendering (requirement 2.7)
# ---------------------------------------------------------------------------


def render_message(record: HistoryRecord, signals: list[str]) -> str:
    """Render a history record's content with its configured metadata signals.

    When ``signals`` is non-empty, any matching keys present in
    ``record.metadata`` are prefixed to the content as bracketed tags, in the
    order ``signals`` lists them::

        render_message(HistoryRecord(..., content="Yes", metadata={"confidence": 0.8}),
                       signals=["confidence"])
        # -> "[confidence: 0.8] Yes"

    Signals requested but absent from the record's metadata are skipped (no
    empty tag). When ``signals`` is empty, the content is returned unchanged —
    the format layer only surfaces metadata the configuration asked for. The
    actual signal *values* are produced elsewhere (agents / orchestrator); this
    helper merely renders present values into the textual context.
    """
    if not signals:
        return record.content

    tags: list[str] = []
    for name in signals:
        if name in record.metadata:
            tags.append(f"[{name}: {record.metadata[name]}]")

    if not tags:
        return record.content
    return f"{' '.join(tags)} {record.content}"


# ---------------------------------------------------------------------------
# Memory assembly M(t) + content transform m̃=f(m)
# ---------------------------------------------------------------------------


def _visible_history(
    history: list[HistoryRecord],
    node: str,
    graph: DebateGraph,
) -> list[HistoryRecord]:
    """Filter ``history`` to the records ``node`` can see (short-term memory).

    Visibility is governed by the topology: an agent sees messages authored by
    its **direct predecessors** (incoming edges). Records are returned in their
    original chronological order (``history`` is assumed ordered by the
    orchestrator). The agent's own turns are excluded — they are its output, not
    received context.
    """
    predecessors = set(graph.predecessors(node))
    return [rec for rec in history if rec.node_id in predecessors]


def _history_messages(
    records: list[HistoryRecord],
    signals: list[str],
) -> list[Message]:
    """Render visible records into ``user`` messages (verbatim passthrough).

    Each visible predecessor turn becomes a ``user`` message carrying the
    (optionally metadata-decorated) content. Prior arguments are presented as
    ``user`` input to the target agent; its own replies are ``assistant`` turns
    the orchestrator records separately.
    """
    return [
        Message(role="user", content=render_message(rec, signals))
        for rec in records
    ]


def assemble_context(
    history: list[HistoryRecord],
    node: str,
    format_spec: Format,
    graph: DebateGraph,
    *,
    system_prompt: str = "",
    summarizer: Optional[Summarizer] = None,
) -> AssembledContext:
    """Assemble the message list to send to ``node``'s model.

    Applies memory assembly ``M(t)`` (short-term, topology-filtered), the content
    transform ``m̃ = f(m)`` per ``format_spec.content.strategy``, and metadata
    signal rendering. Syntax and non-short-term memory are gated as under
    development.

    Args:
        history: The debate-so-far as ordered :class:`HistoryRecord` entries.
        node: The target agent's node id (must exist in ``graph``).
        format_spec: The :class:`~mad.taxonomy.schema.Format` selection.
        graph: The runtime :class:`~mad.engine.graph.DebateGraph`; its
            predecessor relation decides what ``node`` can see.
        system_prompt: The already-composed system prompt for ``node`` (persona
            composition is the orchestrator's job). Prepended as a ``system``
            message when non-empty.
        summarizer: Optional callable wiring a summarizer agent; used only when
            ``content.strategy == "summarized"``.

    Returns:
        An :class:`AssembledContext` with the ordered messages and any
        diagnostic notes (e.g. the summarized→verbatim fallback).

    Raises:
        mad.errors.UnderDevelopment: for ``embeddings`` syntax, non-short-term
            memory, or the ``other`` content strategy.
        KeyError: if ``node`` is not a node of ``graph``.
    """
    _gate_syntax(format_spec)
    _gate_memory(format_spec)

    # M(t): this debate's history, filtered to what the topology lets node see.
    visible = _visible_history(history, node, graph)

    signals = list(format_spec.content.metadata_signals)
    notes: list[str] = []

    # m̃ = f(m): apply the content transform.
    strategy = format_spec.content.strategy
    if strategy == "verbatim":
        history_messages = _history_messages(visible, signals)
    elif strategy == "summarized":
        history_messages, note = _apply_summarized(visible, signals, summarizer)
        if note is not None:
            notes.append(note)
    elif strategy == "other":
        raise UnderDevelopment(
            "The 'other' content strategy is not yet executable: no custom "
            "content transform is registered (transform_ref="
            f"{format_spec.content.transform_ref!r}). Use 'verbatim' or "
            "'summarized' to run this configuration (the 'other' selection can "
            "still be saved)."
        )
    else:  # pragma: no cover - unreachable given the schema's Literal typing.
        raise ValueError(f"unknown content strategy '{strategy}'")

    messages: list[Message] = []
    if system_prompt:
        messages.append(Message(role="system", content=system_prompt))
    messages.extend(history_messages)

    return AssembledContext(messages=messages, notes=notes)


def _apply_summarized(
    visible: list[HistoryRecord],
    signals: list[str],
    summarizer: Optional[Summarizer],
) -> tuple[list[Message], Optional[str]]:
    """Apply the summarized transform, falling back to verbatim when needed.

    Returns ``(messages, note)``. ``note`` is ``None`` on the normal path and a
    human-readable string when the fallback (no summarizer injected) triggers.
    """
    verbatim_messages = _history_messages(visible, signals)

    if summarizer is None:
        # Non-fatal fallback: run verbatim and record why.
        note = (
            "content.strategy is 'summarized' but no summarizer was provided; "
            "falling back to verbatim history for this assembly."
        )
        return verbatim_messages, note

    if not visible:
        # Nothing to summarize; no history block at all.
        return [], None

    summary = summarizer(verbatim_messages)
    return [Message(role="user", content=summary)], None


__all__ = [
    "HistoryRecord",
    "AssembledContext",
    "Summarizer",
    "assemble_context",
    "render_message",
]
