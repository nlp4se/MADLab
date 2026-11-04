"""Agreement layer: resolve a finished debate into a final decision.

This module realises the *Agreement* dimension of the taxonomy — the
``(authority, resolution)`` pair (requirements 3.1-3.6). Given a
:class:`~mad.taxonomy.schema.Agreement` selection and the debate state (the
debaters' outputs and/or the running transcript), it produces a single
:class:`AgreementResult`.

Two orthogonal choices drive resolution:

* **authority** — *who* decides:
  ``collective`` (the debaters' positions are aggregated, no judge),
  ``judge_based`` (a designated judge agent emits the decision),
  ``hybrid`` (try collective first; fall back to the judge on a tie / no
  consensus), or ``other`` (user-dependent / non-standard — no executable
  semantics, gated as *under development*).
* **resolution** — *how* the decision is computed over a list of agent outputs:
  ``majority_vote``, ``average``, ``consensus``, ``weighted_vote``, ``scoring``,
  or ``argument_evaluation`` (judge-oriented).

Design choices
--------------
* **Pure except for an injected ``judge_fn``.** Like the rest of the engine
  (:mod:`mad.engine.graph` / ``protocol`` / ``format``), this module makes no
  model calls and constructs no providers. Judge-based authority needs a model
  call, so the orchestrator injects a ``judge_fn`` callable
  ``(context) -> str | dict`` wired to the judge-role agent. The agreement layer
  only *calls* it. It imports no web dependency and is fully importable offline.

* **Authority ``other`` is the under-development case.** Although the taxonomy
  catalog does not flag ``other`` with ``executable=False`` (the artifact can
  always be saved), ``other`` has *no defined executable decision semantics*, so
  resolving it raises :class:`~mad.errors.UnderDevelopment`. All six resolution
  mechanisms are executable at the engine level; the only gated path is this
  authority. ``argument_evaluation`` stays *judge-requiring*: without a
  ``judge_fn`` (and no debater-side evaluation) it raises an execution error,
  not an under-development error, because the mechanism itself is runnable — it
  is only mis-wired.

* **Error taxonomy.** Runtime *wiring* problems (``judge_based`` /
  ``argument_evaluation`` with no ``judge_fn``; ``weighted_vote`` /
  ``scoring`` / ``average`` fed unusable outputs) raise
  :class:`~mad.errors.ExecutionError`. A *selection with no executable meaning*
  (``authority == "other"``) raises :class:`~mad.errors.UnderDevelopment`.

* **Consensus & the ``undecided`` signal.** ``consensus`` (and ``hybrid`` when
  collective cannot decide) can legitimately *fail to decide* within the
  available outputs. Rather than inventing an answer, the result carries
  ``undecided=True`` and the orchestrator decides whether to run another round
  (capped by ``protocol.max_rounds``) or, for ``hybrid``, invoke the judge. The
  agreement layer is round-agnostic: it resolves the *current* outputs.

Hybrid tie / fallback logic
---------------------------
``hybrid`` attempts the configured *collective* resolution first. If that
resolution yields a confident decision (``undecided == False``), that decision
stands and the judge is never called. The judge (``judge_fn``) is invoked only
when the collective step is **inconclusive**, which happens when:

* ``consensus`` is not unanimous, or
* a vote (``majority_vote`` / ``weighted_vote``) ends in an exact tie for the
  top answer that the configured ``tie_breaker`` does not resolve, or
* ``argument_evaluation`` is the configured resolution (it is inherently
  judge-oriented, so hybrid routes straight to the judge).

On fallback the judge receives the same ``context`` and its output becomes the
decision (parsed against ``output_schema`` when present). If ``hybrid`` is
inconclusive *and* no ``judge_fn`` is injected, the result is returned with
``undecided=True`` (the orchestrator can retry rounds); this is a softer stance
than ``judge_based``, which hard-requires a judge up front.

output_schema parsing & validation
-----------------------------------
When ``agreement.output_schema`` is present, any *textual* judge decision is
parsed into a structured object and validated against the (JSON-Schema-shaped)
constraint. The parser is deliberately lenient about the judge's surface form:

* a JSON object (``{"class": "F"}``) is parsed as-is;
* a bare scalar (``"F"`` / ``F``) is coerced into the schema's single
  ``enum``-constrained string property when the object schema has exactly one
  such property (the RE binary gold case: ``{class: [F, NF]}`` with a reply of
  ``"F"`` resolves to ``{"class": "F"}``).

The schema may be wrapped in the provider envelope (``{name, description,
schema}``); it is unwrapped by :func:`mad.output_schema.unwrap_output_schema`,
the same normalizer the provider request and label extraction use (task 11.13).

Validation uses :mod:`jsonschema` when installed (it is, in this backend) and
otherwise falls back to a pragmatic check (required keys present, no extra keys
under ``additionalProperties: false``, ``enum`` membership). Either way, a reply
that carries none of the schema's declared properties is rejected, since a
schema without ``required`` would otherwise accept any object.
**Decision on an invalid reply:** an output that cannot be parsed
or fails validation does *not* raise — it is reported as ``undecided=True`` with
the raw text preserved in ``decision`` and the reason in ``detail``. This keeps
a single malformed model reply from aborting a run while still signalling the
problem to the orchestrator/UI; the raw text is retained for debugging.
"""

