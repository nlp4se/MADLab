"""Unit tests for the MAD Configuration Artifact schema (Pydantic v2).

These cover: a minimal valid config, defaults filling, each cross-field
semantic validator (rejecting invalid configs with the right message and
accepting valid ones), the under-development gating hook, model_dump/
model_validate round-trip stability, and the UI-friendly field-error helper.

They depend only on pydantic + the ``mad`` package.
"""

import pytest
from pydantic import ValidationError

from mad.taxonomy import catalog
from mad.taxonomy.schema import (
    SCHEMA_VERSION,
    MADConfig,
    validation_error_to_fields,
)


# ---------------------------------------------------------------------------
# Builders
# ---------------------------------------------------------------------------


def _minimal_config(**overrides) -> MADConfig:
    """A minimal valid config: one debater node + minimal input_spec."""
    data = {
        "name": "Minimal",
        "participants": {
            "nodes": [{"id": "alice", "label": "Alice", "roles": ["debater"]}]
        },
        "input_spec": {"template": "Classify {{x}}", "placeholders": ["x"]},
    }
    data.update(overrides)
    return MADConfig.model_validate(data)


# ---------------------------------------------------------------------------
# Minimal valid + defaults
# ---------------------------------------------------------------------------


def test_minimal_config_validates():
    cfg = _minimal_config()
    assert cfg.name == "Minimal"
    assert cfg.schema_version == SCHEMA_VERSION == "1.0"
    assert cfg.id  # uuid auto-generated
    assert len(cfg.participants.nodes) == 1


def test_defaults_fill_from_name_and_one_node():
    cfg = MADConfig.model_validate(
        {
            "name": "Defaults",
            "participants": {"nodes": [{"id": "n1", "label": "N1"}]},
        }
    )
    # participant defaults
    node = cfg.participants.nodes[0]
    assert node.roles == ["debater"]
    assert node.base_model.family == "closed_weight"
    assert node.base_model.temperature == 0.0
    assert node.persona.background is None
    # interaction defaults
    assert cfg.interaction.topology.structure == "fully_connected"
    assert cfg.interaction.topology.adaptability == "static"
    assert cfg.interaction.protocol.mechanism == "sequential"
    assert cfg.interaction.protocol.max_rounds == 1
    assert cfg.interaction.format.syntax == "natural_language"
    assert cfg.interaction.format.content.strategy == "verbatim"
    assert cfg.interaction.format.memory == "short_term"
    # agreement defaults
    assert cfg.agreement.authority == "collective"
    assert cfg.agreement.resolution == "majority_vote"
    # under-development hook: all defaults are executable
    assert cfg.under_development_values() == []


def test_unknown_field_rejected():
    with pytest.raises(ValidationError):
        MADConfig.model_validate({"name": "X", "bogus": 1})


# ---------------------------------------------------------------------------
# Validator 1: edge endpoints reference existing nodes
# ---------------------------------------------------------------------------


def test_edge_endpoints_accepts_valid():
    cfg = _minimal_config(
        participants={
            "nodes": [
                {"id": "alice", "label": "Alice"},
                {"id": "bob", "label": "Bob"},
            ]
        },
        interaction={
            "topology": {"edges": [{"source": "alice", "target": "bob"}]}
        },
    )
    assert cfg.interaction.topology.edges[0].target == "bob"


def test_edge_source_must_exist():
    with pytest.raises(ValidationError) as exc:
        _minimal_config(
            interaction={
                "topology": {"edges": [{"source": "ghost", "target": "alice"}]}
            }
        )
    assert "edge source 'ghost'" in str(exc.value)


def test_edge_target_must_exist():
    with pytest.raises(ValidationError) as exc:
        _minimal_config(
            interaction={
                "topology": {"edges": [{"source": "alice", "target": "ghost"}]}
            }
        )
    assert "edge target 'ghost'" in str(exc.value)


# ---------------------------------------------------------------------------
# Validator 2: order / phase participant refs
# ---------------------------------------------------------------------------


def test_protocol_order_refs_must_exist():
    with pytest.raises(ValidationError) as exc:
        _minimal_config(
            interaction={"protocol": {"order": ["alice", "ghost"]}}
        )
    assert "protocol order entry 'ghost'" in str(exc.value)


