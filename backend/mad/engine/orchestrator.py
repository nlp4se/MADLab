"""Orchestrator: run one debate over one instance into a :class:`Transcript`.

This is the engine's single public entry point (design.md "MAD Engine"):

    run_debate(config, instance, registry) -> Transcript

It ties the four pure engine layers together for one input instance:

    build graph (``graph.py``)              -> who can talk to whom, ``G=(V,E)``
      -> schedule rounds (``protocol.py``)  -> who acts, when, ``E(t)``
        -> assemble context (``format.py``) -> each agent's input ``M(t)`` / ``m̃=f(m)``
          -> invoke the model (``providers``) with per-call retry/backoff
            -> record into the ``Transcript``
    -> resolve agreement (``agreement.py``) -> the final decision

The orchestrator is the *only* engine module that performs model calls; the
layers it composes stay pure. It owns the two behaviours the pure layers
delegate upward:

* **Early consensus stop.** :func:`mad.engine.protocol.schedule_by_round`
  lays out the full ``max_rounds`` plan but never stops early. After each round
  the orchestrator resolves the round's debater outputs and, when the config's
  agreement reaches a confident decision (``undecided == False``) with a
  consensus-style resolution, it stops before the planned final round.

* **Retry / backoff + per-instance error isolation (Req 9.5, 10.6).** Each
  model call is wrapped by :class:`RetryPolicy`: on an exception it retries up
  to ``max_attempts`` with exponential backoff. If every attempt fails the
  failure is recorded as a :class:`~mad.engine.transcript.TranscriptError` and
  the debate continues (that agent simply contributes no message this step);
  one agent's failure never aborts the whole run.

Persona composition lives here (the format layer takes an already-composed
system prompt). The orchestrator builds each agent's system prompt from its
``system_prompt`` / persona fields plus the resolved instance input, wires the
summarizer and judge callables the format/agreement layers expect, and injects
them. It constructs no provider itself — clients come from the injected
:class:`~mad.providers.registry.ProviderRegistry`.
"""

from __future__ import annotations

import time
from dataclasses import dataclass
from typing import Any, Callable, Optional

from mad.engine.agreement import AgreementResult, resolve_agreement
from mad.engine.format import assemble_context, ensure_user_turn, speaker_names
from mad.engine.graph import DebateGraph
from mad.engine.protocol import ActivationStep, schedule_by_round
from mad.engine.transcript import AgentMessage, Transcript, TranscriptError
from mad.errors import ExecutionError, MADError, error_summary
from mad.input.template import resolve_template
from mad.providers.base import Message, ModelResponse
from mad.providers.registry import ProviderRegistry
from mad.taxonomy.schema import Agreement, MADConfig, ParticipantNode

# A sleep hook, injectable so tests do not actually wait during backoff.
SleepFn = Callable[[float], None]


@dataclass
class RetryPolicy:
    """Configurable per-call retry/backoff policy (Req 9.5).

    A failed model call is retried up to ``max_attempts`` times total (the first
    try counts as attempt 1). Backoff before attempt *n* (n >= 2) is
    ``base_delay_s * backoff_factor ** (n - 2)``, capped at ``max_delay_s``. A
    ``max_attempts`` of 1 disables retrying.

    Attributes:
        max_attempts: Total invocation attempts per call (>= 1).
        base_delay_s: Delay before the first retry.
        backoff_factor: Multiplier applied per subsequent retry.
        max_delay_s: Upper bound on any single backoff delay.
    """

    max_attempts: int = 3
    base_delay_s: float = 0.5
    backoff_factor: float = 2.0
    max_delay_s: float = 30.0

    def delay_before(self, attempt: int) -> float:
        """Backoff delay (seconds) before ``attempt`` (1-based). 0 for attempt 1."""
        if attempt <= 1:
            return 0.0
        raw = self.base_delay_s * (self.backoff_factor ** (attempt - 2))
        return min(raw, self.max_delay_s)


# Resolutions whose confident outcome is a legitimate reason to stop a debate
# early (the group has settled). Vote/score resolutions always "decide", so
# stopping on them would collapse every debate to a single round; they run the
# full plan and resolve once at the end.
_CONSENSUS_STOP_RESOLUTIONS = frozenset({"consensus"})

