"""Structured debate record produced by the orchestrator.

The :class:`Transcript` is the engine's single output artifact for one debate
over one instance: it captures *what happened* (the per-round, per-agent
messages), *what it cost* (token/latency/cost usage, aggregated and per-call),
*what was decided* (the final :class:`~mad.engine.agreement.AgreementResult`),
and *what went wrong* (recoverable per-call errors that did not abort the run).

Design choices
--------------
* **Pure data, offline.** Like the rest of the engine
  (:mod:`mad.engine.graph` / ``protocol`` / ``format`` / ``agreement``), this
  module makes no model calls and imports no web/DB dependency. It is a plain
  :mod:`dataclasses` structure so it stays importable from the CLI, the engine,
  and tests, and so the app layer can serialise it to JSON for persistence
  (``execution_instances.transcript``) and the history viewer.

* **Decoupled from the format layer's history shape.** The format layer defines
  its own minimal :class:`~mad.engine.format.HistoryRecord`; the transcript
  carries a richer :class:`AgentMessage` (adds usage + raw structured output)
  and knows how to *project* itself down to the ``HistoryRecord`` list the
  format layer consumes (:meth:`Transcript.to_history`). The orchestrator
  records into the transcript and feeds a derived history into ``format``,
  keeping the two shapes independent.

* **Usage aggregation is additive and total.** Every recorded model call
  contributes a :class:`~mad.providers.base.Usage`; :attr:`Transcript.usage`
  is their running sum (tokens add; cost/latency add when any call reported
  them). This gives Req 9.4's per-run usage roll-up for free while each
  :class:`AgentMessage` retains its own per-call usage for per-agent reporting.

* **Errors are recoverable breadcrumbs, not exceptions.** A model call that
  ultimately failed (after the orchestrator's retry policy) is recorded as a
  :class:`TranscriptError` and the run continues where it can (Req 9.5 /
  10.6 isolation). A fatal error that aborts the whole debate is raised by the
  orchestrator, not stored here.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Optional

from mad.engine.agreement import AgreementResult
from mad.engine.format import HistoryRecord
from mad.providers.base import Usage


@dataclass
class AgentMessage:
    """One agent's turn in the debate.

    Attributes:
        node_id: Id of the participant that authored this turn.
        round_index: 0-based round in which the turn was produced.
        role: The agent's primary role at the time of the turn (``debater`` /
            ``judge`` / ``summarizer`` / ...), recorded for the viewer's
            colour-coding. Defaults to ``"debater"``.
        content: The authored message text.
        usage: Token/latency/cost signals for the model call that produced this
            turn (Req 9.4). Zeroed when no call was made.
        metadata: Attached signals keyed by metadata-signal name (e.g.
            ``{"confidence": 0.8}``), surfaced into downstream context by the
            format layer when configured.
        structured: Parsed structured output when the call requested a
            ``response_schema`` (e.g. a judge's ``{"class": "F"}``); ``None``
            otherwise.
        step: Index of the activation step that produced the turn (turns
            sharing a step were concurrent); ``None`` for turns outside the
            round plan (judge decision). Not persisted.
    """

    node_id: str
    round_index: int
    content: str
    role: str = "debater"
    usage: Usage = field(default_factory=Usage)
    metadata: dict[str, Any] = field(default_factory=dict)
    structured: Optional[dict[str, Any]] = None
    step: Optional[int] = None

    def to_history_record(self) -> HistoryRecord:
        """Project this message to the format layer's :class:`HistoryRecord`."""
        return HistoryRecord(
            node_id=self.node_id,
            round_index=self.round_index,
            content=self.content,
            metadata=dict(self.metadata),
            step=self.step,
        )


@dataclass
class TranscriptError:
    """A recoverable per-call failure that did not abort the run (Req 9.5).

    Attributes:
        node_id: The agent whose model call failed.
        round_index: The round in which the failure occurred.
        message: Human-readable error description (the final exception text
            after retries were exhausted).
        attempts: How many invocation attempts were made before giving up.
    """

    node_id: str
    round_index: int
    message: str
    attempts: int = 1


@dataclass
class Transcript:
    """The structured record of one debate over one instance.

    Attributes:
        config_id: Id of the :class:`~mad.taxonomy.schema.MADConfig` that was
            run (for cross-referencing a persisted config snapshot).
        config_name: Human-readable config name, copied for display.
        instance: The resolved instance inputs (ad-hoc field values / mapped CSV
            row) this debate ran over.
        resolved_input: The debate's initial prompt text after resolving the
            config's ``input_spec.template`` against ``instance``.
        rounds: Number of rounds actually executed (may be < ``max_rounds`` if an
            early consensus stop fired).
        messages: Every :class:`AgentMessage` in activation order across rounds.
        decision: The final :class:`~mad.engine.agreement.AgreementResult`, or
            ``None`` if agreement was never reached (e.g. a dataset pre-run gate
            that aborted before resolution).
        usage: Aggregate :class:`~mad.providers.base.Usage` summed over every
            recorded model call (Req 9.4).
        errors: Recoverable :class:`TranscriptError` breadcrumbs (Req 9.5).
        notes: Human-readable diagnostics bubbled up from the format layer
            (e.g. a summarized→verbatim fallback) and the orchestrator.
        calls: Number of successful model calls folded into :attr:`usage`
            (every recorded message plus calls that produce no message, such
            as summarizer compressions). Failed attempts are not counted.
        duration_s: Wall-clock seconds the debate took, set by the caller that
            timed ``run_debate`` (the job runner); ``None`` when not timed.
    """

    config_id: str
    config_name: str
    instance: dict[str, Any] = field(default_factory=dict)
    resolved_input: str = ""
    rounds: int = 0
    messages: list[AgentMessage] = field(default_factory=list)
    decision: Optional[AgreementResult] = None
    usage: Usage = field(default_factory=Usage)
    errors: list[TranscriptError] = field(default_factory=list)
    notes: list[str] = field(default_factory=list)
    calls: int = 0
    duration_s: Optional[float] = None

    # -- recording helpers (used by the orchestrator) ----------------------

    def add_message(self, message: AgentMessage) -> AgentMessage:
        """Append ``message`` and fold its usage into the aggregate total."""
        self.messages.append(message)
        self.add_usage(message.usage)
        return message

    def add_usage(self, usage: Usage) -> None:
        """Count one successful model call and fold its usage into the total.

        :meth:`add_message` calls this for every recorded turn; the
        orchestrator calls it directly for calls that record no message
        (summarizer compressions), so the totals cover every model call.
        """
        self.calls += 1
        self._accumulate_usage(usage)

    def add_error(self, error: TranscriptError) -> TranscriptError:
        """Record a recoverable per-call failure (Req 9.5)."""
        self.errors.append(error)
        return error

    def add_note(self, note: str) -> None:
        """Record a human-readable diagnostic, de-duplicating repeats."""
        if note and note not in self.notes:
            self.notes.append(note)

    def add_notes(self, notes: list[str]) -> None:
        """Record several diagnostics (see :meth:`add_note`)."""
        for note in notes:
            self.add_note(note)

    # -- views -------------------------------------------------------------

    def to_history(self) -> list[HistoryRecord]:
        """Project the transcript to the format layer's history list.

        Returns the messages (in order) as :class:`HistoryRecord` entries the
        :func:`mad.engine.format.assemble_context` call consumes.
        """
        return [m.to_history_record() for m in self.messages]

    def messages_in_round(self, round_index: int) -> list[AgentMessage]:
        """Return the messages authored in ``round_index`` (activation order)."""
        return [m for m in self.messages if m.round_index == round_index]

    def latest_round_outputs(self) -> list[AgentMessage]:
        """Return the messages of the highest round that has any messages.

        Convenience for agreement resolution, which aggregates the debaters'
        *final* positions. Returns an empty list when nothing was recorded.
        """
        if not self.messages:
            return []
        last = max(m.round_index for m in self.messages)
        return self.messages_in_round(last)

    # -- internals ---------------------------------------------------------

    def _accumulate_usage(self, usage: Usage) -> None:
        """Fold one call's usage into the running aggregate (Req 9.4)."""
        total = self.usage
        total.prompt_tokens += usage.prompt_tokens
        total.completion_tokens += usage.completion_tokens
        total.total_tokens += usage.total_tokens
        if usage.cost_usd is not None:
            total.cost_usd = (total.cost_usd or 0.0) + usage.cost_usd
        if usage.latency_s is not None:
            total.latency_s = (total.latency_s or 0.0) + usage.latency_s


__all__ = [
    "AgentMessage",
    "TranscriptError",
    "Transcript",
]