from __future__ import annotations

import json
from collections import Counter
from dataclasses import dataclass, field
from typing import Any, Callable, Optional, Union

from mad.errors import ExecutionError, UnderDevelopment
from mad.output_schema import declared_properties, unwrap_output_schema
from mad.taxonomy.schema import Agreement

# A judge callable maps an opaque context (transcript, summary, prompt — the
# orchestrator decides) to the judge's decision: free text or an already
# structured object. The agreement layer only calls it; it never builds it.
JudgeFn = Callable[[Any], Union[str, dict[str, Any]]]

# A single agent output consumed by the collective resolution strategies. This
# is intentionally a loose mapping so the orchestrator can pass transcript-
# derived dicts directly. Recognised keys:
#   node_id    - author id (used for per-node weights)
#   content    - raw message text (fallback categorical answer)
#   vote       - explicit categorical answer for vote/consensus strategies
#   numeric    - numeric value for ``average``
#   score      - numeric score (``scoring``) or per-option score mapping
#   confidence - confidence weight (``weighted_vote`` confidence path)
AgentOutput = dict[str, Any]

# The decision can be a plain answer (string/number) or a structured object.
Decision = Union[str, float, int, dict[str, Any], None]


@dataclass
class AgreementResult:
    """The resolved outcome of the Agreement dimension for one debate.

    Attributes:
        decision: The final answer. A string/number for collective strategies, a
            string or structured dict for judge-based decisions, or the raw text
            when a schema-validated decision could not be produced (with
            ``undecided=True``). ``None`` only when there is nothing to decide
            over and no fallback applied.
        authority: The authority that produced this result (``collective`` /
            ``judge_based`` / ``hybrid``).
        resolution: The resolution mechanism applied.
        detail: Optional human-readable rationale / diagnostics (tie-break notes,
            fallback reason, validation failure explanation).
        structured: The parsed + validated structured decision when
            ``output_schema`` is present and parsing succeeded; otherwise
            ``None``.
        undecided: ``True`` when resolution could not reach a confident decision
            (no consensus, unresolved tie with no judge, or an invalid
            schema-constrained reply). Signals the orchestrator to continue
            rounds or fall back.
    """

    decision: Decision
    authority: str
    resolution: str
    detail: Optional[str] = None
    structured: Optional[dict[str, Any]] = None
    undecided: bool = False


# ---------------------------------------------------------------------------
# Public entry point
# ---------------------------------------------------------------------------