# System instruction of a summarizer node that sets no system prompt.
_DEFAULT_SUMMARIZER_PROMPT = "Summarize the debate so far concisely."

# Closing line of the judge's context: the debate has ended, decide now.
JUDGE_CLOSING = (
    "The debate is over. Evaluate the arguments above and give your final decision."
)

# Stand-in for a turn whose model call failed after retries (judge context).
FAILED_TURN_NOTE = "(no response: the model call failed)"


# ---------------------------------------------------------------------------
# Public entry point
# ---------------------------------------------------------------------------


def run_debate(
    config: MADConfig,
    instance: dict[str, Any],
    registry: ProviderRegistry,
    *,
    retry_policy: Optional[RetryPolicy] = None,
    seed: Optional[int] = None,
    sleep: SleepFn = time.sleep,
) -> Transcript:
    """Execute ``config`` over one ``instance`` and return its :class:`Transcript`.

    Args:
        config: The MAD configuration to run. Topology / protocol / format /
            agreement selections drive the run; ``input_spec.template`` is
            resolved against ``instance`` to form the debate's initial prompt.
        instance: The resolved instance inputs (ad-hoc field values or a mapped
            CSV row) referenced by the template placeholders.
        registry: Resolves each participant's ``base_model`` binding to a model
            client (supports heterogeneous models in one debate, Req 9.2).
        retry_policy: Per-call retry/backoff policy (Req 9.5). Defaults to
            :class:`RetryPolicy`'s defaults (3 attempts, exponential backoff).
        seed: Optional RNG seed forwarded to the scheduler for ``randomized``
            ordering reproducibility.
        sleep: Injectable sleep used for backoff (tests pass a no-op).

    Returns:
        A :class:`Transcript` with the per-round messages, aggregate usage, the
        final decision, and any recoverable per-call errors.

    Raises:
        mad.errors.UnderDevelopment: if the config selects a non-executable
            value the engine layers gate (dynamic topology without a policy,
            coordinator ordering, embeddings syntax, non-short-term memory,
            ``other`` content strategy, ``other`` authority).
        mad.errors.ProviderError: if a participant's model binding cannot be
            resolved.
        mad.errors.ExecutionError: if the run aborts (e.g. the judge fails
            after retries). Any :class:`~mad.errors.MADError` raised once the
            rounds start carries the partial transcript as ``exc.transcript``.
    """
    policy = retry_policy or RetryPolicy()
    interaction = config.interaction

    transcript = Transcript(
        config_id=config.id,
        config_name=config.name,
        instance=dict(instance),
        resolved_input=_resolve_template(config.input_spec.template, instance),
    )

    # Build the pure layers. These raise UnderDevelopment for gated selections,
    # surfacing as a pre-run validation error to the caller/service.
    graph = DebateGraph.from_config(config)
    nodes_by_id = {node.id: node for node in config.participants.nodes}

    plan_by_round = schedule_by_round(
        interaction.protocol, graph, seed=seed
    )

    # A summarizer callable wired to the first summarizer-role node (if any), so
    # content.strategy == "summarized" can compress history.
    summarizer = _make_summarizer(
        config, graph, registry, policy, transcript, sleep
    )

    try:
        _run_rounds_and_agreement(
            config=config,
            graph=graph,
            nodes_by_id=nodes_by_id,
            plan_by_round=plan_by_round,
            registry=registry,
            policy=policy,
            transcript=transcript,
            summarizer=summarizer,
            sleep=sleep,
        )
    except MADError as exc:
        # Keep what was recorded before the failure (messages, errors, notes)
        # so the caller can persist it with the error (task 11.17).
        if exc.transcript is None:
            exc.transcript = transcript
        raise
    return transcript