def test_phase_participant_refs_must_exist():
    with pytest.raises(ValidationError) as exc:
        _minimal_config(
            interaction={
                "protocol": {
                    "mechanism": "hybrid",
                    "phases": [
                        {"mechanism": "sequential", "participants": ["ghost"]}
                    ],
                }
            }
        )
    assert "phase 0 participant 'ghost'" in str(exc.value)


def test_protocol_order_valid_accepted():
    cfg = _minimal_config(interaction={"protocol": {"order": ["alice"]}})
    assert cfg.interaction.protocol.order == ["alice"]


# ---------------------------------------------------------------------------
# Validator 3: group refs
# ---------------------------------------------------------------------------


def test_node_group_must_exist():
    with pytest.raises(ValidationError) as exc:
        _minimal_config(
            participants={
                "nodes": [
                    {"id": "alice", "label": "Alice", "group": "g1"}
                ],
            }
        )
    assert "references group 'g1'" in str(exc.value)


def test_node_group_valid_accepted():
    cfg = _minimal_config(
        participants={
            "nodes": [{"id": "alice", "label": "Alice", "group": "g1"}],
            "groups": [{"id": "g1", "label": "Team A"}],
        }
    )
    assert cfg.participants.nodes[0].group == "g1"


# ---------------------------------------------------------------------------
# Validator 4: judge-based authority needs a judge
# ---------------------------------------------------------------------------


def test_judge_based_requires_judge_role():
    with pytest.raises(ValidationError) as exc:
        _minimal_config(agreement={"authority": "judge_based"})
    assert "judge_based authority requires at least one node with the 'judge' role" in str(
        exc.value
    )


def test_judge_based_accepts_judge_node():
    cfg = _minimal_config(
        participants={
            "nodes": [
                {"id": "alice", "label": "Alice", "roles": ["debater"]},
                {"id": "jury", "label": "Jury", "roles": ["judge"]},
            ]
        },
        agreement={"authority": "judge_based"},
    )
    assert cfg.agreement.authority == "judge_based"


# ---------------------------------------------------------------------------
# Validator: Start/End IO connections (topology.entry_nodes / exit_nodes)
# ---------------------------------------------------------------------------

_IO_NODES = {
    "nodes": [
        {"id": "alice", "label": "Alice", "roles": ["debater"]},
        {"id": "bob", "label": "Bob", "roles": ["debater"]},
        {"id": "jury", "label": "Jury", "roles": ["judge"]},
    ]
}


def test_io_nodes_default_to_none():
    cfg = _minimal_config()
    assert cfg.interaction.topology.entry_nodes is None
    assert cfg.interaction.topology.exit_nodes is None


def test_io_nodes_accept_existing_ids_and_round_trip():
    cfg = _minimal_config(
        participants=_IO_NODES,
        interaction={"topology": {"entry_nodes": ["alice"], "exit_nodes": ["bob"]}},
    )
    assert cfg.interaction.topology.entry_nodes == ["alice"]
    again = MADConfig.model_validate(cfg.model_dump())
    assert again.interaction.topology.exit_nodes == ["bob"]


@pytest.mark.parametrize("field", ["entry_nodes", "exit_nodes"])
def test_io_nodes_must_reference_existing_nodes(field):
    with pytest.raises(ValidationError) as exc:
        _minimal_config(
            participants=_IO_NODES,
            interaction={"topology": {field: ["alice", "ghost"]}},
        )
    assert f"{field} entry 'ghost' does not reference an existing participant node" in str(
        exc.value
    )


@pytest.mark.parametrize("field", ["entry_nodes", "exit_nodes"])
def test_io_nodes_must_be_non_empty_when_set(field):
    with pytest.raises(ValidationError) as exc:
        _minimal_config(participants=_IO_NODES, interaction={"topology": {field: []}})
    assert f"interaction.topology.{field} must be non-empty" in str(exc.value)