def resolve_agreement(
    agreement: Agreement,
    outputs: list[AgentOutput],
    *,
    context: Any = None,
    judge_fn: Optional[JudgeFn] = None,
) -> AgreementResult:
    """Resolve ``agreement`` over the debate state into an :class:`AgreementResult`.

    Args:
        agreement: The :class:`~mad.taxonomy.schema.Agreement` selection
            (authority, resolution, resolution_params, output_schema).
        outputs: The debaters' outputs this round (see :data:`AgentOutput`).
            Used by every collective resolution strategy.
        context: Opaque judge context (transcript / summary / prompt) passed
            through to ``judge_fn`` for judge-based and hybrid-fallback
            decisions. The agreement layer does not interpret it.
        judge_fn: Injected judge callable wiring the judge-role agent. Required
            for ``judge_based`` authority; used as the fallback for ``hybrid``.

    Returns:
        An :class:`AgreementResult`.

    Raises:
        mad.errors.UnderDevelopment: when ``authority == "other"`` (no
            executable semantics).
        mad.errors.ExecutionError: for runtime wiring errors (judge-based or
            argument_evaluation without a ``judge_fn``; strategies fed unusable
            outputs).
    """
    authority = agreement.authority

    if authority == "other":
        raise UnderDevelopment(
            "Agreement authority 'other' (user-dependent / undefined / "
            "non-standard) has no executable decision semantics: the engine "
            "cannot resolve a final decision for it. Choose 'collective', "
            "'judge_based', or 'hybrid' to run this configuration (the 'other' "
            "selection can still be saved)."
        )

    if authority == "judge_based":
        return _resolve_judge_based(agreement, outputs, context, judge_fn)

    if authority == "collective":
        return _resolve_collective(agreement, outputs)

    if authority == "hybrid":
        return _resolve_hybrid(agreement, outputs, context, judge_fn)

    # Unreachable given the schema's Literal typing, but keep an explicit guard.
    raise ExecutionError(  # pragma: no cover
        f"unknown agreement authority '{authority}'"
    )


# ---------------------------------------------------------------------------
# Authority routing
# ---------------------------------------------------------------------------


def _resolve_judge_based(
    agreement: Agreement,
    outputs: list[AgentOutput],
    context: Any,
    judge_fn: Optional[JudgeFn],
) -> AgreementResult:
    """Route the decision to the injected judge and parse against the schema."""
    if judge_fn is None:
        raise ExecutionError(
            "judge_based authority requires an injected judge_fn: the "
            "orchestrator must wire the judge-role agent's model call so the "
            "agreement layer can obtain the final decision. None was provided."
        )

    raw = judge_fn(context)
    return _decision_from_judge(raw, agreement, authority="judge_based")


def _resolve_collective(
    agreement: Agreement,
    outputs: list[AgentOutput],
) -> AgreementResult:
    """Aggregate the debaters' outputs (no judge) via the resolution strategy."""
    return _apply_resolution(agreement, outputs, authority="collective")


def _resolve_hybrid(
    agreement: Agreement,
    outputs: list[AgentOutput],
    context: Any,
    judge_fn: Optional[JudgeFn],
) -> AgreementResult:
    """Try collective resolution; fall back to the judge when inconclusive.

    See the module docstring's "Hybrid tie / fallback logic". ``argument_
    evaluation`` routes straight to the judge; otherwise the configured
    collective strategy runs first and the judge is consulted only when that
    step is ``undecided``.
    """
    if agreement.resolution == "argument_evaluation":
        # Inherently judge-oriented: no debater-side collective step to try.
        if judge_fn is None:
            return AgreementResult(
                decision=None,
                authority="hybrid",
                resolution=agreement.resolution,
                detail=(
                    "hybrid + argument_evaluation needs a judge, but no "
                    "judge_fn was provided; cannot decide on debater outputs "
                    "alone."
                ),
                undecided=True,
            )
        raw = judge_fn(context)
        result = _decision_from_judge(raw, agreement, authority="hybrid")
        result.detail = _join_detail(
            "hybrid: argument_evaluation routed to judge", result.detail
        )
        return result

    collective = _apply_resolution(agreement, outputs, authority="hybrid")
    if not collective.undecided:
        return collective

    # Collective could not decide -> fall back to the judge if available.
    if judge_fn is None:
        collective.detail = _join_detail(
            collective.detail,
            "hybrid: collective step inconclusive and no judge_fn provided; "
            "returning undecided for the orchestrator to retry or escalate.",
        )
        return collective

    raw = judge_fn(context)
    result = _decision_from_judge(raw, agreement, authority="hybrid")
    result.detail = _join_detail(
        _join_detail(
            "hybrid: collective step inconclusive -> fell back to judge",
            collective.detail,
        ),
        result.detail,
    )
    return result


# ---------------------------------------------------------------------------
# Resolution strategies (operate over the debaters' outputs)
# ---------------------------------------------------------------------------