def _run_rounds_and_agreement(
    *,
    config: MADConfig,
    graph: DebateGraph,
    nodes_by_id: dict[str, ParticipantNode],
    plan_by_round: list,
    registry: ProviderRegistry,
    policy: RetryPolicy,
    transcript: Transcript,
    summarizer: Any,
    sleep: SleepFn,
) -> None:
    """Run every planned round (with the early stop), then the agreement."""
    executed_rounds = 0
    step_index = 0
    for round_index, round_steps in enumerate(plan_by_round):
        # Rounds completed so far; the summarizer callable reads it as the
        # current 0-based round (round prompts, error attribution).
        transcript.rounds = round_index
        executed_rounds = round_index + 1
        for step in round_steps:
            _run_step(
                step=step,
                step_index=step_index,
                config=config,
                graph=graph,
                nodes_by_id=nodes_by_id,
                registry=registry,
                policy=policy,
                transcript=transcript,
                summarizer=summarizer,
                sleep=sleep,
            )
            step_index += 1

        # Early consensus stop: resolve the round's debater outputs and break if
        # a consensus-style agreement has confidently settled.
        if _should_stop_after_round(config.agreement, transcript, config):
            break

    transcript.rounds = executed_rounds

    # Final agreement over the latest round's debater outputs.
    transcript.decision = _resolve_final_agreement(
        config, graph, registry, policy, transcript, sleep
    )
    if transcript.decision is not None and transcript.decision.detail:
        transcript.add_note(transcript.decision.detail)


# ---------------------------------------------------------------------------
# Per-step execution
# ---------------------------------------------------------------------------


def _run_step(
    *,
    step: ActivationStep,
    step_index: int,
    config: MADConfig,
    graph: DebateGraph,
    nodes_by_id: dict[str, ParticipantNode],
    registry: ProviderRegistry,
    policy: RetryPolicy,
    transcript: Transcript,
    summarizer: Any,
    sleep: SleepFn,
) -> None:
    """Run every agent activated in ``step`` and record their messages.

    ``sequential`` steps carry one agent; ``simultaneous`` steps carry several.
    Each agent sees the transcript-so-far (the format layer filters it to the
    agent's predecessors), so within a simultaneous step every agent reads the
    same prior history — they do not see each other's same-step turns, matching
    the "act concurrently" semantics. Each recorded turn carries
    ``step_index`` so later contexts replay concurrent turns faithfully (an
    agent's own turn before the same-step turns it never saw).
    """
    history = transcript.to_history()
    for node_id in step.active:
        node = nodes_by_id.get(node_id)
        if node is None:  # pragma: no cover - plan is derived from the graph.
            continue
        if _is_judge_only(node):
            # A judge does not speak during the debate rounds; it decides at the
            # agreement step (even when the config lists it in protocol.order).
            # Nodes that are *also* debaters still take their turn.
            continue
        _run_agent_turn(
            node=node,
            round_index=step.round_index,
            step_index=step_index,
            config=config,
            graph=graph,
            registry=registry,
            policy=policy,
            transcript=transcript,
            history=history,
            summarizer=summarizer,
            sleep=sleep,
        )


def _run_agent_turn(
    *,
    node: ParticipantNode,
    round_index: int,
    config: MADConfig,
    graph: DebateGraph,
    registry: ProviderRegistry,
    policy: RetryPolicy,
    transcript: Transcript,
    history: list,
    step_index: Optional[int] = None,
    summarizer: Any,
    sleep: SleepFn,
) -> None:
    """Assemble context for ``node``, invoke its model, and record the turn.

    A model failure (after retries) is recorded as a :class:`TranscriptError`
    and the turn is skipped — isolation keeps the run going (Req 9.5 / 10.6).
    """
    task = transcript.resolved_input if _receives_input(config, node.id) else ""
    assembled = assemble_context(
        history=history,
        node=node.id,
        format_spec=config.interaction.format,
        graph=graph,
        system_prompt=_compose_system_prompt(node, task),
        summarizer=summarizer,
        speakers=speaker_names(config.participants.nodes),
        has_task=bool(task),
    )
    transcript.add_notes(assembled.notes)

    try:
        response = _invoke_with_retry(
            registry=registry,
            node=node,
            messages=assembled.messages,
            policy=policy,
            transcript=transcript,
            round_index=round_index,
            sleep=sleep,
            has_task=bool(task),
        )
    except _CallFailed:
        # Already recorded as a TranscriptError; skip this turn.
        return

    transcript.add_message(
        AgentMessage(
            node_id=node.id,
            round_index=round_index,
            content=response.text,
            role=_primary_role(node),
            usage=response.usage,
            structured=response.structured,
            step=step_index,
        )
    )


# ---------------------------------------------------------------------------
# Model invocation + retry/backoff
# ---------------------------------------------------------------------------


