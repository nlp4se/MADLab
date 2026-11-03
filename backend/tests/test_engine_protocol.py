"""Unit + gold-case tests for the protocol scheduler (``mad.engine.protocol``).

These assert the activation plan ``E(t)`` the scheduler produces for each
mechanism (sequential fixed/randomized/coordinator, simultaneous, hybrid), the
round grouping helper, and the exact step shapes for the gold cases (ChatEval
S1/S2/S3 and the RE binary debate).

They depend only on the standard library + the ``mad`` package (schema,
templates, engine), so they run without any third-party web dependency.

Validates: Requirements 2.5
"""

import pytest

from mad.engine import (
    ActivationStep,
    DebateGraph,
    is_last_round,
    schedule,
    schedule_by_round,
)
from mad.errors import UnderDevelopment
from mad.taxonomy import templates
from mad.taxonomy.schema import (
    Edge,
    Participants,
    ParticipantNode,
    Phase,
    Protocol,
    Topology,
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _graph(node_ids, edges=None):
    """Build a bare DebateGraph over ``node_ids`` with optional explicit arcs."""
    return DebateGraph(node_ids, edges or [])


def _fc_graph(node_ids):
    """A fully-connected DebateGraph over ``node_ids``."""
    arcs = [(u, v) for u in node_ids for v in node_ids if u != v]
    return _graph(node_ids, arcs)


def _shape(plan):
    """Compact view of a plan: list of (round_index, mode, active-tuple)."""
    return [(s.round_index, s.mode, s.active) for s in plan]


THREE = ["alice", "bob", "carol"]


# ---------------------------------------------------------------------------
# ActivationStep invariants
# ---------------------------------------------------------------------------


def test_sequential_step_requires_single_node():
    with pytest.raises(ValueError):
        ActivationStep(round_index=0, active=("a", "b"), mode="sequential")


def test_step_requires_at_least_one_node():
    with pytest.raises(ValueError):
        ActivationStep(round_index=0, active=(), mode="simultaneous")


# ---------------------------------------------------------------------------
# Sequential — fixed ordering
# ---------------------------------------------------------------------------


def test_sequential_fixed_uses_protocol_order():
    graph = _fc_graph(THREE)
    proto = Protocol(
        mechanism="sequential", ordering="fixed", order=THREE, max_rounds=2
    )
    plan = schedule(proto, graph)

    # N * max_rounds steps, one agent per step.
    assert len(plan) == len(THREE) * 2
    assert all(s.mode == "sequential" and len(s.active) == 1 for s in plan)

    # Order respected within each round; rounds in sequence.
    assert _shape(plan) == [
        (0, "sequential", ("alice",)),
        (0, "sequential", ("bob",)),
        (0, "sequential", ("carol",)),
        (1, "sequential", ("alice",)),
        (1, "sequential", ("bob",)),
        (1, "sequential", ("carol",)),
    ]


def test_sequential_fixed_falls_back_to_node_order_when_order_empty():
    # Declaration order is carol, alice, bob -> that is the fallback order.
    decl = ["carol", "alice", "bob"]
    graph = _fc_graph(decl)
    proto = Protocol(mechanism="sequential", ordering="fixed", order=[], max_rounds=1)
    plan = schedule(proto, graph)
    assert [s.active[0] for s in plan] == decl


def test_sequential_fixed_order_may_be_a_subset():
    graph = _fc_graph(THREE)
    proto = Protocol(
        mechanism="sequential", ordering="fixed", order=["bob", "alice"], max_rounds=1
    )
    plan = schedule(proto, graph)
    assert [s.active[0] for s in plan] == ["bob", "alice"]


def test_sequential_fixed_rejects_unknown_order_entry():
    graph = _fc_graph(THREE)
    proto = Protocol(
        mechanism="sequential", ordering="fixed", order=["ghost"], max_rounds=1
    )
    with pytest.raises(ValueError):
        schedule(proto, graph)


# ---------------------------------------------------------------------------
# Sequential — randomized ordering (seedable determinism)
# ---------------------------------------------------------------------------


def test_sequential_randomized_is_permutation_each_round():
    graph = _fc_graph(THREE)
    proto = Protocol(mechanism="sequential", ordering="randomized", max_rounds=3)
    plan = schedule(proto, graph, seed=7)

    by_round = schedule_by_round(proto, graph, seed=7)
    for round_steps in by_round:
        order = [s.active[0] for s in round_steps]
        # A permutation of the full participant set each round.
        assert sorted(order) == sorted(THREE)
    assert len(plan) == len(THREE) * 3


def test_sequential_randomized_same_seed_reproduces():
    graph = _fc_graph(THREE)
    proto = Protocol(mechanism="sequential", ordering="randomized", max_rounds=3)
    a = schedule(proto, graph, seed=123)
    b = schedule(proto, graph, seed=123)
    assert _shape(a) == _shape(b)


def test_sequential_randomized_different_seeds_can_differ():
    # Use enough rounds/nodes that two seeds almost surely diverge.
    nodes = ["a", "b", "c", "d", "e"]
    graph = _fc_graph(nodes)
    proto = Protocol(mechanism="sequential", ordering="randomized", max_rounds=4)
    a = schedule(proto, graph, seed=1)
    b = schedule(proto, graph, seed=2)
    assert _shape(a) != _shape(b)


# ---------------------------------------------------------------------------
# Sequential — coordinator ordering is under development
# ---------------------------------------------------------------------------


def test_sequential_coordinator_raises_under_development():
    graph = _fc_graph(THREE)
    proto = Protocol(mechanism="sequential", ordering="coordinator", max_rounds=1)
    with pytest.raises(UnderDevelopment):
        schedule(proto, graph)


# ---------------------------------------------------------------------------
# Simultaneous
# ---------------------------------------------------------------------------


def test_simultaneous_one_step_per_round_all_nodes():
    graph = _fc_graph(THREE)
    proto = Protocol(mechanism="simultaneous", max_rounds=3)
    plan = schedule(proto, graph)

    assert len(plan) == 3
    assert _shape(plan) == [
        (0, "simultaneous", tuple(THREE)),
        (1, "simultaneous", tuple(THREE)),
        (2, "simultaneous", tuple(THREE)),
    ]


# ---------------------------------------------------------------------------
# Hybrid — phase composition within each round
# ---------------------------------------------------------------------------


def test_hybrid_requires_phases():
    graph = _fc_graph(THREE)
    proto = Protocol(mechanism="hybrid", phases=None, max_rounds=1)
    with pytest.raises(ValueError):
        schedule(proto, graph)


def test_hybrid_phases_compose_within_round():
    nodes = ["alice", "bob", "carol", "summarizer"]
    graph = _fc_graph(nodes)
    proto = Protocol(
        mechanism="hybrid",
        max_rounds=2,
        phases=[
            Phase(mechanism="simultaneous", participants=["alice", "bob", "carol"]),
            Phase(mechanism="sequential", participants=["summarizer"]),
        ],
    )
    plan = schedule(proto, graph)

    # Per round: one simultaneous step (3 debaters) then one sequential step.
    assert _shape(plan) == [
        (0, "simultaneous", ("alice", "bob", "carol")),
        (0, "sequential", ("summarizer",)),
        (1, "simultaneous", ("alice", "bob", "carol")),
        (1, "sequential", ("summarizer",)),
    ]


def test_hybrid_sequential_phase_is_one_step_per_participant():
    graph = _fc_graph(THREE)
    proto = Protocol(
        mechanism="hybrid",
        max_rounds=1,
        phases=[Phase(mechanism="sequential", participants=THREE)],
    )
    plan = schedule(proto, graph)
    assert _shape(plan) == [
        (0, "sequential", ("alice",)),
        (0, "sequential", ("bob",)),
        (0, "sequential", ("carol",)),
    ]


def test_hybrid_empty_participants_means_all_nodes():
    graph = _fc_graph(THREE)
    proto = Protocol(
        mechanism="hybrid",
        max_rounds=1,
        phases=[
            Phase(mechanism="simultaneous", participants=[]),
            Phase(mechanism="sequential", participants=[]),
        ],
    )
    plan = schedule(proto, graph)
    assert _shape(plan) == [
        (0, "simultaneous", tuple(THREE)),
        (0, "sequential", ("alice",)),
        (0, "sequential", ("bob",)),
        (0, "sequential", ("carol",)),
    ]


def test_hybrid_rejects_unknown_phase_participant():
    graph = _fc_graph(THREE)
    proto = Protocol(
        mechanism="hybrid",
        max_rounds=1,
        phases=[Phase(mechanism="sequential", participants=["ghost"])],
    )
    with pytest.raises(ValueError):
        schedule(proto, graph)


# ---------------------------------------------------------------------------
# schedule_by_round grouping + total counts
# ---------------------------------------------------------------------------


def test_schedule_by_round_groups_correctly():
    graph = _fc_graph(THREE)
    proto = Protocol(
        mechanism="sequential", ordering="fixed", order=THREE, max_rounds=3
    )
    grouped = schedule_by_round(proto, graph)

    assert len(grouped) == 3
    assert all(len(r) == 3 for r in grouped)
    for i, round_steps in enumerate(grouped):
        assert all(s.round_index == i for s in round_steps)
    # Flattened grouping equals the flat plan.
    flat = [s for r in grouped for s in r]
    assert _shape(flat) == _shape(schedule(proto, graph))


def test_schedule_by_round_length_matches_max_rounds_even_if_phase_order():
    # Grouping always yields exactly max_rounds buckets.
    graph = _fc_graph(["alice", "bob", "carol", "summarizer"])
    proto = Protocol(
        mechanism="hybrid",
        max_rounds=2,
        phases=[
            Phase(mechanism="simultaneous", participants=["alice", "bob", "carol"]),
            Phase(mechanism="sequential", participants=["summarizer"]),
        ],
    )
    grouped = schedule_by_round(proto, graph)
    assert len(grouped) == 2
    assert [len(r) for r in grouped] == [2, 2]


# ---------------------------------------------------------------------------
# Consensus-stop hook
# ---------------------------------------------------------------------------


def test_is_last_round_hook():
    proto = Protocol(mechanism="simultaneous", max_rounds=3)
    assert not is_last_round(proto, 0)
    assert not is_last_round(proto, 1)
    assert is_last_round(proto, 2)


# ---------------------------------------------------------------------------
# Gold cases — expected step shapes
# ---------------------------------------------------------------------------


def test_gold_chateval_s1_sequential_shape():
    config = templates.chateval_s1()
    graph = DebateGraph.from_config(config)
    plan = schedule(config.interaction.protocol, graph)

    # Sequential Alice -> Bob -> Carol, 2 rounds -> 6 steps.
    assert _shape(plan) == [
        (0, "sequential", ("alice",)),
        (0, "sequential", ("bob",)),
        (0, "sequential", ("carol",)),
        (1, "sequential", ("alice",)),
        (1, "sequential", ("bob",)),
        (1, "sequential", ("carol",)),
    ]


def test_gold_chateval_s2_simultaneous_shape():
    config = templates.chateval_s2()
    graph = DebateGraph.from_config(config)
    plan = schedule(config.interaction.protocol, graph)

    # One simultaneous step (all 3 debaters) per round, 2 rounds.
    assert _shape(plan) == [
        (0, "simultaneous", ("alice", "bob", "carol")),
        (1, "simultaneous", ("alice", "bob", "carol")),
    ]


def test_gold_chateval_s3_hybrid_shape():
    config = templates.chateval_s3()
    graph = DebateGraph.from_config(config)
    plan = schedule(config.interaction.protocol, graph)

    # Per round: debaters simultaneous, then summarizer once. 2 rounds.
    assert _shape(plan) == [
        (0, "simultaneous", ("alice", "bob", "carol")),
        (0, "sequential", ("summarizer",)),
        (1, "simultaneous", ("alice", "bob", "carol")),
        (1, "sequential", ("summarizer",)),
    ]


def test_gold_re_binary_debate_sequential_plan():
    config = templates.re_binary_debate()
    graph = DebateGraph.from_config(config)
    plan = schedule(config.interaction.protocol, graph)

    order = ["functional-debater", "non-functional-debater", "judge"]
    expected = []
    for r in range(2):  # max_rounds = 2
        for node_id in order:
            expected.append((r, "sequential", (node_id,)))
    assert _shape(plan) == expected
    assert len(plan) == len(order) * 2