def _apply_resolution(
    agreement: Agreement,
    outputs: list[AgentOutput],
    *,
    authority: str,
) -> AgreementResult:
    """Dispatch to the configured collective resolution strategy."""
    resolution = agreement.resolution
    params = agreement.resolution_params or {}

    if resolution == "majority_vote":
        return _majority_vote(outputs, params, authority)
    if resolution == "weighted_vote":
        return _weighted_vote(outputs, params, authority)
    if resolution == "average":
        return _average(outputs, authority)
    if resolution == "consensus":
        return _consensus(outputs, authority)
    if resolution == "scoring":
        return _scoring(outputs, params, authority)
    if resolution == "argument_evaluation":
        # argument_evaluation with collective authority still needs a judge:
        # there is no debater-side evaluation mechanism. This is a wiring error,
        # not an under-development selection.
        raise ExecutionError(
            "resolution 'argument_evaluation' evaluates the debate via a judge "
            "and cannot run on debater outputs alone. Use 'judge_based' (or "
            "'hybrid') authority with an injected judge_fn, or pick a "
            "debater-side resolution (majority_vote, weighted_vote, average, "
            "scoring, consensus)."
        )

    # Unreachable given the schema's Literal typing.
    raise ExecutionError(  # pragma: no cover
        f"unknown resolution '{resolution}'"
    )


def _categorical_answer(output: AgentOutput) -> Optional[str]:
    """Extract the categorical answer from an output (``vote`` else ``content``)."""
    if output.get("vote") is not None:
        return str(output["vote"])
    content = output.get("content")
    if content is not None:
        return str(content)
    return None


def _majority_vote(
    outputs: list[AgentOutput],
    params: dict[str, Any],
    authority: str,
) -> AgreementResult:
    """Count categorical answers; return the most common.

    Tie-breaking: if two or more answers share the top count, ``params
    ["tie_breaker"]`` is consulted. When it names one of the tied answers that
    answer wins (deterministic, documented). Otherwise the tie is broken
    deterministically by *first appearance order* among the outputs. The chosen
    tie-break path is recorded in ``detail``; a tie with no usable breaker makes
    the result ``undecided`` only for hybrid escalation purposes — majority_vote
    itself always produces an answer via first-appearance, but flags the tie.
    """
    answers = [a for a in (_categorical_answer(o) for o in outputs) if a is not None]
    if not answers:
        raise ExecutionError(
            "majority_vote needs at least one categorical answer (a 'vote' or "
            "'content' field) among the outputs; none were found."
        )

    counts = Counter(answers)
    top_count = max(counts.values())
    tied = [a for a in _dedupe_in_order(answers) if counts[a] == top_count]

    if len(tied) == 1:
        return AgreementResult(
            decision=tied[0],
            authority=authority,
            resolution="majority_vote",
            detail=f"majority_vote: '{tied[0]}' with {top_count} vote(s).",
        )

    # Tie among >= 2 answers.
    tie_breaker = params.get("tie_breaker")
    if tie_breaker is not None and str(tie_breaker) in tied:
        winner = str(tie_breaker)
        return AgreementResult(
            decision=winner,
            authority=authority,
            resolution="majority_vote",
            detail=(
                f"majority_vote: tie among {tied} at {top_count} vote(s); "
                f"resolved by tie_breaker -> '{winner}'."
            ),
        )

    # Deterministic fallback: first-appearance order.
    winner = tied[0]
    return AgreementResult(
        decision=winner,
        authority=authority,
        resolution="majority_vote",
        detail=(
            f"majority_vote: tie among {tied} at {top_count} vote(s); no usable "
            f"tie_breaker, resolved deterministically by first-appearance -> "
            f"'{winner}'."
        ),
        # Flag the tie so hybrid can escalate; collective still has an answer.
        undecided=(authority == "hybrid"),
    )