class _CallFailed(Exception):
    """Internal signal that a model call exhausted its retries (recorded).

    Carries the attempts made and a short summary of the last error so the
    judge path can say *why* it failed (task 11.17).
    """

    def __init__(self, attempts: int = 0, summary: str = "") -> None:
        super().__init__(summary)
        self.attempts = attempts
        self.summary = summary


# Length caps for error text: the transcript keeps more detail than the
# one-line instance error shown in lists.
_TRANSCRIPT_ERROR_LIMIT = 600
_INSTANCE_ERROR_LIMIT = 300


def _invoke_with_retry(
    *,
    registry: ProviderRegistry,
    node: ParticipantNode,
    messages: list[Message],
    policy: RetryPolicy,
    transcript: Transcript,
    round_index: int,
    sleep: SleepFn,
    response_schema: Optional[dict] = None,
    has_task: bool = False,
) -> ModelResponse:
    """Invoke ``node``'s model with retry/backoff; record + signal on failure.

    Every model call (debater turns, judge, summarizer) goes through here, so
    this is the one place that guarantees a non-system message
    (:func:`~mad.engine.format.ensure_user_turn`): a list with no user turn
    gets a round prompt appended (``has_task`` picks the "Respond to the task
    above." wording). Providers such as Anthropic reject system-only lists.

    Returns the :class:`~mad.providers.base.ModelResponse` on success. On final
    failure, records a :class:`TranscriptError` and raises :class:`_CallFailed`
    so the caller can isolate the turn.

    Retries stop early when they cannot help (task 11.17): a classified
    :class:`~mad.errors.ProviderError` that is not ``retryable`` (auth, unknown
    model, rejected request), or a provider-requested ``retry_after_s`` longer
    than ``policy.max_delay_s`` (e.g. a Gemini free-tier daily quota asking to
    retry in hours). A shorter ``retry_after_s`` stretches the next backoff.
    """
    messages = ensure_user_turn(
        messages, round_index=round_index, has_task=has_task
    )
    client, model_key = registry.resolve(node.base_model)
    params = dict(node.base_model.params)
    params.setdefault("temperature", node.base_model.temperature)

    last_error: Optional[Exception] = None
    attempts = 0
    for attempt in range(1, policy.max_attempts + 1):
        delay = policy.delay_before(attempt)
        retry_after = getattr(last_error, "retry_after_s", None)
        if isinstance(retry_after, (int, float)):
            delay = max(delay, float(retry_after))
        if delay > 0:
            sleep(delay)
        attempts = attempt
        try:
            return client.complete(
                messages=messages,
                model=model_key,
                params=params,
                response_schema=response_schema,
            )
        except Exception as exc:  # noqa: BLE001 - isolate + record any failure.
            last_error = exc
            if not _worth_retrying(exc, policy):
                break

    summary = error_summary(last_error, _TRANSCRIPT_ERROR_LIMIT) if last_error else ""
    transcript.add_error(
        TranscriptError(
            node_id=node.id,
            round_index=round_index,
            message=(
                f"model call for node '{node.id}' failed after "
                f"{attempts} attempt(s): {summary}"
            ),
            attempts=attempts,
        )
    )
    raise _CallFailed(
        attempts=attempts,
        summary=error_summary(last_error, _INSTANCE_ERROR_LIMIT) if last_error else "",
    )


def _worth_retrying(exc: Exception, policy: RetryPolicy) -> bool:
    """Whether another attempt at the same call can succeed (task 11.17)."""
    if getattr(exc, "retryable", True) is False:
        return False
    retry_after = getattr(exc, "retry_after_s", None)
    if isinstance(retry_after, (int, float)) and retry_after > policy.max_delay_s:
        return False
    return True


# ---------------------------------------------------------------------------
# Agreement wiring
# ---------------------------------------------------------------------------


def _resolve_final_agreement(
    config: MADConfig,
    graph: DebateGraph,
    registry: ProviderRegistry,
    policy: RetryPolicy,
    transcript: Transcript,
    sleep: SleepFn,
) -> Optional[AgreementResult]:
    """Resolve the configured agreement over the debate's final outputs."""
    outputs = _debater_outputs(transcript, config)
    judge_fn = _make_judge_fn(
        config, graph, registry, policy, transcript, sleep
    )
    return resolve_agreement(
        config.agreement,
        outputs,
        context=_judge_context(transcript, config),
        judge_fn=judge_fn,
    )


