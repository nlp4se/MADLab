"""Protocol scheduler: the temporal activation sequence ``E(t)``.

This module turns the *declarative* protocol of a
:class:`~mad.taxonomy.schema.Protocol` (``interaction.protocol``) into a
concrete, ordered **activation plan**: the sequence of steps describing *which*
agent(s) act, *when* (in which round), and *how* (one-at-a-time vs
concurrently). It is the direct analogue of :mod:`mad.engine.graph` for the
time dimension — where the graph is ``G=(V,E)`` (who *can* talk to whom), the
scheduler is ``E(t)`` (who actually acts, and in what order, over rounds).

Like the graph model it is a **pure function of the configuration**: it makes
no model calls and imports no web dependencies, so it stays importable from the
CLI, the engine, and tests. The orchestrator (task 3.5) consumes the plan,
performs the model calls per step, and is solely responsible for any *early*
consensus stop (see "Consensus stop" below).

Representation
--------------
The plan is a flat, ordered list of :class:`ActivationStep`::

    ActivationStep(round_index=0, active=["alice"],          mode="sequential")
    ActivationStep(round_index=0, active=["bob"],            mode="sequential")
    ActivationStep(round_index=0, active=["carol"],          mode="sequential")
    ActivationStep(round_index=1, active=["alice"],          mode="sequential")
    ...

Each step says which node ids act in that step (``active``) and in which round
(``round_index``, 0-based). ``mode`` records *how* the step's agents act:

* ``"sequential"`` — one agent at a time. ``active`` has length exactly 1.
* ``"simultaneous"`` — all listed agents act concurrently. ``active`` has
  length >= 1 (one step for the whole set).

:func:`schedule` returns the full flat plan across ``protocol.max_rounds``
rounds. :func:`schedule_by_round` returns the same steps grouped into one list
per round (``list[list[ActivationStep]]``), which is the convenient shape for an
orchestrator that iterates round-by-round and may stop between rounds.

Mechanisms
----------
* **sequential** — within each round, agents act one at a time, producing one
  sequential step per agent per round. Ordering:

  * ``fixed`` — use ``protocol.order`` if non-empty (it must be a subset/
    permutation of ``nodes``); otherwise fall back to node declaration order.
  * ``randomized`` — shuffle the order *per round* using a seeded RNG so runs
    are reproducible. Pass ``seed=`` to :func:`schedule` to make it
    deterministic; each round is shuffled independently from that one seed, so
    the same seed always yields the same plan and different seeds can differ.
  * ``coordinator`` — a coordinator model picks the next speaker at run time.
    That needs live model calls, which this static scheduler does not perform,
    so it raises :class:`mad.errors.UnderDevelopment` (matching the catalog's
    ``executable=False`` for coordinator ordering).

* **simultaneous** — within each round, all eligible agents act concurrently: a
  single simultaneous step containing every node, one such step per round.

* **hybrid** — driven by ``protocol.phases`` (an ordered list of
  :class:`~mad.taxonomy.schema.Phase`). The plan composes as
  ``rounds × phases``: for every round, the phases are emitted in order, and
  within a round each phase expands by its own mechanism:

  * a ``sequential`` phase yields one sequential step per listed participant
    (or per node, in declaration order, if ``phase.participants`` is empty);
  * a ``simultaneous`` phase yields a single simultaneous step with the listed
    participants (or all nodes if empty).

Consensus stop
--------------
The scheduler is intentionally *static*: it lays out the full ``max_rounds``
plan and never decides to stop early. Early termination on consensus is the
orchestrator's concern (task 3.5): because :func:`schedule_by_round` groups the
plan per round, the orchestrator can iterate rounds lazily, check its own
consensus condition after each round, and simply ``break`` — no model calls
leak into this module. :func:`is_last_round` is a small convenience for that
loop ("is this the final planned round?").
"""

from __future__ import annotations

import random
from dataclasses import dataclass
from typing import Literal, Optional