def _weighted_vote(
    outputs: list[AgentOutput],
    params: dict[str, Any],
    authority: str,
) -> AgreementResult:
    """Votes weighted by per-node ``params['weights']`` or attached confidence.

    Each output contributes its weight to its categorical answer. Weight is
    taken from ``params['weights'][node_id]`` when a weights map is configured;
    otherwise from the output's ``confidence`` (confidence-weighting path);
    defaulting to ``1.0`` when neither is present. The answer with the greatest
    aggregate weight wins; ties fall back to first-appearance order (and flag
    ``undecided`` under hybrid, like ``majority_vote``).
    """
    weights_map = params.get("weights")
    use_confidence = weights_map is None

    aggregate: dict[str, float] = {}
    order: list[str] = []
    for out in outputs:
        answer = _categorical_answer(out)
        if answer is None:
            continue
        if answer not in aggregate:
            aggregate[answer] = 0.0
            order.append(answer)
        if weights_map is not None:
            weight = float(weights_map.get(out.get("node_id"), 0.0))
        elif out.get("confidence") is not None:
            weight = float(out["confidence"])
        else:
            weight = 1.0
        aggregate[answer] += weight

    if not aggregate:
        raise ExecutionError(
            "weighted_vote needs at least one categorical answer among the "
            "outputs; none were found."
        )

    top = max(aggregate.values())
    tied = [a for a in order if aggregate[a] == top]
    winner = tied[0]
    source = "confidence weights" if use_confidence else "configured per-node weights"
    detail = (
        f"weighted_vote ({source}): aggregate {aggregate}; winner '{winner}' "
        f"at weight {top}."
    )
    undecided = len(tied) > 1 and authority == "hybrid"
    if len(tied) > 1:
        detail += f" Tie among {tied} resolved by first-appearance."
    return AgreementResult(
        decision=winner,
        authority=authority,
        resolution="weighted_vote",
        detail=detail,
        undecided=undecided,
    )


def _average(outputs: list[AgentOutput], authority: str) -> AgreementResult:
    """Mean of the numeric outputs (``numeric`` else ``score`` scalar)."""
    values: list[float] = []
    for out in outputs:
        value = out.get("numeric")
        if value is None:
            score = out.get("score")
            if isinstance(score, (int, float)):
                value = score
        if value is None:
            continue
        try:
            values.append(float(value))
        except (TypeError, ValueError):
            continue

    if not values:
        raise ExecutionError(
            "average needs at least one numeric output (a 'numeric' or scalar "
            "'score' field); none were found."
        )

    mean = sum(values) / len(values)
    return AgreementResult(
        decision=mean,
        authority=authority,
        resolution="average",
        detail=f"average: mean of {len(values)} numeric output(s) = {mean}.",
    )


def _consensus(outputs: list[AgentOutput], authority: str) -> AgreementResult:
    """Decide only when all agents agree; otherwise signal ``undecided``."""
    answers = [a for a in (_categorical_answer(o) for o in outputs) if a is not None]
    if not answers:
        raise ExecutionError(
            "consensus needs at least one categorical answer among the outputs; "
            "none were found."
        )

    unique = set(answers)
    if len(unique) == 1:
        answer = answers[0]
        return AgreementResult(
            decision=answer,
            authority=authority,
            resolution="consensus",
            detail=f"consensus: unanimous agreement on '{answer}'.",
        )

    return AgreementResult(
        decision=None,
        authority=authority,
        resolution="consensus",
        detail=(
            f"consensus: no agreement (answers {sorted(unique)}); the "
            "orchestrator may run another round (capped by max_rounds) or, for "
            "hybrid authority, escalate to the judge."
        ),
        undecided=True,
    )


def _scoring(
    outputs: list[AgentOutput],
    params: dict[str, Any],
    authority: str,
) -> AgreementResult:
    """Aggregate agents' per-option scores and pick the best aggregate option.

    Each output's ``score`` is expected to be a mapping ``{option: number}``
    (an agent scoring the candidate answers). Scores are summed per option
    across agents and the top-scoring option wins. ``params['aggregate']`` may
    request ``"mean"`` instead of the default ``"sum"``. Ties fall back to
    first-appearance order (and flag ``undecided`` under hybrid).
    """
    totals: dict[str, float] = {}
    counts: dict[str, int] = {}
    order: list[str] = []
    for out in outputs:
        score = out.get("score")
        if not isinstance(score, dict):
            continue
        for option, value in score.items():
            try:
                num = float(value)
            except (TypeError, ValueError):
                continue
            key = str(option)
            if key not in totals:
                totals[key] = 0.0
                counts[key] = 0
                order.append(key)
            totals[key] += num
            counts[key] += 1

    if not totals:
        raise ExecutionError(
            "scoring needs at least one output with a 'score' mapping "
            "{option: number}; none were found. Configure agents to emit "
            "per-option scores (see resolution_params)."
        )

    aggregate_mode = str(params.get("aggregate", "sum"))
    if aggregate_mode == "mean":
        aggregate = {k: totals[k] / counts[k] for k in totals}
    else:
        aggregate = dict(totals)

    best = max(aggregate.values())
    tied = [k for k in order if aggregate[k] == best]
    winner = tied[0]
    detail = (
        f"scoring ({aggregate_mode}): aggregate {aggregate}; best option "
        f"'{winner}' at {aggregate[winner]}."
    )
    undecided = len(tied) > 1 and authority == "hybrid"
    if len(tied) > 1:
        detail += f" Tie among {tied} resolved by first-appearance."
    return AgreementResult(
        decision=winner,
        authority=authority,
        resolution="scoring",
        detail=detail,
        undecided=undecided,
    )