def test_judge_based_exit_nodes_must_include_a_judge():
    with pytest.raises(ValidationError) as exc:
        _minimal_config(
            participants=_IO_NODES,
            interaction={"topology": {"exit_nodes": ["alice", "bob"]}},
            agreement={"authority": "judge_based"},
        )
    assert "exit_nodes to include at least one node with the 'judge' role" in str(
        exc.value
    )
    cfg = _minimal_config(
        participants=_IO_NODES,
        interaction={"topology": {"exit_nodes": ["alice", "jury"]}},
        agreement={"authority": "judge_based"},
    )
    assert cfg.interaction.topology.exit_nodes == ["alice", "jury"]


def test_io_node_error_surfaces_as_field_error():
    with pytest.raises(ValidationError) as exc:
        _minimal_config(participants=_IO_NODES, interaction={"topology": {"exit_nodes": []}})
    fields = validation_error_to_fields(exc.value)
    assert any("exit_nodes must be non-empty" in f["message"] for f in fields)


# ---------------------------------------------------------------------------
# Validator 5: weighted_vote / scoring require resolution_params
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("resolution", ["weighted_vote", "scoring"])
def test_weighted_scoring_require_params(resolution):
    with pytest.raises(ValidationError) as exc:
        _minimal_config(agreement={"resolution": resolution})
    assert f"resolution '{resolution}' requires non-empty resolution_params" in str(
        exc.value
    )


def test_weighted_vote_with_params_accepted():
    cfg = _minimal_config(
        agreement={
            "resolution": "weighted_vote",
            "resolution_params": {"weights": {"alice": 1.0}},
        }
    )
    assert cfg.agreement.resolution == "weighted_vote"


# ---------------------------------------------------------------------------
# Validator 6: structured_network requires a pattern
# ---------------------------------------------------------------------------


def test_structured_network_requires_pattern():
    with pytest.raises(ValidationError) as exc:
        _minimal_config(
            interaction={"topology": {"structure": "structured_network"}}
        )
    assert "structured_network topology requires a 'pattern'" in str(exc.value)


def test_structured_network_with_pattern_accepted():
    cfg = _minimal_config(
        interaction={
            "topology": {"structure": "structured_network", "pattern": "chain"}
        }
    )
    assert cfg.interaction.topology.pattern == "chain"


# ---------------------------------------------------------------------------
# Validator 7: unique node / group ids
# ---------------------------------------------------------------------------


def test_duplicate_node_ids_rejected():
    with pytest.raises(ValidationError) as exc:
        _minimal_config(
            participants={
                "nodes": [
                    {"id": "alice", "label": "A1"},
                    {"id": "alice", "label": "A2"},
                ]
            }
        )
    assert "node ids must be unique" in str(exc.value)


def test_duplicate_group_ids_rejected():
    with pytest.raises(ValidationError) as exc:
        _minimal_config(
            participants={
                "nodes": [{"id": "alice", "label": "A"}],
                "groups": [
                    {"id": "g1", "label": "A"},
                    {"id": "g1", "label": "B"},
                ],
            }
        )
    assert "group ids must be unique" in str(exc.value)


# ---------------------------------------------------------------------------
# Validator 8: role entries validity
# ---------------------------------------------------------------------------


def test_unknown_role_rejected():
    with pytest.raises(ValidationError) as exc:
        _minimal_config(
            participants={
                "nodes": [{"id": "alice", "label": "A", "roles": ["wizard"]}]
            }
        )
    assert "role 'wizard' is not a known role" in str(exc.value)


def test_catalog_roles_accepted():
    role_keys = sorted(
        v.key for v in catalog.get_subdimension("participants", "roles").values
    )
    cfg = _minimal_config(
        participants={
            "nodes": [{"id": "alice", "label": "A", "roles": role_keys}]
        }
    )
    assert cfg.participants.nodes[0].roles == role_keys


def test_custom_role_prefix_accepted():
    cfg = _minimal_config(
        participants={
            "nodes": [
                {"id": "alice", "label": "A", "roles": ["custom:devil_advocate"]}
            ]
        }
    )
    assert cfg.participants.nodes[0].roles == ["custom:devil_advocate"]


def test_empty_custom_role_rejected():
    with pytest.raises(ValidationError) as exc:
        _minimal_config(
            participants={
                "nodes": [{"id": "alice", "label": "A", "roles": ["custom:"]}]
            }
        )
    assert "must have a non-empty name" in str(exc.value)


