"""Unit tests for the data-driven MAD taxonomy catalog.

These tests assert the structural invariants of the catalog (all dimensions and
sub-dimensions present, unique keys, exactly one default per single-select
sub-dimension), the correct "under development" flagging of non-executable
values, JSON-ready serialization, and the accessor helpers.

They depend only on the standard library + the ``mad`` package, so they run
without any third-party backend dependencies installed.
"""

import json

import pytest

from mad.taxonomy import catalog


# --- Structure: dimensions and sub-dimensions present ----------------------

EXPECTED_STRUCTURE = {
    "participants": {
        "persona_attributes": "attributes",
        "persona_heterogeneity": "single",
        "persona_assignment": "single",
        "roles": "multi",
        "base_model_family": "single",
        "base_model_heterogeneity": "single",
    },
    "interaction": {
        "topology_adaptability": "single",
        "topology_structure": "single",
        "topology_pattern": "single",
        "protocol_mechanism": "single",
        "protocol_ordering": "single",
        "format_syntax": "single",
        "format_content": "single",
        "format_content_metadata": "multi",
        "format_memory": "single",
    },
    "agreement": {
        "authority": "single",
        "resolution": "single",
    },
}


def test_three_dimensions_present_in_order():
    keys = [dim.key for dim in catalog.list_dimensions()]
    assert keys == ["participants", "interaction", "agreement"]


@pytest.mark.parametrize(
    "dimension_key,subdimension_key,selection",
    [
        (dim, sub, sel)
        for dim, subs in EXPECTED_STRUCTURE.items()
        for sub, sel in subs.items()
    ],
)
def test_subdimension_present_with_selection(dimension_key, subdimension_key, selection):
    sub = catalog.get_subdimension(dimension_key, subdimension_key)
    assert sub is not None, f"missing {dimension_key}.{subdimension_key}"
    assert sub.selection == selection


def test_no_unexpected_subdimensions():
    for dim in catalog.list_dimensions():
        expected = set(EXPECTED_STRUCTURE[dim.key])
        actual = {sub.key for sub in dim.subdimensions}
        assert actual == expected, f"{dim.key} sub-dimensions mismatch"


def test_every_subdimension_has_values():
    for _, sub, _ in _iter_once():
        pass
    for dim in catalog.list_dimensions():
        for sub in dim.subdimensions:
            assert sub.values, f"{dim.key}.{sub.key} has no values"


def _iter_once():
    # helper to exercise iter_values without failing on empty
    return list(catalog.iter_values())


# --- Defaults: exactly one per single-select sub-dimension -----------------


# Single-select sub-dimensions that intentionally have NO default because the
# value is only meaningful in a specific context and is nullable in the
# artifact (a topology pattern is chosen only for a structured network; there
# is no "dominant" pattern to default to).
OPTIONAL_SINGLE_SELECT = {("interaction", "topology_pattern")}


def test_at_most_one_default_per_single_select():
    for dim in catalog.list_dimensions():
        for sub in dim.subdimensions:
            default_count = sum(1 for v in sub.values if v.default)
            if sub.selection == "single":
                if (dim.key, sub.key) in OPTIONAL_SINGLE_SELECT:
                    assert default_count == 0, (
                        f"{dim.key}.{sub.key} is optional and must have no "
                        f"default, got {default_count}"
                    )
                else:
                    assert default_count == 1, (
                        f"{dim.key}.{sub.key} must have exactly one default, "
                        f"got {default_count}"
                    )
            else:
                # multi / attributes: at most one value may be flagged default
                # (e.g. roles flags `debater` so a fresh node starts sensibly).
                assert default_count <= 1, (
                    f"{dim.key}.{sub.key} ({sub.selection}) must have at most "
                    f"one default, got {default_count}"
                )


def test_default_accessor_matches_flag():
    for dim in catalog.list_dimensions():
        for sub in dim.subdimensions:
            if sub.selection == "single" and (dim.key, sub.key) not in OPTIONAL_SINGLE_SELECT:
                assert sub.default is not None
                assert sub.default.default is True