# ---------------------------------------------------------------------------
# Judge decision + output_schema parsing / validation
# ---------------------------------------------------------------------------


def _decision_from_judge(
    raw: Union[str, dict[str, Any]],
    agreement: Agreement,
    *,
    authority: str,
) -> AgreementResult:
    """Turn a raw judge reply into an :class:`AgreementResult`.

    With no ``output_schema`` the raw reply (text or dict) becomes the decision.
    With a schema, the reply is parsed into a structured object and validated;
    on success ``structured`` carries the validated object and ``decision`` the
    structured object too. On a parse/validation failure the result is
    ``undecided`` with the raw text preserved (documented choice — see module
    docstring).
    """
    resolution = agreement.resolution
    schema = agreement.output_schema

    if schema is None:
        return AgreementResult(
            decision=raw,
            authority=authority,
            resolution=resolution,
            detail="judge decision (no output_schema).",
        )

    parsed, parse_error = _parse_against_schema(raw, schema)
    if parse_error is not None:
        return AgreementResult(
            decision=raw,
            authority=authority,
            resolution=resolution,
            detail=f"judge decision failed schema parsing/validation: {parse_error}",
            undecided=True,
        )

    return AgreementResult(
        decision=parsed,
        authority=authority,
        resolution=resolution,
        detail="judge decision parsed and validated against output_schema.",
        structured=parsed,
    )


def _parse_against_schema(
    raw: Union[str, dict[str, Any]],
    schema: dict[str, Any],
) -> tuple[Optional[dict[str, Any]], Optional[str]]:
    """Parse ``raw`` into a structured object and validate against ``schema``.

    Returns ``(parsed, None)`` on success or ``(None, reason)`` on failure. The
    parser accepts a dict as-is, a JSON-object string, or a bare scalar that is
    coerced into the schema's single enum-constrained string property (the RE
    binary gold case). Validation prefers :mod:`jsonschema` when available and
    otherwise applies a pragmatic required-keys + enum-membership check.

    ``schema`` may be wrapped in the provider envelope (``{name, schema}``);
    it is unwrapped first (:func:`mad.output_schema.unwrap_output_schema`) so
    validation runs against the JSON schema proper (task 11.13).
    """
    schema = unwrap_output_schema(schema) or schema
    obj = _coerce_to_object(raw, schema)
    if obj is None:
        return None, (
            f"could not parse judge reply {raw!r} into an object matching the "
            f"schema"
        )

    error = _validate_object(obj, schema)
    if error is not None:
        return None, error
    return obj, None


def _coerce_to_object(
    raw: Union[str, dict[str, Any]],
    schema: dict[str, Any],
) -> Optional[dict[str, Any]]:
    """Best-effort coercion of a judge reply into an object for ``schema``."""
    if isinstance(raw, dict):
        return raw

    if not isinstance(raw, str):
        return None

    text = raw.strip()
    # Try a JSON object first.
    if text.startswith("{"):
        try:
            loaded = json.loads(text)
        except json.JSONDecodeError:
            loaded = None
        if isinstance(loaded, dict):
            return loaded

    # Bare scalar -> fit into a single enum-constrained string property.
    single = _single_enum_property(schema)
    if single is not None:
        prop_name = single
        # Strip surrounding quotes a model might emit (e.g. '"F"').
        value = text.strip('"').strip("'").strip()
        return {prop_name: value}

    return None