from mad.engine.graph import DebateGraph
from mad.errors import UnderDevelopment
from mad.taxonomy.schema import Protocol

Mode = Literal["sequential", "simultaneous"]


@dataclass(frozen=True)
class ActivationStep:
    """One step of the activation plan: who acts, when, and how.

    Attributes:
        round_index: 0-based index of the round this step belongs to.
        active: The node id(s) acting in this step, in activation order. For a
            ``sequential`` step this has length exactly 1; for a
            ``simultaneous`` step it has length >= 1.
        mode: How the step's agents act — ``"sequential"`` (one at a time) or
            ``"simultaneous"`` (concurrently).
    """

    round_index: int
    active: tuple[str, ...]
    mode: Mode

    def __post_init__(self) -> None:
        if not self.active:
            raise ValueError("an activation step must activate at least one node")
        if self.mode == "sequential" and len(self.active) != 1:
            raise ValueError(
                "a sequential activation step must activate exactly one node; "
                f"got {list(self.active)}"
            )


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------


def schedule(
    protocol: Protocol,
    graph: DebateGraph,
    nodes: Optional[list[str]] = None,
    *,
    seed: Optional[int] = None,
) -> list[ActivationStep]:
    """Produce the full activation plan across ``protocol.max_rounds`` rounds.

    Args:
        protocol: The temporal protocol (mechanism / ordering / order / phases /
            max_rounds) to lay out.
        graph: The runtime :class:`~mad.engine.graph.DebateGraph`. Its node set
            defines the default participant universe and declaration order.
        nodes: Optional explicit list of participant node ids (a subset/ordering
            of the graph's nodes). Defaults to ``graph.nodes()``.
        seed: Optional RNG seed used **only** for ``randomized`` sequential
            ordering, to make the shuffle reproducible. Ignored otherwise.

    Returns:
        The ordered, flat list of :class:`ActivationStep` describing ``E(t)``.

    Raises:
        mad.errors.UnderDevelopment: for ``coordinator`` ordering (needs runtime
            model calls, not yet built).
        ValueError: if ``nodes`` / ``protocol.order`` / phase participants do not
            reference graph nodes, or ``hybrid`` has no ``phases``.
    """
    participant_ids = list(nodes) if nodes is not None else graph.nodes()
    _validate_known(participant_ids, graph, context="participant node")

    mechanism = protocol.mechanism
    if mechanism == "sequential":
        return _schedule_sequential(protocol, graph, participant_ids, seed=seed)
    if mechanism == "simultaneous":
        return _schedule_simultaneous(protocol, participant_ids)
    if mechanism == "hybrid":
        return _schedule_hybrid(protocol, graph, participant_ids)
    # Unreachable given the schema's Literal typing.
    raise ValueError(f"unknown protocol mechanism '{mechanism}'")


def schedule_by_round(
    protocol: Protocol,
    graph: DebateGraph,
    nodes: Optional[list[str]] = None,
    *,
    seed: Optional[int] = None,
) -> list[list[ActivationStep]]:
    """Like :func:`schedule`, but grouped into one list of steps per round.

    Returns a list of length ``protocol.max_rounds`` where element ``i`` holds
    every :class:`ActivationStep` with ``round_index == i``, in order. This is
    the convenient shape for an orchestrator that runs round-by-round and may
    stop early on consensus (just ``break`` between rounds).
    """
    plan = schedule(protocol, graph, nodes, seed=seed)
    grouped: list[list[ActivationStep]] = [[] for _ in range(protocol.max_rounds)]
    for step in plan:
        grouped[step.round_index].append(step)
    return grouped


def is_last_round(protocol: Protocol, round_index: int) -> bool:
    """Return ``True`` if ``round_index`` is the final planned round.

    A convenience hook for the orchestrator's round loop. The scheduler never
    stops early itself; the orchestrator owns consensus-based termination.
    """
    return round_index >= protocol.max_rounds - 1


# ---------------------------------------------------------------------------
# Mechanism implementations
# ---------------------------------------------------------------------------