@pytest.mark.parametrize(
    "dimension_key,subdimension_key,expected_default",
    [
        ("participants", "persona_heterogeneity", "homogeneous"),
        ("participants", "persona_assignment", "unspecified"),
        ("participants", "base_model_family", "closed_weight"),
        ("participants", "base_model_heterogeneity", "homogeneous"),
        ("interaction", "topology_adaptability", "static"),
        ("interaction", "topology_structure", "fully_connected"),
        ("interaction", "protocol_mechanism", "sequential"),
        ("interaction", "protocol_ordering", "fixed"),
        ("interaction", "format_syntax", "natural_language"),
        ("interaction", "format_content", "verbatim"),
        ("interaction", "format_memory", "short_term"),
        ("agreement", "authority", "collective"),
        ("agreement", "resolution", "majority_vote"),
    ],
)
def test_specific_defaults(dimension_key, subdimension_key, expected_default):
    default = catalog.default_value(dimension_key, subdimension_key)
    assert default is not None
    assert default.key == expected_default


def test_roles_debater_is_default_despite_multi_select():
    # Roles is multi-select; the paper's dominant role (debater) is still
    # marked default so a brand-new node starts as a debater.
    roles = catalog.get_subdimension("participants", "roles")
    debater = roles.get("debater")
    assert debater is not None and debater.default is True
    # but no other role is default
    assert sum(1 for v in roles.values if v.default) == 1


# --- Unique keys -----------------------------------------------------------


def test_keys_unique_within_each_subdimension():
    for dim in catalog.list_dimensions():
        for sub in dim.subdimensions:
            keys = [v.key for v in sub.values]
            assert len(keys) == len(set(keys)), f"duplicate keys in {dim.key}.{sub.key}"


def test_subdimension_keys_unique_within_dimension():
    for dim in catalog.list_dimensions():
        keys = [sub.key for sub in dim.subdimensions]
        assert len(keys) == len(set(keys)), f"duplicate sub-dimension keys in {dim.key}"


def test_all_keys_snake_case():
    import re

    pattern = re.compile(r"^[a-z][a-z0-9_]*$")
    for dim in catalog.list_dimensions():
        assert pattern.match(dim.key), dim.key
        for sub in dim.subdimensions:
            assert pattern.match(sub.key), sub.key
            for value in sub.values:
                assert pattern.match(value.key), f"{sub.key}.{value.key}"


# --- Executable flags ------------------------------------------------------

# Fully-qualified (subdimension_key, value_key) pairs for the non-executable
# values. Qualified because value keys are only unique *within* a sub-dimension:
# `other` exists under both format_content (under-dev) and authority (executable).
EXPECTED_UNDER_DEVELOPMENT = {
    ("persona_assignment", "automatic"),
    ("topology_adaptability", "dynamic"),
    ("protocol_ordering", "coordinator"),
    ("format_syntax", "embeddings"),
    ("format_content", "other"),
    ("format_memory", "long_term"),
    ("format_memory", "knowledge_retrieval"),
    ("format_memory", "parametric"),
}


def test_under_development_values_exactly_match_expected():
    actual = {
        (sub.key, value.key)
        for _, sub, value in catalog.iter_values()
        if not value.executable
    }
    assert actual == EXPECTED_UNDER_DEVELOPMENT


def test_under_development_keys_helper_lists_them():
    # The convenience helper returns bare keys; it must contain each
    # under-development value's key.
    keys = catalog.under_development_keys()
    for _, value_key in EXPECTED_UNDER_DEVELOPMENT:
        assert value_key in keys


def test_all_other_values_are_executable():
    for _, sub, value in catalog.iter_values():
        if (sub.key, value.key) in EXPECTED_UNDER_DEVELOPMENT:
            assert value.executable is False, f"{sub.key}.{value.key} should be under-dev"
        else:
            assert value.executable is True, f"{sub.key}.{value.key} should be executable"


# --- Icons -----------------------------------------------------------------


def test_roles_and_topology_patterns_have_icons():
    roles = catalog.get_subdimension("participants", "roles")
    for value in roles.values:
        assert value.icon is not None and value.icon.startswith("role/")

    patterns = catalog.get_subdimension("interaction", "topology_pattern")
    for value in patterns.values:
        assert value.icon is not None and value.icon.startswith("topology/")


def test_non_icon_values_have_no_icon():
    for _, sub, value in catalog.iter_values():
        if sub.key not in {"roles", "topology_pattern"}:
            assert value.icon is None, f"{sub.key}.{value.key} unexpectedly has an icon"


# --- Content spot checks (paper alignment) ---------------------------------


def test_persona_attribute_families():
    attrs = catalog.get_subdimension("participants", "persona_attributes")
    assert [v.key for v in attrs.values] == ["background", "personality", "stance"]
    assert attrs.selection == "attributes"


