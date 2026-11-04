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
  agent sees the messages authored by its **direct predecessors** in the graph
  (incoming edges) plus **its own prior turns**, in chronological order. This
  is deliberately kept to *direct* predecessors for this layer; any transitive
  propagation happens because a predecessor incorporated upstream content into
  its own message, which then flows forward naturally round by round.

* **Conversation shape.** The agent's own prior turns are replayed verbatim as
  ``assistant`` messages (so in a multi-round debate it keeps track of what it
  argued); every other visible turn is a ``user`` message attributed to its
  speaker and round, e.g. ``"[Round 1] Non-functional Debater: ..."`` (the
  speaker is the node label, disambiguated with the id when labels collide;
  see :func:`speaker_names`). Metadata-signal tags follow the attribution. An
  own turn that no user message precedes (the agent spoke without visible
  history, e.g. round 1, or twice in a row) is preceded by the round prompt it
  actually received (:func:`turn_prompt`), so the list never opens on, nor
  stacks, ``assistant`` turns. Only the others' turns go through the content
  transform: with ``summarized`` they are compressed into one ``user`` summary
  placed after the agent's own turns.

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
  / UI. When a summarizer *is* provided, the others' visible turns are replaced
  by its single summary message (the agent's own turns stay verbatim).
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Callable, Iterable, Mapping, Optional

from mad.engine.graph import DebateGraph
from mad.errors import UnderDevelopment
from mad.providers.base import Message
from mad.taxonomy.schema import Format, ParticipantNode

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
        step: Optional activation-step index. Records sharing a step were
            produced concurrently (a simultaneous step), so none of their
            authors saw the others' turns before speaking. ``None`` when
            unknown (treated as strictly chronological).
    """

    node_id: str
    round_index: int
    content: str
    metadata: dict[str, object] = field(default_factory=dict)
    step: Optional[int] = None


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
    its **direct predecessors** (incoming edges) and its **own** prior turns.
    Records are returned in their original chronological order (``history`` is
    assumed ordered by the orchestrator), except that within a group of
    concurrent records (same non-``None`` ``step``) the agent's own turn comes
    first: it spoke without having seen the others' same-step turns.
    """
    predecessors = set(graph.predecessors(node))
    visible = [
        rec for rec in history if rec.node_id == node or rec.node_id in predecessors
    ]
    ordered: list[HistoryRecord] = []
    i = 0
    while i < len(visible):
        step = visible[i].step
        j = i + 1
        if step is not None:
            while j < len(visible) and visible[j].step == step:
                j += 1
        group = visible[i:j]
        ordered.extend(r for r in group if r.node_id == node)
        ordered.extend(r for r in group if r.node_id != node)
        i = j
    return ordered


def speaker_names(nodes: Iterable[ParticipantNode]) -> dict[str, str]:
    """Map node ids to the speaker names used to attribute history turns.

    The name is the node's label; a label shared by several nodes (compared
    case-insensitively) becomes ``"<label> (<id>)"`` so speakers stay
    distinguishable, and a blank label falls back to the id.
    """
    nodes = list(nodes)
    counts: dict[str, int] = {}
    for n in nodes:
        key = (n.label or "").strip().casefold()
        if key:
            counts[key] = counts.get(key, 0) + 1
    names: dict[str, str] = {}
    for n in nodes:
        label = (n.label or "").strip()
        if not label:
            names[n.id] = n.id
        elif counts[label.casefold()] > 1 and label != n.id:
            names[n.id] = f"{label} ({n.id})"
        else:
            names[n.id] = label
    return names


def attribute(
    record: HistoryRecord,
    signals: list[str],
    speakers: Optional[Mapping[str, str]] = None,
) -> str:
    """Render ``record`` attributed to its speaker and 1-based round.

    ``"[Round 1] Functional Debater: [confidence: 0.8] content"``: the
    speaker comes from ``speakers`` (see :func:`speaker_names`), defaulting to
    the node id; metadata-signal tags (:func:`render_message`) follow it.
    """
    speaker = (speakers or {}).get(record.node_id) or record.node_id
    return (
        f"[Round {record.round_index + 1}] {speaker}: "
        f"{render_message(record, signals)}"
    )


def _thread_messages(
    records: list[HistoryRecord],
    node: str,
    signals: list[str],
    speakers: Optional[Mapping[str, str]],
    has_task: bool,
) -> list[Message]:
    """Render visible records as the agent's chronological conversation.

    ``node``'s own turns become ``assistant`` messages (raw content, blank ones
    skipped); every other turn becomes an attributed ``user`` message. An own
    turn not preceded by a ``user`` message gets the round prompt the agent
    received for it (:func:`turn_prompt`), so the list never starts with, or
    stacks, ``assistant`` turns.
    """
    messages: list[Message] = []
    for rec in records:
        if rec.node_id == node:
            if not rec.content.strip():
                continue
            if not messages or messages[-1].role != "user":
                messages.append(
                    Message(
                        role="user",
                        content=turn_prompt(rec.round_index, has_task=has_task),
                    )
                )
            messages.append(Message(role="assistant", content=rec.content))
        else:
            messages.append(
                Message(role="user", content=attribute(rec, signals, speakers))
            )
    return messages


def assemble_context(
    history: list[HistoryRecord],
    node: str,
    format_spec: Format,
    graph: DebateGraph,
    *,
    system_prompt: str = "",
    summarizer: Optional[Summarizer] = None,
    speakers: Optional[Mapping[str, str]] = None,
    has_task: bool = False,
) -> AssembledContext:
    """Assemble the message list to send to ``node``'s model.

    Applies memory assembly ``M(t)`` (short-term, topology-filtered, own turns
    included), the content transform ``m̃ = f(m)`` per
    ``format_spec.content.strategy``, speaker/round attribution, and metadata
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
            ``content.strategy == "summarized"``. It receives the others'
            visible turns as attributed ``user`` messages.
        speakers: Node id -> speaker name used to attribute others' turns
            (see :func:`speaker_names`); ids are used when absent.
        has_task: Whether ``node``'s system prompt carries the task line;
            selects the wording of round prompts inserted before own turns.

    Returns:
        An :class:`AssembledContext` with the ordered messages and any
        diagnostic notes (e.g. the summarized→verbatim fallback). The list may
        hold no user turn (e.g. round 1 with no visible history); the
        orchestrator applies :func:`ensure_user_turn` to every model call.

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
        history_messages = _thread_messages(visible, node, signals, speakers, has_task)
    elif strategy == "summarized":
        history_messages, note = _apply_summarized(
            visible, node, signals, summarizer, speakers, has_task
        )
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


# ---------------------------------------------------------------------------
# User-turn guarantee (every model call carries a non-system message)
# ---------------------------------------------------------------------------

#: Turn prompt for an agent that received the task (its system prompt carries
#: the "Task: <input>" line) but has no visible history yet. ``{round}`` is the
#: 1-based round number.
TURN_PROMPT_WITH_TASK = "Round {round}. Respond to the task above."

#: Neutral turn prompt for an agent with no task line and no visible history
#: (e.g. a non-entry node whose predecessors have not spoken yet).
TURN_PROMPT_NO_TASK = "Round {round}. Give your contribution for this round."


def turn_prompt(round_index: int, *, has_task: bool) -> str:
    """Return the fallback user turn for 0-based ``round_index``.

    ``has_task`` selects :data:`TURN_PROMPT_WITH_TASK` (the agent's system
    prompt carries the task) over the neutral :data:`TURN_PROMPT_NO_TASK`.
    """
    template = TURN_PROMPT_WITH_TASK if has_task else TURN_PROMPT_NO_TASK
    return template.format(round=round_index + 1)


def has_user_turn(messages: list[Message]) -> bool:
    """``True`` if ``messages`` holds a non-system message with non-blank text."""
    return any(m.role != "system" and m.content.strip() for m in messages)


def ensure_user_turn(
    messages: list[Message],
    *,
    round_index: int,
    has_task: bool,
) -> list[Message]:
    """Guarantee ``messages`` carries at least one non-system message.

    Some providers (Anthropic) reject a request made only of system messages,
    which is what a first-round turn with no visible history assembles. When
    ``messages`` already has a non-blank user/assistant turn it is returned
    unchanged (same list). Otherwise a new list is returned: the system
    messages kept as-is (so the "Task:" line stays in the system prompt),
    blank non-system messages dropped, and :func:`turn_prompt` appended as a
    ``user`` message. Provider-agnostic: it does not rely on LiteLLM's
    ``modify_params``.

    A list that ends on the agent's own ``assistant`` turn (it spoke last and
    nobody it listens to has spoken since) also gets the round prompt
    appended; otherwise the provider would treat that turn as a prefill to
    continue rather than ask for a new contribution.
    """
    if has_user_turn(messages):
        if messages[-1].role != "assistant":
            return messages
        return [
            *messages,
            Message(role="user", content=turn_prompt(round_index, has_task=has_task)),
        ]
    kept = [m for m in messages if m.role == "system"]
    kept.append(
        Message(role="user", content=turn_prompt(round_index, has_task=has_task))
    )
    return kept


def _apply_summarized(
    visible: list[HistoryRecord],
    node: str,
    signals: list[str],
    summarizer: Optional[Summarizer],
    speakers: Optional[Mapping[str, str]],
    has_task: bool,
) -> tuple[list[Message], Optional[str]]:
    """Apply the summarized transform, falling back to verbatim when needed.

    The others' visible turns go to ``summarizer`` as attributed ``user``
    messages and come back as one ``user`` summary, placed after the agent's
    own turns (kept verbatim as ``assistant`` messages). Returns
    ``(messages, note)``: ``note`` is ``None`` on the normal path and a
    human-readable string when the fallback (no summarizer injected) triggers.
    """
    if summarizer is None:
        # Non-fatal fallback: run verbatim and record why.
        note = (
            "content.strategy is 'summarized' but no summarizer was provided; "
            "falling back to verbatim history for this assembly."
        )
        return _thread_messages(visible, node, signals, speakers, has_task), note

    own = [rec for rec in visible if rec.node_id == node]
    others = [rec for rec in visible if rec.node_id != node]
    messages = _thread_messages(own, node, signals, speakers, has_task)
    if not others:
        # Nothing to summarize; only the agent's own turns (if any).
        return messages, None

    summary = summarizer(_thread_messages(others, node, signals, speakers, has_task))
    messages.append(Message(role="user", content=summary))
    return messages, None


__all__ = [
    "HistoryRecord",
    "AssembledContext",
    "Summarizer",
    "assemble_context",
    "render_message",
    "attribute",
    "speaker_names",
    "TURN_PROMPT_WITH_TASK",
    "TURN_PROMPT_NO_TASK",
    "turn_prompt",
    "has_user_turn",
    "ensure_user_turn",
]