def _should_stop_after_round(
    agreement: Agreement,
    transcript: Transcript,
    config: Optional[MADConfig] = None,
) -> bool:
    """Decide whether a consensus-style agreement has settled early.

    Only consensus-style resolutions trigger an early stop (see
    :data:`_CONSENSUS_STOP_RESOLUTIONS`): resolving the current round's debater
    outputs yields a confident (``undecided == False``) decision. Vote/score
    resolutions always decide, so they never short-circuit here — they run the
    full planned horizon and resolve once at the end.

    When the config sets ``interaction.topology.exit_nodes`` the probe uses the
    same exit-filtered set as the final resolution (:func:`_debater_outputs`);
    with ``exit_nodes`` unset it probes every latest-round output (unchanged
    legacy behaviour).
    """
    if agreement.resolution not in _CONSENSUS_STOP_RESOLUTIONS:
        return False
    if config is not None and config.interaction.topology.exit_nodes is not None:
        outputs = _debater_outputs(transcript, config)
    else:
        outputs = [
            _message_to_output(m) for m in transcript.latest_round_outputs()
        ]
    if not outputs:
        return False
    try:
        result = resolve_agreement(agreement, outputs)
    except Exception:  # noqa: BLE001 - never let a probe abort the loop.
        return False
    return not result.undecided


def _debater_outputs(
    transcript: Transcript, config: MADConfig
) -> list[dict[str, Any]]:
    """Collect the debaters' final-round outputs for collective resolution.

    Uses the latest round that produced messages; judge/summarizer turns are
    excluded so collective strategies aggregate only the debaters' positions.
    When ``interaction.topology.exit_nodes`` is set, only the listed nodes'
    outputs are kept (the End connectors on the canvas); ``None`` keeps every
    debater.
    """
    judge_ids = _role_node_ids(config, "judge")
    summarizer_ids = _role_node_ids(config, "summarizer")
    excluded = judge_ids | summarizer_ids
    exit_nodes = config.interaction.topology.exit_nodes
    allowed = set(exit_nodes) if exit_nodes is not None else None
    return [
        _message_to_output(m)
        for m in transcript.latest_round_outputs()
        if m.node_id not in excluded and (allowed is None or m.node_id in allowed)
    ]


def _message_to_output(message: AgentMessage) -> dict[str, Any]:
    """Project an :class:`AgentMessage` to an agreement ``AgentOutput`` dict."""
    output: dict[str, Any] = {
        "node_id": message.node_id,
        "content": message.content,
    }
    if message.structured:
        # Surface a single-property structured answer as an explicit vote.
        if len(message.structured) == 1:
            output["vote"] = next(iter(message.structured.values()))
    output.update(
        {k: v for k, v in message.metadata.items() if k in {"confidence", "numeric", "score"}}
    )
    return output


def _make_judge_fn(
    config: MADConfig,
    graph: DebateGraph,
    registry: ProviderRegistry,
    policy: RetryPolicy,
    transcript: Transcript,
    sleep: SleepFn,
):
    """Build the judge callable the agreement layer invokes, or ``None``.

    Wires the deciding judge (see :func:`_deciding_judge`) to a model call that
    receives the debate context and returns the judge's reply (text or
    structured). ``None`` when there is no deciding judge, so the agreement
    layer can report the mis-wiring (``judge_based``) or stay undecided
    (``hybrid`` fallback).
    """
    judge_node = _deciding_judge(config)
    if judge_node is None:
        return None

    def judge_fn(context: Any):
        messages: list[Message] = []
        # The judge's own prompt + persona; the task travels in the context.
        system_prompt = _compose_system_prompt(judge_node, "")
        if system_prompt:
            messages.append(Message(role="system", content=system_prompt))
        messages.append(Message(role="user", content=str(context)))
        try:
            response = _invoke_with_retry(
                registry=registry,
                node=judge_node,
                messages=messages,
                policy=policy,
                transcript=transcript,
                round_index=transcript.rounds,
                sleep=sleep,
                response_schema=config.agreement.output_schema,
            )
        except _CallFailed as failed:
            # Name the last provider error so the instance error is actionable
            # on its own (task 11.17); the transcript keeps the longer text.
            reason = f": {failed.summary}" if failed.summary else ""
            raise ExecutionError(
                f"judge node '{judge_node.id}' failed to produce a decision "
                f"after {failed.attempts} attempt(s){reason} "
                "(details in the transcript errors)"
            ) from None
        transcript.add_message(
            AgentMessage(
                node_id=judge_node.id,
                round_index=transcript.rounds,
                content=response.text,
                role="judge",
                usage=response.usage,
                structured=response.structured,
            )
        )
        # Prefer the structured object when present (output_schema path).
        return response.structured if response.structured is not None else response.text

    return judge_fn


