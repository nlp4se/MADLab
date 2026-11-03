"""Tests for predefined templates and gold-case configs (``mad.taxonomy.templates``).

Covers:
* every persona pattern applies and yields non-empty persona field-set(s);
* each topology builder produces the expected edge count/shape;
* role definitions expose the six catalog roles with icons;
* each gold config constructs/validates;
* S1/S2/S3 differ ONLY in the documented attributes and share the rest
  (the paper's benchmarking claim, Req 4.4);
* RE binary debate specifics (judge node for judge_based authority, output
  schema constrains class to [F, NF], input template has {{requirement}});
* gold configs survive an export/import round-trip (version.py from task 1.3).

Depends only on pydantic + the ``mad`` package.
"""

import pytest

from mad.taxonomy import catalog
from mad.taxonomy.schema import MADConfig
from mad.taxonomy.version import export_config, import_config
from mad.taxonomy import templates
from mad.taxonomy.templates import (
    apply_persona_pattern,
    bipartite,
    build_topology,
    chain,
    chateval_s1,
    chateval_s2,
    chateval_s3,
    fully_connected,
    fully_connected_topology,
    get_persona_pattern,
    gold_cases,
    layered,
    list_persona_patterns,
    list_roles,
    re_binary_debate,
    ring,
    sparse,
    star,
    tree,
)


# ---------------------------------------------------------------------------
# Persona patterns
# ---------------------------------------------------------------------------

_EXPECTED_PATTERN_KEYS = {
    "angel",
    "devil",
    "prosecution",
    "defence",
    "faithful",
    "unfaithful",
    "proponent",
    "challenger",
    "gold",
    "distractor",
    "six_thinking_hats",
    "domain_expert_panel",
}


def test_all_expected_persona_patterns_present():
    keys = {p.key for p in list_persona_patterns()}
    assert _EXPECTED_PATTERN_KEYS <= keys


@pytest.mark.parametrize("key", sorted(_EXPECTED_PATTERN_KEYS))
def test_every_pattern_applies_and_yields_nonempty_personas(key):
    personas = apply_persona_pattern(key)
    assert len(personas) >= 1
    for persona in personas:
        # at least one of background/personality/stance is non-empty
        content = [persona.background, persona.personality, persona.stance]
        assert any(c and c.strip() for c in content)
        # the applied persona carries the template ref back to the pattern
        assert persona.template_ref == key


def test_opposing_pairs_reference_each_other():
    for a, b in [
        ("angel", "devil"),
        ("prosecution", "defence"),
        ("faithful", "unfaithful"),
        ("proponent", "challenger"),
        ("gold", "distractor"),
    ]:
        assert get_persona_pattern(a).pair_with == b
        assert get_persona_pattern(b).pair_with == a


def test_set_patterns_expand_to_multiple_personas():
    assert len(apply_persona_pattern("six_thinking_hats")) == 6
    assert len(apply_persona_pattern("domain_expert_panel")) >= 3
    assert get_persona_pattern("six_thinking_hats").is_set is True


def test_apply_unknown_pattern_raises():
    with pytest.raises(KeyError):
        apply_persona_pattern("nope")


# ---------------------------------------------------------------------------
# Topology builders
# ---------------------------------------------------------------------------


def _pairs(edges):
    return {(e.source, e.target) for e in edges}


def test_fully_connected_edge_count_and_shape():
    nodes = ["a", "b", "c"]
    edges = fully_connected(nodes)
    assert len(edges) == 6  # n(n-1) = 3*2
    assert _pairs(edges) == {
        ("a", "b"), ("a", "c"),
        ("b", "a"), ("b", "c"),
        ("c", "a"), ("c", "b"),
    }
    assert all(e.directed for e in edges)


def test_chain_edge_count_and_shape():
    nodes = ["a", "b", "c", "d"]
    edges = chain(nodes)
    assert len(edges) == len(nodes) - 1  # n-1
    assert _pairs(edges) == {("a", "b"), ("b", "c"), ("c", "d")}


def test_ring_edge_count_and_shape():
    nodes = ["a", "b", "c", "d"]
    edges = ring(nodes)
    assert len(edges) == len(nodes)  # n
    assert ("d", "a") in _pairs(edges)


def test_star_edges_point_to_center():
    nodes = ["a", "b", "c", "d"]
    edges = star(nodes, center="a")
    assert len(edges) == len(nodes) - 1  # n-1
    assert _pairs(edges) == {("b", "a"), ("c", "a"), ("d", "a")}


def test_star_center_must_be_a_node():
    with pytest.raises(ValueError):
        star(["a", "b"], center="z")


def test_tree_binary_shape():
    nodes = ["r", "c1", "c2", "g1", "g2", "g3", "g4"]
    edges = tree(nodes, branching=2)
    assert len(edges) == len(nodes) - 1  # connected tree => n-1
    assert ("r", "c1") in _pairs(edges)
    assert ("r", "c2") in _pairs(edges)
    assert ("c1", "g1") in _pairs(edges)
    assert ("c2", "g4") in _pairs(edges)