# ---------------------------------------------------------------------------
# metadata signals validity
# ---------------------------------------------------------------------------


def test_unknown_metadata_signal_rejected():
    with pytest.raises(ValidationError) as exc:
        _minimal_config(
            interaction={
                "format": {"content": {"metadata_signals": ["bogus"]}}
            }
        )
    assert "unknown metadata signal" in str(exc.value)


def test_known_metadata_signals_accepted():
    cfg = _minimal_config(
        interaction={
            "format": {
                "content": {"metadata_signals": ["confidence", "uncertainty"]}
            }
        }
    )
    assert cfg.interaction.format.content.metadata_signals == [
        "confidence",
        "uncertainty",
    ]


# ---------------------------------------------------------------------------
# max_rounds constraint
# ---------------------------------------------------------------------------


def test_max_rounds_must_be_at_least_one():
    with pytest.raises(ValidationError):
        _minimal_config(interaction={"protocol": {"max_rounds": 0}})


# ---------------------------------------------------------------------------
# under_development_values() gating hook
# ---------------------------------------------------------------------------


def test_under_development_values_for_dynamic_and_embeddings():
    cfg = _minimal_config(
        interaction={
            "topology": {"adaptability": "dynamic"},
            "format": {"syntax": "embeddings"},
        }
    )
    uds = cfg.under_development_values()
    assert "dynamic" in uds
    assert "embeddings" in uds
    # executable defaults must NOT appear
    assert "static" not in uds
    assert "natural_language" not in uds


def test_under_development_values_collects_all_nonexecutable():
    cfg = _minimal_config(
        participants={
            "nodes": [{"id": "alice", "label": "A"}],
            "persona_assignment": "automatic",
        },
        interaction={
            "topology": {"adaptability": "dynamic"},
            "protocol": {"ordering": "coordinator"},
            "format": {
                "syntax": "embeddings",
                "content": {"strategy": "other"},
                "memory": "long_term",
            },
        },
    )
    uds = set(cfg.under_development_values())
    assert {
        "automatic",
        "dynamic",
        "coordinator",
        "embeddings",
        "other",
        "long_term",
    } <= uds


def test_under_development_values_empty_for_executable_config():
    assert _minimal_config().under_development_values() == []


# ---------------------------------------------------------------------------
# Round-trip stability
# ---------------------------------------------------------------------------


def test_model_dump_validate_round_trip():
    cfg = _minimal_config(
        participants={
            "nodes": [
                {"id": "alice", "label": "Alice", "roles": ["debater"]},
                {"id": "jury", "label": "Jury", "roles": ["judge"]},
            ],
            "groups": [{"id": "g1", "label": "Team A", "color": "#fff"}],
        },
        interaction={
            "topology": {"edges": [{"source": "alice", "target": "jury"}]},
            "protocol": {"order": ["alice", "jury"]},
        },
        agreement={"authority": "judge_based"},
    )
    dumped = cfg.model_dump()
    reloaded = MADConfig.model_validate(dumped)
    assert reloaded.model_dump() == dumped
    assert reloaded == cfg


def test_round_trip_json_mode():
    cfg = _minimal_config()
    dumped = cfg.model_dump(mode="json")
    reloaded = MADConfig.model_validate(dumped)
    assert reloaded.model_dump(mode="json") == dumped


# ---------------------------------------------------------------------------
# field-error helper
# ---------------------------------------------------------------------------


def test_validation_error_to_fields_shape():
    with pytest.raises(ValidationError) as exc:
        MADConfig.model_validate({"name": "X", "bogus": 1})
    fields = validation_error_to_fields(exc.value)
    assert isinstance(fields, list)
    assert all(set(f.keys()) == {"field", "message"} for f in fields)
    assert any("bogus" in f["field"] for f in fields)


def test_validation_error_to_fields_nested_path():
    with pytest.raises(ValidationError) as exc:
        _minimal_config(
            participants={
                "nodes": [{"id": "alice", "label": "A", "roles": ["wizard"]}]
            }
        )
    fields = validation_error_to_fields(exc.value)
    # custom model_validator message is carried through
    assert any("role 'wizard' is not a known role" in f["message"] for f in fields)