def _make_summarizer(
    config: MADConfig,
    graph: DebateGraph,
    registry: ProviderRegistry,
    policy: RetryPolicy,
    transcript: Transcript,
    sleep: SleepFn,
):
    """Build the summarizer callable the format layer uses, or ``None``.

    Wires the first ``summarizer``-role node to a model call that compresses the
    visible history messages into a single string. ``None`` when the config has
    no summarizer node; the format layer then falls back to verbatim.
    """
    summarizer_node = _first_role_node(config, "summarizer")
    if summarizer_node is None:
        return None

    # The node's prompt + persona; the default instruction leads when the
    # node has no explicit system prompt.
    system_prompt = _compose_system_prompt(summarizer_node, "")
    if not summarizer_node.system_prompt:
        system_prompt = "\n\n".join(
            part for part in (_DEFAULT_SUMMARIZER_PROMPT, system_prompt) if part
        )

    def summarize(messages: list[Message]) -> str:
        # ``messages`` are the attributed history turns ("[Round r] Speaker:").
        call_messages: list[Message] = [
            Message(role="system", content=system_prompt)
        ]
        call_messages.extend(messages)
        try:
            response = _invoke_with_retry(
                registry=registry,
                node=summarizer_node,
                messages=call_messages,
                policy=policy,
                transcript=transcript,
                round_index=transcript.rounds,
                sleep=sleep,
            )
        except _CallFailed:
            # Degrade to a trivial concatenation rather than abort the run.
            return "\n".join(m.content for m in messages)
        return response.text

    return summarize


# ---------------------------------------------------------------------------
# Persona composition, template resolution, role helpers
# ---------------------------------------------------------------------------


def _compose_system_prompt(node: ParticipantNode, resolved_input: str) -> str:
    """Compose a node's system prompt from its prompt/persona + the input.

    Precedence: an explicit ``node.system_prompt`` is the base; the persona's
    background/personality/stance are appended as labelled lines when set; the
    resolved instance input (the debate task) is appended last so the agent
    sees what it is debating. Callers pass an empty ``resolved_input`` for nodes
    that are not entry nodes (see :func:`_receives_input`). All parts are
    optional; the result may be empty.
    """
    parts: list[str] = []
    if node.system_prompt:
        parts.append(node.system_prompt.strip())

    persona = node.persona
    persona_lines = [
        f"Background: {persona.background}" if persona.background else "",
        f"Personality: {persona.personality}" if persona.personality else "",
        f"Stance: {persona.stance}" if persona.stance else "",
    ]
    persona_block = "\n".join(line for line in persona_lines if line)
    if persona_block:
        parts.append(persona_block)

    if resolved_input:
        parts.append(f"Task: {resolved_input}")

    return "\n\n".join(parts)


def _resolve_template(template: str, instance: dict[str, Any]) -> str:
    """Resolve ``{{placeholder}}`` tags in ``template`` against ``instance``.

    Delegates to :func:`mad.input.template.resolve_template` in lenient mode:
    each known ``{{key}}`` is substituted while unknown tags are left untouched
    so a misconfiguration stays visible rather than aborting the run. The web /
    CLI run launcher validates templates up front (``validate_template``) so a
    strict error surfaces before execution.
    """
    return resolve_template(template, instance, strict=False)


def _primary_role(node: ParticipantNode) -> str:
    """Return the node's primary role for display (first role, else debater)."""
    return node.roles[0] if node.roles else "debater"


def _is_judge_only(node: ParticipantNode) -> bool:
    """``True`` if ``node`` is a judge and not also a debater.

    A pure judge is driven by the agreement layer, not the round scheduler, so
    it is skipped during activation steps. A node that carries both ``judge``
    and ``debater`` still speaks in the rounds (and may judge at the end).
    """
    return "judge" in node.roles and "debater" not in node.roles


