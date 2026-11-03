"""Tests for the runtime topology graph (``mad.engine.graph.DebateGraph``).

Covers (Req 2.1, 2.3, 2.4, 7.5):

* fully_connected over 3 nodes => 6 directed edges; successors/predecessors;
* structured_network chain / ring / star successor + predecessor shapes;
* grouped => edges restricted within groups;
* explicit edges in the artifact are honoured as authoritative (precedence);
* an undirected edge (directed=False) adds both directions to the adjacency;
* dynamic adaptability without a policy raises UnderDevelopment;
* the gold cases build with the expected edge counts
  (ChatEval S1/S2 = 6 edges over 3 debaters; S3 = 9 edges incl.
  debater->summarizer; RE binary debate = fully-connected over 3 nodes = 6).

Pure data-structure tests: no model calls, no web deps.
"""

import pytest

from mad.engine import DebateGraph
from mad.errors import UnderDevelopment
from mad.taxonomy import templates
from mad.taxonomy.schema import (
    BaseModelSpec,
    Edge,
    Group,
    Interaction,
    MADConfig,
    ParticipantNode,
    Participants,
    Protocol,
    Topology,
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _node(node_id: str, group: str | None = None) -> ParticipantNode:
    return ParticipantNode(id=node_id, label=node_id.title(), group=group)


def _config(
    nodes: list[ParticipantNode],
    topology: Topology,
    groups: list[Group] | None = None,
) -> MADConfig:
    return MADConfig(
        name="test",
        participants=Participants(nodes=nodes, groups=groups or []),
        interaction=Interaction(topology=topology),
    )


# ---------------------------------------------------------------------------
# fully_connected
# ---------------------------------------------------------------------------


def test_fully_connected_three_nodes_has_six_directed_edges():
    nodes = [_node("a"), _node("b"), _node("c")]
    topo = templates.fully_connected_topology(["a", "b", "c"])
    graph = DebateGraph.from_config(_config(nodes, topo))

    assert graph.nodes() == ["a", "b", "c"]
    assert len(graph.edges()) == 6  # n*(n-1) = 3*2

    # Every node reaches (and is reached by) the other two.
    assert sorted(graph.successors("a")) == ["b", "c"]
    assert sorted(graph.successors("b")) == ["a", "c"]
    assert sorted(graph.predecessors("a")) == ["b", "c"]
    assert sorted(graph.predecessors("c")) == ["a", "b"]

    assert graph.has_edge("a", "b")
    assert graph.has_edge("b", "a")
    assert not graph.has_edge("a", "a")


def test_fully_connected_derived_when_no_explicit_edges():
    # structure says fully_connected but edges list is empty -> derive.
    nodes = [_node("a"), _node("b"), _node("c")]
    topo = Topology(structure="fully_connected", edges=[])
    graph = DebateGraph.from_config(_config(nodes, topo))
    assert len(graph.edges()) == 6


# ---------------------------------------------------------------------------
# structured_network patterns
# ---------------------------------------------------------------------------


def test_structured_network_chain_successor_chain():
    nodes = [_node("a"), _node("b"), _node("c")]
    topo = templates.build_topology("chain", ["a", "b", "c"])
    graph = DebateGraph.from_config(_config(nodes, topo))

    assert graph.edges() == [("a", "b"), ("b", "c")]
    assert graph.successors("a") == ["b"]
    assert graph.successors("b") == ["c"]
    assert graph.successors("c") == []
    assert graph.predecessors("a") == []
    assert graph.predecessors("c") == ["b"]


def test_structured_network_ring_closes_the_loop():
    nodes = [_node("a"), _node("b"), _node("c")]
    topo = templates.build_topology("ring", ["a", "b", "c"])
    graph = DebateGraph.from_config(_config(nodes, topo))

    assert ("c", "a") in graph.edges()  # closing edge
    assert graph.successors("c") == ["a"]
    assert graph.predecessors("a") == ["c"]
    assert len(graph.edges()) == 3


def test_structured_network_star_center_has_all_predecessors():
    nodes = [_node("hub"), _node("a"), _node("b")]
    topo = templates.build_topology("star", ["hub", "a", "b"], center="hub")
    graph = DebateGraph.from_config(_config(nodes, topo))

    # Every non-center node points to the center; center aggregates.
    assert sorted(graph.predecessors("hub")) == ["a", "b"]
    assert graph.successors("a") == ["hub"]
    assert graph.successors("hub") == []


def test_structured_network_without_pattern_and_no_edges_raises():
    nodes = [_node("a"), _node("b")]
    # Bypass schema validator (which requires a pattern) by hand-constructing,
    # then assert the graph layer also guards against it.
    topo = Topology.model_construct(
        adaptability="static",
        dynamic_policy=None,
        structure="structured_network",
        pattern=None,
        edges=[],
    )
    with pytest.raises(ValueError, match="requires a 'pattern'"):
        DebateGraph.from_parts(Participants(nodes=nodes), topo)


# ---------------------------------------------------------------------------
# grouped
# ---------------------------------------------------------------------------


def test_grouped_edges_restricted_within_groups():
    groups = [Group(id="g1", label="G1"), Group(id="g2", label="G2")]
    nodes = [
        _node("a", group="g1"),
        _node("b", group="g1"),
        _node("c", group="g2"),
        _node("d", group="g2"),
    ]
    topo = Topology(structure="grouped", edges=[])
    graph = DebateGraph.from_config(_config(nodes, topo, groups=groups))

    # Within-group fully-connected: g1 {a,b} = 2 edges, g2 {c,d} = 2 edges.
    assert len(graph.edges()) == 4
    assert graph.has_edge("a", "b")
    assert graph.has_edge("b", "a")
    assert graph.has_edge("c", "d")
    # No cross-group edges.
    assert not graph.has_edge("a", "c")
    assert not graph.has_edge("b", "d")
    assert sorted(graph.successors("a")) == ["b"]
    assert sorted(graph.successors("c")) == ["d"]


def test_grouped_ungrouped_nodes_are_isolated():
    groups = [Group(id="g1", label="G1")]
    nodes = [_node("a", group="g1"), _node("b", group="g1"), _node("lonely")]
    topo = Topology(structure="grouped", edges=[])
    graph = DebateGraph.from_config(_config(nodes, topo, groups=groups))

    assert graph.successors("lonely") == []
    assert graph.predecessors("lonely") == []
    assert len(graph.edges()) == 2


# ---------------------------------------------------------------------------
# explicit-edges precedence
# ---------------------------------------------------------------------------


def test_explicit_edges_are_authoritative_over_structure():
    # structure claims fully_connected (would be 6 edges) but explicit edges
    # define only a single arc -> explicit wins.
    nodes = [_node("a"), _node("b"), _node("c")]
    topo = Topology(
        structure="fully_connected",
        edges=[Edge(source="a", target="b", directed=True)],
    )
    graph = DebateGraph.from_config(_config(nodes, topo))

    assert graph.edges() == [("a", "b")]
    assert graph.successors("a") == ["b"]
    assert graph.successors("b") == []


# ---------------------------------------------------------------------------
# undirected edge -> both directions
# ---------------------------------------------------------------------------


def test_undirected_edge_adds_both_directions():
    nodes = [_node("a"), _node("b"), _node("c")]
    topo = Topology(
        structure="fully_connected",
        edges=[Edge(source="a", target="b", directed=False)],
    )
    graph = DebateGraph.from_config(_config(nodes, topo))

    assert graph.has_edge("a", "b")
    assert graph.has_edge("b", "a")
    assert graph.successors("a") == ["b"]
    assert graph.successors("b") == ["a"]
    assert len(graph.edges()) == 2


# ---------------------------------------------------------------------------
# dynamic adaptability without policy
# ---------------------------------------------------------------------------


def test_dynamic_adaptability_without_policy_raises_under_development():
    nodes = [_node("a"), _node("b")]
    topo = Topology(
        adaptability="dynamic",
        structure="fully_connected",
        edges=[Edge(source="a", target="b")],
    )
    with pytest.raises(UnderDevelopment, match="Dynamic topology"):
        DebateGraph.from_config(_config(nodes, topo))


def test_static_topology_builds_normally():
    nodes = [_node("a"), _node("b")]
    topo = Topology(adaptability="static", edges=[Edge(source="a", target="b")])
    graph = DebateGraph.from_config(_config(nodes, topo))
    assert graph.successors("a") == ["b"]


# ---------------------------------------------------------------------------
# unknown-node queries
# ---------------------------------------------------------------------------


def test_queries_for_unknown_node_raise_keyerror():
    graph = DebateGraph(["a"], [])
    with pytest.raises(KeyError):
        graph.successors("missing")
    with pytest.raises(KeyError):
        graph.predecessors("missing")
    assert not graph.has_edge("a", "missing")
    assert graph.has_node("a")
    assert not graph.has_node("missing")


def test_construction_rejects_edge_to_unknown_node():
    with pytest.raises(ValueError, match="does not reference an existing node"):
        DebateGraph(["a", "b"], [("a", "ghost")])


# ---------------------------------------------------------------------------
# gold cases
# ---------------------------------------------------------------------------


def test_re_binary_debate_graph_is_fully_connected_over_three_nodes():
    graph = DebateGraph.from_config(templates.re_binary_debate())
    assert len(graph.nodes()) == 3
    assert len(graph.edges()) == 6  # fully-connected over 3 nodes
    for node in graph.nodes():
        # Every node connects to both others in a fully-connected debate.
        assert sorted(graph.successors(node)) == sorted(
            n for n in graph.nodes() if n != node
        )


def test_chateval_s1_and_s2_have_six_edges_over_three_debaters():
    for builder in (templates.chateval_s1, templates.chateval_s2):
        graph = DebateGraph.from_config(builder())
        assert len(graph.nodes()) == 3
        assert len(graph.edges()) == 6


def test_chateval_s3_has_nine_edges_including_debater_to_summarizer():
    graph = DebateGraph.from_config(templates.chateval_s3())
    assert len(graph.nodes()) == 4  # 3 debaters + summarizer
    assert len(graph.edges()) == 9  # 6 among debaters + 3 debater->summarizer

    # The summarizer receives from every debater and sends to none.
    assert sorted(graph.predecessors("summarizer")) == ["alice", "bob", "carol"]
    assert graph.successors("summarizer") == []