def test_six_roles_present():
    roles = catalog.get_subdimension("participants", "roles")
    assert {v.key for v in roles.values} == {
        "debater",
        "judge",
        "summarizer",
        "leader",
        "verifier",
        "editor",
    }


def test_seven_topology_patterns_present():
    patterns = catalog.get_subdimension("interaction", "topology_pattern")
    assert {v.key for v in patterns.values} == {
        "chain",
        "ring",
        "star",
        "tree",
        "layered",
        "sparse",
        "bipartite",
    }


def test_six_metadata_signals_present():
    meta = catalog.get_subdimension("interaction", "format_content_metadata")
    assert {v.key for v in meta.values} == {
        "confidence",
        "uncertainty",
        "verifier_score",
        "judge_likelihood",
        "bias_quality",
        "guideline_weight",
    }
    assert meta.selection == "multi"


def test_resolution_strategies_present():
    res = catalog.get_subdimension("agreement", "resolution")
    assert {v.key for v in res.values} == {
        "majority_vote",
        "argument_evaluation",
        "weighted_vote",
        "scoring",
        "average",
        "consensus",
    }


# --- Accessor helpers ------------------------------------------------------


def test_get_value_round_trip():
    value = catalog.get_value("interaction", "topology_pattern", "sparse")
    assert value is not None
    assert value.label == "Sparse"
    assert value.icon == "topology/sparse"


def test_get_value_missing_returns_none():
    assert catalog.get_value("participants", "roles", "nonexistent") is None
    assert catalog.get_value("participants", "nonexistent", "debater") is None
    assert catalog.get_value("nonexistent", "roles", "debater") is None


def test_get_dimension_and_subdimension():
    assert catalog.get_dimension("agreement").label == "Agreement"
    assert catalog.get_dimension("nope") is None
    assert catalog.get_subdimension("agreement", "authority").selection == "single"
    assert catalog.get_subdimension("agreement", "nope") is None


def test_iter_values_covers_everything():
    triples = list(catalog.iter_values())
    total = sum(
        len(sub.values)
        for dim in catalog.list_dimensions()
        for sub in dim.subdimensions
    )
    assert len(triples) == total
    # every triple is (Dimension, SubDimension, Value)
    for dim, sub, value in triples:
        assert isinstance(dim, catalog.Dimension)
        assert isinstance(sub, catalog.SubDimension)
        assert isinstance(value, catalog.Value)


def test_default_config_mapping():
    cfg = catalog.default_config()
    assert cfg["interaction"]["topology_structure"] == "fully_connected"
    assert cfg["agreement"]["resolution"] == "majority_vote"
    assert cfg["participants"]["base_model_family"] == "closed_weight"
    # multi / attributes sub-dimensions are not included
    assert "roles" not in cfg["participants"]
    assert "persona_attributes" not in cfg["participants"]
    assert "format_content_metadata" not in cfg["interaction"]


# --- Serialization ---------------------------------------------------------


def test_to_dict_is_json_serializable():
    data = catalog.to_dict()
    # Round-trips through json without error and preserves structure.
    text = json.dumps(data)
    restored = json.loads(text)
    assert restored == data


def test_to_dict_shape():
    data = catalog.to_dict()
    assert set(data.keys()) == {"dimensions"}
    assert len(data["dimensions"]) == 3

    participants = data["dimensions"][0]
    assert participants["key"] == "participants"
    assert "subdimensions" in participants

    roles = next(
        sub for sub in participants["subdimensions"] if sub["key"] == "roles"
    )
    assert roles["selection"] == "multi"
    debater = next(v for v in roles["values"] if v["key"] == "debater")
    assert set(debater.keys()) == {
        "key",
        "label",
        "description",
        "default",
        "executable",
        "icon",
    }
    assert debater["icon"] == "role/debater"
    assert debater["default"] is True
    assert debater["executable"] is True


def test_to_dict_contains_only_plain_types():
    def check(obj):
        if isinstance(obj, dict):
            for k, v in obj.items():
                assert isinstance(k, str)
                check(v)
        elif isinstance(obj, list):
            for item in obj:
                check(item)
        else:
            assert obj is None or isinstance(obj, (str, bool, int, float)), type(obj)

    check(catalog.to_dict())


# --- Immutability ----------------------------------------------------------


def test_values_are_frozen():
    value = catalog.get_value("agreement", "authority", "collective")
    with pytest.raises(Exception):
        value.key = "mutated"  # type: ignore[misc]