def _single_enum_property(schema: Any) -> Optional[str]:
    """Return the name of the lone enum-constrained string property, if any.

    Accepts a bare or enveloped schema (unwrapped first).
    """
    schema = unwrap_output_schema(schema)
    if schema is None or schema.get("type") != "object":
        return None
    props = schema.get("properties")
    if not isinstance(props, dict):
        return None
    enum_props = [
        name
        for name, spec in props.items()
        if isinstance(spec, dict) and isinstance(spec.get("enum"), list)
    ]
    if len(enum_props) == 1:
        return enum_props[0]
    # Fall back to the lone property even without an enum.
    if len(props) == 1:
        return next(iter(props))
    return None


def _validate_object(obj: dict[str, Any], schema: dict[str, Any]) -> Optional[str]:
    """Validate ``obj`` against ``schema``; return an error reason or ``None``.

    Full JSON Schema validation (``required``, ``additionalProperties``, enums,
    types, ...) via :mod:`jsonschema`, else :func:`_pragmatic_validate`. On top
    of that, a reply that carries *none* of the schema's declared properties is
    rejected (:func:`_off_schema_reason`): with no ``required`` list JSON Schema
    would accept any object, which is how off-schema replies used to pass.
    """
    try:
        import jsonschema  # type: ignore
    except Exception:  # pragma: no cover - exercised only without the dep
        error = _pragmatic_validate(obj, schema)
    else:
        error = None
        try:
            jsonschema.validate(instance=obj, schema=schema)
        except jsonschema.ValidationError as exc:  # type: ignore[attr-defined]
            # exc.message is concise and UI-friendly.
            error = exc.message
        except jsonschema.SchemaError as exc:  # type: ignore[attr-defined]
            return f"invalid output_schema: {exc.message}"
    return error or _off_schema_reason(obj, schema)


def _off_schema_reason(obj: dict[str, Any], schema: dict[str, Any]) -> Optional[str]:
    """Reject a reply (even ``{}``) that shares no key with the declared properties."""
    props = declared_properties(schema)
    if not props or any(key in props for key in obj):
        return None
    return (
        f"reply has none of the schema's properties {sorted(props)} "
        f"(got {sorted(map(str, obj))})"
    )


def _pragmatic_validate(obj: dict[str, Any], schema: dict[str, Any]) -> Optional[str]:
    """Dependency-free fallback: required keys, extra keys, enum membership.

    Checks ``required`` keys exist, rejects keys outside ``properties`` when
    the schema sets ``additionalProperties: false``, and checks that any
    property with an ``enum`` holds one of the allowed values. This is the
    light check used only when :mod:`jsonschema` is unavailable.
    """
    required = schema.get("required", [])
    for key in required:
        if key not in obj:
            return f"missing required key '{key}'"

    props = schema.get("properties", {})
    if schema.get("additionalProperties") is False and isinstance(props, dict):
        extra = sorted(str(k) for k in obj if k not in props)
        if extra:
            return f"additional properties are not allowed ({', '.join(extra)})"

    if isinstance(props, dict):
        for name, spec in props.items():
            if name not in obj or not isinstance(spec, dict):
                continue
            enum = spec.get("enum")
            if isinstance(enum, list) and obj[name] not in enum:
                return (
                    f"value {obj[name]!r} for '{name}' is not one of the allowed "
                    f"options {enum}"
                )
    return None


# ---------------------------------------------------------------------------
# Small helpers
# ---------------------------------------------------------------------------


def _dedupe_in_order(items: list[str]) -> list[str]:
    """Return ``items`` with duplicates removed, preserving first-seen order."""
    seen: set[str] = set()
    result: list[str] = []
    for item in items:
        if item not in seen:
            seen.add(item)
            result.append(item)
    return result


def _join_detail(a: Optional[str], b: Optional[str]) -> Optional[str]:
    """Join two optional detail strings with a separator, dropping empties."""
    parts = [p for p in (a, b) if p]
    return " | ".join(parts) if parts else None


__all__ = [
    "JudgeFn",
    "AgentOutput",
    "Decision",
    "AgreementResult",
    "resolve_agreement",
]