def test_layered_edge_count_across_consecutive_layers():
    layers = [["a"], ["b", "c"], ["d"]]
    edges = layered(layers)
    # 1*2 + 2*1 = 4
    assert len(edges) == 4
    assert ("a", "b") in _pairs(edges)
    assert ("c", "d") in _pairs(edges)


def test_sparse_is_low_density():
    nodes = ["a", "b", "c", "d"]
    edges = sparse(nodes, neighbors=1)
    assert len(edges) == len(nodes)  # ring-like with neighbors=1
    # much fewer than fully-connected (12)
    assert len(edges) < len(fully_connected(nodes))


def test_bipartite_edge_count_across_partition():
    set_a = ["a1", "a2"]
    set_b = ["b1", "b2", "b3"]
    edges = bipartite(set_a, set_b)
    assert len(edges) == len(set_a) * len(set_b)  # 2*3 = 6
    assert all(e.source in set_a and e.target in set_b for e in edges)


def test_build_topology_structured_network_sets_pattern():
    topo = build_topology("chain", ["a", "b", "c"])
    assert topo.structure == "structured_network"
    assert topo.pattern == "chain"
    assert len(topo.edges) == 2


def test_build_topology_layered_and_bipartite_keyword_forms():
    layered_topo = build_topology("layered", [], layers=[["a"], ["b", "c"]])
    assert layered_topo.pattern == "layered"
    assert len(layered_topo.edges) == 2

    bip_topo = build_topology("bipartite", [], set_a=["a"], set_b=["b", "c"])
    assert bip_topo.pattern == "bipartite"
    assert len(bip_topo.edges) == 2


def test_fully_connected_topology_structure():
    topo = fully_connected_topology(["a", "b", "c"])
    assert topo.structure == "fully_connected"
    assert topo.pattern is None
    assert len(topo.edges) == 6


def test_build_topology_unknown_pattern_raises():
    with pytest.raises(ValueError):
        build_topology("mystery", ["a", "b"])


# ---------------------------------------------------------------------------
# Role definitions
# ---------------------------------------------------------------------------


def test_roles_expose_six_roles_with_icons():
    roles = list_roles()
    assert len(roles) == 6
    catalog_keys = {
        v.key for v in catalog.get_subdimension("participants", "roles").values
    }
    assert {r.key for r in roles} == catalog_keys
    for role in roles:
        assert role.icon  # every role has an icon ref
        assert role.icon.startswith("role/")


# ---------------------------------------------------------------------------
# Gold cases: construction / validation
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("key", sorted(gold_cases().keys()))
def test_each_gold_case_constructs_and_validates(key):
    cfg = gold_cases()[key]()
    assert isinstance(cfg, MADConfig)
    # re-validate via model_validate on the dumped form
    revalidated = MADConfig.model_validate(cfg.model_dump())
    assert revalidated.name == cfg.name


def test_gold_cases_return_fresh_instances():
    a = re_binary_debate()
    b = re_binary_debate()
    assert a is not b
    assert a.id != b.id  # fresh uuids


# ---------------------------------------------------------------------------
# RE binary debate specifics
# ---------------------------------------------------------------------------


def test_re_binary_judge_authority_has_judge_node():
    cfg = re_binary_debate()
    assert cfg.agreement.authority == "judge_based"
    assert any("judge" in n.roles for n in cfg.participants.nodes)


def test_re_binary_output_schema_constrains_class_to_f_nf():
    cfg = re_binary_debate()
    schema = cfg.agreement.output_schema
    assert schema is not None
    assert schema["properties"]["class"]["enum"] == ["F", "NF"]


def test_re_binary_input_template_has_requirement_placeholder():
    cfg = re_binary_debate()
    assert "{{requirement}}" in cfg.input_spec.template
    assert "requirement" in cfg.input_spec.placeholders
    assert any(f.key == "requirement" for f in cfg.input_spec.ad_hoc_fields)


def test_re_binary_topology_is_fully_connected():
    cfg = re_binary_debate()
    assert cfg.interaction.topology.structure == "fully_connected"
    # 3 nodes => 6 directed edges
    assert len(cfg.interaction.topology.edges) == 6
    assert cfg.interaction.protocol.mechanism == "sequential"


# ---------------------------------------------------------------------------
# ChatEval S1/S2/S3: differ ONLY in documented attributes (Req 4.4)
# ---------------------------------------------------------------------------


def test_chateval_three_debaters_distinct_personalities():
    for factory in (chateval_s1, chateval_s2, chateval_s3):
        cfg = factory()
        debaters = [n for n in cfg.participants.nodes if "debater" in n.roles]
        assert len(debaters) == 3
        personalities = [d.persona.personality for d in debaters]
        assert all(p and p.strip() for p in personalities)
        assert len(set(personalities)) == 3  # distinct
        assert cfg.participants.persona_heterogeneity == "heterogeneous"
        assert cfg.participants.persona_assignment == "manual"