def _role_node_ids(config: MADConfig, role: str) -> set[str]:
    """Return the ids of every node carrying ``role``."""
    return {n.id for n in config.participants.nodes if role in n.roles}


def _first_role_node(config: MADConfig, role: str) -> Optional[ParticipantNode]:
    """Return the first node carrying ``role`` in declaration order, or ``None``."""
    for node in config.participants.nodes:
        if role in node.roles:
            return node
    return None


def _receives_input(config: MADConfig, node_id: str) -> bool:
    """``True`` if ``node_id`` gets the "Task: <input>" line in its system prompt.

    With ``interaction.topology.entry_nodes`` unset (``None``) every speaking
    participant receives the task input (legacy behaviour). When set, only the
    listed entry nodes receive it; the others only see what their predecessors
    send them. The judge's decision context (:func:`_judge_context`) always
    carries the task, independent of ``entry_nodes``.
    """
    entry_nodes = config.interaction.topology.entry_nodes
    return entry_nodes is None or node_id in entry_nodes


def _deciding_judge(config: MADConfig) -> Optional[ParticipantNode]:
    """Return the judge node the agreement layer calls, or ``None``.

    Rule (applies uniformly to ``judge_based`` and to ``hybrid``'s judge
    fallback; ``collective`` never calls the judge):

    * ``interaction.topology.exit_nodes`` unset -> the first ``judge``-role node
      in declaration order (legacy behaviour).
    * ``exit_nodes`` set -> the first ``judge``-role node *listed in*
      ``exit_nodes`` (in list order). If no listed node is a judge there is no
      deciding judge: ``hybrid`` then resolves on the exit debaters' votes only
      (an inconclusive vote stays ``undecided``), and ``judge_based`` cannot
      occur because schema validation requires a judge in its ``exit_nodes``.

    For ``hybrid`` the collective vote step aggregates the exit nodes that are
    debaters (see :func:`_debater_outputs`), so the End connectors on the
    canvas name both the voters and the fallback judge.
    """
    exit_nodes = config.interaction.topology.exit_nodes
    if exit_nodes is None:
        return _first_role_node(config, "judge")
    nodes_by_id = {n.id: n for n in config.participants.nodes}
    for ref in exit_nodes:
        node = nodes_by_id.get(ref)
        if node is not None and "judge" in node.roles:
            return node
    return None


def _judge_context(
    transcript: Transcript, config: Optional[MADConfig] = None
) -> str:
    """Render the whole discussion into the text context a judge receives.

    Layout::

        Task: <resolved input>

        Debate transcript:
        [Round 1] Functional Debater: ...
        [Round 1] Non-functional Debater: (no response: the model call failed)
        ...

        The debate is over. Evaluate the arguments above and give your final decision.

    Every recorded turn (all rounds, all speakers, in order) is attributed by
    speaker name (:func:`~mad.engine.format.speaker_names`, ids without a
    ``config``) and 1-based round. A turn whose call failed after retries is
    listed with :data:`FAILED_TURN_NOTE` at the end of its round, so the judge
    knows a participant was silent rather than absent. The task line is always
    present (independent of ``entry_nodes``) when the input is non-empty.
    """
    speakers = speaker_names(config.participants.nodes) if config else {}

    def name(node_id: str) -> str:
        return speakers.get(node_id) or node_id

    errors_by_round: dict[int, list[TranscriptError]] = {}
    for error in transcript.errors:
        errors_by_round.setdefault(error.round_index, []).append(error)
    rounds = sorted(
        {m.round_index for m in transcript.messages} | set(errors_by_round)
    )

    turns: list[str] = []
    for round_index in rounds:
        label = f"[Round {round_index + 1}]"
        for message in transcript.messages_in_round(round_index):
            turns.append(f"{label} {name(message.node_id)}: {message.content}")
        for error in errors_by_round.get(round_index, []):
            turns.append(f"{label} {name(error.node_id)}: {FAILED_TURN_NOTE}")

    blocks: list[str] = []
    if transcript.resolved_input:
        blocks.append(f"Task: {transcript.resolved_input}")
    if turns:
        blocks.append("Debate transcript:\n" + "\n".join(turns))
    if blocks:
        blocks.append(JUDGE_CLOSING)
    return "\n\n".join(blocks)


__all__ = [
    "RetryPolicy",
    "run_debate",
]