def _schedule_sequential(
    protocol: Protocol,
    graph: DebateGraph,
    participant_ids: list[str],
    *,
    seed: Optional[int],
) -> list[ActivationStep]:
    """One sequential step per agent per round, ordered per ``protocol.ordering``."""
    ordering = protocol.ordering

    if ordering == "coordinator":
        raise UnderDevelopment(
            "Coordinator-driven ordering is not yet executable: selecting the "
            "next speaker requires runtime model calls, which the static "
            "scheduler does not perform. Use 'fixed' or 'randomized' ordering to "
            "run this configuration (the coordinator selection can still be saved)."
        )

    if ordering == "fixed":
        base_order = _fixed_order(protocol, graph, participant_ids)
        plan: list[ActivationStep] = []
        for r in range(protocol.max_rounds):
            for node_id in base_order:
                plan.append(
                    ActivationStep(round_index=r, active=(node_id,), mode="sequential")
                )
        return plan

    if ordering == "randomized":
        # One RNG seeded once; each round is shuffled independently from it so
        # the whole plan is reproducible given the seed.
        rng = random.Random(seed)
        plan = []
        for r in range(protocol.max_rounds):
            round_order = list(participant_ids)
            rng.shuffle(round_order)
            for node_id in round_order:
                plan.append(
                    ActivationStep(round_index=r, active=(node_id,), mode="sequential")
                )
        return plan

    # Unreachable given the schema's Literal typing.
    raise ValueError(f"unknown ordering '{ordering}'")


def _schedule_simultaneous(
    protocol: Protocol,
    participant_ids: list[str],
) -> list[ActivationStep]:
    """One simultaneous step per round containing every participant."""
    active = tuple(participant_ids)
    return [
        ActivationStep(round_index=r, active=active, mode="simultaneous")
        for r in range(protocol.max_rounds)
    ]


def _schedule_hybrid(
    protocol: Protocol,
    graph: DebateGraph,
    participant_ids: list[str],
) -> list[ActivationStep]:
    """Compose ``rounds × phases``: each phase expands by its own mechanism."""
    if not protocol.phases:
        raise ValueError(
            "hybrid protocol requires at least one phase in 'protocol.phases'"
        )

    # Validate phase participant references up front.
    for i, phase in enumerate(protocol.phases):
        _validate_known(
            phase.participants, graph, context=f"phase {i} participant"
        )

    plan: list[ActivationStep] = []
    for r in range(protocol.max_rounds):
        for phase in protocol.phases:
            phase_participants = (
                list(phase.participants) if phase.participants else list(participant_ids)
            )
            if phase.mechanism == "sequential":
                for node_id in phase_participants:
                    plan.append(
                        ActivationStep(
                            round_index=r, active=(node_id,), mode="sequential"
                        )
                    )
            else:  # "simultaneous"
                plan.append(
                    ActivationStep(
                        round_index=r,
                        active=tuple(phase_participants),
                        mode="simultaneous",
                    )
                )
    return plan


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _fixed_order(
    protocol: Protocol,
    graph: DebateGraph,
    participant_ids: list[str],
) -> list[str]:
    """Resolve the fixed activation order.

    Use ``protocol.order`` when non-empty (validated to be a subset of the
    graph's nodes); otherwise fall back to ``participant_ids`` (node declaration
    order).
    """
    if protocol.order:
        _validate_known(protocol.order, graph, context="protocol order entry")
        return list(protocol.order)
    return list(participant_ids)


def _validate_known(
    ids: list[str], graph: DebateGraph, *, context: str
) -> None:
    """Raise ``ValueError`` if any id is not a node of ``graph``."""
    for node_id in ids:
        if not graph.has_node(node_id):
            raise ValueError(
                f"{context} '{node_id}' does not reference an existing graph node"
            )


__all__ = [
    "ActivationStep",
    "schedule",
    "schedule_by_round",
    "is_last_round",
]