def test_chateval_edge_counts_per_table_3():
    assert len([e for e in chateval_s1().interaction.topology.edges]) == 6
    assert len([e for e in chateval_s2().interaction.topology.edges]) == 6
    # S3: 6 among debaters + 3 debater->summarizer = 9
    assert len([e for e in chateval_s3().interaction.topology.edges]) == 9


def test_chateval_s3_has_summarizer_with_inbound_edges():
    cfg = chateval_s3()
    summarizers = [n for n in cfg.participants.nodes if "summarizer" in n.roles]
    assert len(summarizers) == 1
    summ_id = summarizers[0].id
    inbound = [e for e in cfg.interaction.topology.edges if e.target == summ_id]
    assert len(inbound) == 3  # one from each debater


def _shared_attribute_view(cfg: MADConfig) -> dict:
    """Project a config down to the attributes S1/S2/S3 are supposed to SHARE.

    Excludes the documented differentiators (protocol mechanism/order/phases,
    the summarizer node, the summarizer edges, and content strategy).
    """
    debaters = sorted(
        (n for n in cfg.participants.nodes if "debater" in n.roles),
        key=lambda n: n.id,
    )
    return {
        "persona_heterogeneity": cfg.participants.persona_heterogeneity,
        "persona_assignment": cfg.participants.persona_assignment,
        "base_model_heterogeneity": cfg.participants.base_model_heterogeneity,
        "debaters": [
            (n.id, n.label, n.persona.personality, n.base_model.model_key)
            for n in debaters
        ],
        "topology_adaptability": cfg.interaction.topology.adaptability,
        "topology_structure": cfg.interaction.topology.structure,
        "format_syntax": cfg.interaction.format.syntax,
        "memory": cfg.interaction.format.memory,
        "max_rounds": cfg.interaction.protocol.max_rounds,
        "authority": cfg.agreement.authority,
        "resolution": cfg.agreement.resolution,
        "resolution_params": cfg.agreement.resolution_params,
    }


def test_s1_s2_s3_share_all_non_differentiating_attributes():
    s1, s2, s3 = chateval_s1(), chateval_s2(), chateval_s3()
    v1, v2, v3 = (
        _shared_attribute_view(s1),
        _shared_attribute_view(s2),
        _shared_attribute_view(s3),
    )
    assert v1 == v2 == v3


def test_s1_s2_differ_only_in_protocol_mechanism():
    """S1 vs S2: same nodes, same topology, same content — only mechanism flips."""
    s1, s2 = chateval_s1(), chateval_s2()
    assert s1.interaction.protocol.mechanism == "sequential"
    assert s2.interaction.protocol.mechanism == "simultaneous"
    # identical topology edges (as sets of pairs)
    assert _pairs(s1.interaction.topology.edges) == _pairs(
        s2.interaction.topology.edges
    )
    # identical content strategy
    assert (
        s1.interaction.format.content.strategy
        == s2.interaction.format.content.strategy
        == "verbatim"
    )
    # S1 carries an explicit order; S2 (simultaneous) does not
    assert s1.interaction.protocol.order == ["alice", "bob", "carol"]


def test_s2_s3_differ_only_in_documented_attributes():
    """S2 vs S3: the ONLY deltas are the summarizer node, its edges, and content.

    (Protocol mechanism differs structurally — S3 adds a summarizer phase — but
    the debater-level simultaneity is preserved; the documented differentiators
    are: + Summarizer node, + 3 debater->summarizer edges, content strategy.)
    """
    s2, s3 = chateval_s2(), chateval_s3()

    # delta 1: summarizer node present only in S3
    s2_summ = [n for n in s2.participants.nodes if "summarizer" in n.roles]
    s3_summ = [n for n in s3.participants.nodes if "summarizer" in n.roles]
    assert s2_summ == []
    assert len(s3_summ) == 1

    # debater set is identical
    s2_deb = {n.id for n in s2.participants.nodes if "debater" in n.roles}
    s3_deb = {n.id for n in s3.participants.nodes if "debater" in n.roles}
    assert s2_deb == s3_deb

    # delta 2: debater->summarizer edges only in S3; debater-debater edges equal
    summ_id = s3_summ[0].id
    s3_debater_edges = {
        (e.source, e.target)
        for e in s3.interaction.topology.edges
        if e.target != summ_id
    }
    assert s3_debater_edges == _pairs(s2.interaction.topology.edges)
    s3_summ_edges = [e for e in s3.interaction.topology.edges if e.target == summ_id]
    assert len(s3_summ_edges) == 3

    # delta 3: content strategy
    assert s2.interaction.format.content.strategy == "verbatim"
    assert s3.interaction.format.content.strategy == "summarized"


# ---------------------------------------------------------------------------
# Export / import round-trip (version.py)
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("key", sorted(gold_cases().keys()))
def test_gold_case_export_import_round_trip(key):
    cfg = gold_cases()[key]()
    reloaded = import_config(export_config(cfg))
    assert reloaded == cfg
