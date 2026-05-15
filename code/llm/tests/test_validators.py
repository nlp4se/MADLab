""""
Hypothesis tests for FR-TOP and FR-PROT requirements.
Verifies that `validators.py` rejects invalid configurations
and accepts valid ones, without duplicating validation logic.
"""

import pytest
from hypothesis import given, strategies as st
from ..validators import validate_interaction_file
from .strategies import (
    assistant_ids,
    valid_interaction_config_list,
    valid_interaction_config_dict,
    MIN_ROUNDS,
)


def base_valid_config(assistants):
    """
    Creates a minimal valid configuration.
    Topology: every node points to every other node (no self-refs, no empty edges).
    Turns: one group containing all assistants (valid single-turn round).
    """
    topology = {a: [b for b in assistants if b != a] for a in assistants}
    return {
        "assistants": assistants,
        "topology": topology,
        "turns": [list(assistants)],
        "number_of_rounds": MIN_ROUNDS,
    }


# ---------------------------------------------------------------------------
# FR-TOP AC2: Required keys and correct types
# ---------------------------------------------------------------------------

@given(assistants=assistant_ids)
def test_missing_assistants_key(assistants):
    """[FR-TOP-AC2] Validates that missing 'assistants' key is rejected."""
    config = base_valid_config(assistants)
    del config["assistants"]
    with pytest.raises(ValueError, match="Missing mandatory attribute 'assistants'"):
        validate_interaction_file(config)


@given(assistants=assistant_ids)
def test_missing_topology_key(assistants):
    """[FR-TOP-AC2] Validates that missing 'topology' key is rejected."""
    config = base_valid_config(assistants)
    del config["topology"]
    with pytest.raises(ValueError, match="Missing mandatory attribute 'topology'"):
        validate_interaction_file(config)


@given(assistants=assistant_ids)
def test_missing_turns_key(assistants):
    """[FR-TOP-AC2] Validates that missing 'turns' key is rejected."""
    config = base_valid_config(assistants)
    del config["turns"]
    with pytest.raises(ValueError, match="Missing mandatory attribute 'turns'"):
        validate_interaction_file(config)


def test_assistants_not_list():
    """[FR-TOP-AC2] Validates that non-list 'assistants' is rejected."""
    config = {"assistants": "soy_string", "topology": {}, "turns": []}
    with pytest.raises(ValueError, match="'assistants' must be a list"):
        validate_interaction_file(config)


def test_topology_not_dict():
    """[FR-TOP-AC2] Validates that non-dict 'topology' is rejected."""
    config = {"assistants": [], "topology": "no_soy_dict", "turns": []}
    with pytest.raises(ValueError, match="'topology' must be a dictionary"):
        validate_interaction_file(config)


def test_turns_not_list_nor_dict():
    """[FR-TOP-AC2] Validates that 'turns' that is neither list nor dict is rejected."""
    config = {"assistants": [], "topology": {}, "turns": 123}
    with pytest.raises(ValueError, match="'turns' must be a list or a dictionary"):
        validate_interaction_file(config)


# ---------------------------------------------------------------------------
# FR-TOP AC3–AC6: Topology structure validation
# ---------------------------------------------------------------------------

@given(assistants=assistant_ids)
def test_topology_keys_must_match_assistants(assistants):
    """[FR-TOP-AC3] Validates that any mismatch between topology keys and assistants is rejected.

    This single test covers all key-set mismatch cases: empty topology,
    missing assistants, extra keys, and entirely foreign keys. All of them
    hit the same guard in validate_topology (topology_keys != assistants_set)
    and produce the same error, so one representative case is sufficient.
    """
    config = base_valid_config(assistants)
    config["topology"] = {"ghost": [assistants[0]]}
    with pytest.raises(ValueError, match="'topology' must contain exactly all assistants"):
        validate_interaction_file(config)


@given(assistants=assistant_ids)
def test_node_empty_edges_rejected(assistants):
    """[FR-TOP-AC3] Validates that a node with an empty edge list is rejected."""
    config = base_valid_config(assistants)
    config["topology"][assistants[0]] = []
    with pytest.raises(ValueError, match="must point to at least one node"):
        validate_interaction_file(config)


@given(assistants=assistant_ids)
def test_duplicate_targets_rejected(assistants):
    """[FR-TOP-AC5] Validates that duplicate edges for a node in topology are rejected."""
    config = base_valid_config(assistants)
    a, b = assistants[0], assistants[1]
    config["topology"][a] = [b, b]
    with pytest.raises(ValueError, match="Duplicate edges detected for node"):
        validate_interaction_file(config)


@given(assistants=assistant_ids)
def test_nonexistent_target_node(assistants):
    """[FR-TOP-AC4] Validates that a target node not in assistants is rejected."""
    config = base_valid_config(assistants)
    config["topology"][assistants[0]] = ["ghost"]
    with pytest.raises(ValueError, match="Target node 'ghost'.*does not exist"):
        validate_interaction_file(config)


@given(assistants=assistant_ids)
def test_self_reference_rejected(assistants):
    """[FR-TOP-AC6] Validates that self-referencing topology edges are rejected.

    Distinct from test_nonexistent_target_node: a self-ref target IS in
    assistants_set, so it passes the 'does not exist' check and only fails
    the dedicated self-reference guard, producing a different error message.
    """
    config = base_valid_config(assistants)
    config["topology"][assistants[0]] = [assistants[0]]
    with pytest.raises(ValueError, match="cannot point to itself"):
        validate_interaction_file(config)


# ---------------------------------------------------------------------------
# FR-PROT AC2–AC6: Turns / rounds structure validation
# ---------------------------------------------------------------------------

# ---------------------------------------------------------------------------
# FR-PROT: LIST branch
# ---------------------------------------------------------------------------

def base_valid_config_list(assistants):
    """Valid config with turns as a list."""
    return {
        "assistants": assistants,
        "topology": {a: [b for b in assistants if b != a] for a in assistants},
        "turns": [list(assistants)],
        "number_of_rounds": MIN_ROUNDS,
    }


def base_valid_config_dict(assistants):
    """Valid config with turns as a dict."""
    return {
        "assistants": assistants,
        "topology": {a: [b for b in assistants if b != a] for a in assistants},
        "turns": {"0": [list(assistants)]},
    }

@given(assistants=assistant_ids)
def test_list_turns_requires_number_of_rounds(assistants):
    """[FR-PROT-AC2] Hits: 'number_of_rounds' not in interaction_config."""
    config = base_valid_config_list(assistants)
    del config["number_of_rounds"]
    with pytest.raises(ValueError, match="'number_of_rounds' must be specified"):
        validate_interaction_file(config)


@given(
    assistants=assistant_ids,
    bad_rounds=st.one_of(
        st.integers(min_value=-5, max_value=0),  # int but ≤ 0
        st.just("three"),                         # wrong type: string
        st.just(1.5),                             # wrong type: float
        st.just(None),                            # wrong type: NoneType
    ),
)
def test_list_turns_rejects_valid_rounds(assistants, bad_rounds):
    """[FR-PROT-AC2] Hits: not isinstance(number_of_rounds, int) or number_of_rounds - 1 < 0."""
    config = base_valid_config_list(assistants)
    config["number_of_rounds"] = bad_rounds
    with pytest.raises(ValueError, match="'number_of_rounds' must be greater than 0"):
        validate_interaction_file(config)


@given(assistants=assistant_ids)
def test_list_turns_rejects_empty_round(assistants):
    """[FR-PROT-AC4] Hits: not current_round_turns. List branch.
    turns es una lista válida pero está vacía, por lo que el único round no tiene turns.
    """
    config = base_valid_config_list(assistants)
    config["turns"] = []
    with pytest.raises(ValueError, match="at least one turn"):
        validate_interaction_file(config)



def test_list_turns_non_list_turn_group():
    """[FR-PROT-AC4] Hits: not isinstance(group, list). List branch.
    El round sí es una lista pero uno de los grupos dentro no lo es.
    Distinct from test_list_turns_rejects_non_list_round: el round SÍ es lista,
    pero un grupo dentro de él no lo es.
    """
    config = {
        "assistants": ["a", "b"],
        "topology": {"a": ["b"], "b": ["a"]},
        "turns": [["a"], "not_a_list"],
        "number_of_rounds": MIN_ROUNDS,
    }
    with pytest.raises(ValueError, match="Each turn must be a list of assistants"):
        validate_interaction_file(config)


@given(assistants=assistant_ids)
def test_list_turns_rejects_empty_turn_group(assistants):
    """[FR-PROT-AC4] Hits: not group → 'turn cannot be empty'. List branch."""
    config = base_valid_config_list(assistants)
    config["turns"] = [list(assistants), []]
    with pytest.raises(ValueError, match="turn cannot be empty"):
        validate_interaction_file(config)


@given(assistants=assistant_ids)
def test_list_turns_agent_turns_not_in_assist(assistants):
    """[FR-PROT-AC5] Hits: node not in assistants_set → 'not listed in assistants'. List branch."""
    config = base_valid_config_list(assistants)
    config["turns"] = [["ghost"]]
    with pytest.raises(ValueError, match="not listed in 'assistants'"):
        validate_interaction_file(config)


@given(assistants=assistant_ids)
def test_list_turns_agent_twice_same_round(assistants):
    """[FR-PROT-AC6] Hits: node in seen_in_round → 'speaks more than once'. List branch."""
    if len(assistants) < 2:
        return
    a = assistants[0]
    others = [x for x in assistants if x != a]
    config = base_valid_config_list(assistants)
    config["turns"] = [[a], others + [a]]
    with pytest.raises(ValueError, match="speaks more than once in the same round"):
        validate_interaction_file(config)


# ---------------------------------------------------------------------------
# FR-PROT: DICT branch
# ---------------------------------------------------------------------------

def test_dict_turns_empty_dict_rejected():
    """[FR-PROT-AC2] Validates that an empty turns dict is rejected."""
    config = {
        "assistants": ["a", "b"],
        "topology": {"a": ["b"], "b": ["a"]},
        "turns": {},
    }
    with pytest.raises(ValueError, match="at least one round with key '0'"):
        validate_interaction_file(config)


@given(assistants=assistant_ids)
def test_dict_turns_non_consecutive_keys(assistants):
    """[FR-PROT-AC2] Hits: actual_keys != expected_keys (aquí falta '1')."""
    config = {
        "assistants": assistants,
        "topology": {a: [b for b in assistants if b != a] for a in assistants},
        "turns": {"0": [list(assistants)], "2": [list(assistants)]},
    }
    with pytest.raises(ValueError, match="Keys in 'turns' dict must go strictly"):
        validate_interaction_file(config)


def test_dict_turns_rejects_non_list_round():
    """[FR-PROT-AC2] Hits: not isinstance(current_round_turns, list). Dict branch."""
    config = {
        "assistants": ["a", "b"],
        "topology": {"a": ["b"], "b": ["a"]},
        "turns": {"0": "not_a_list"},
    }
    with pytest.raises(ValueError, match="Turns for a round must be a list of lists"):
        validate_interaction_file(config)


@given(assistants=assistant_ids)
def test_dict_turns_rejects_empty_round(assistants):
    """[FR-PROT-AC3] Hits: not current_round_turns. Dict branch."""
    config = base_valid_config_dict(assistants)
    config["turns"] = {"0": []}
    with pytest.raises(ValueError, match="at least one turn"):
        validate_interaction_file(config)


def test_dict_turns_non_list_turn_group():
    """[FR-PROT-AC3] Hits: not isinstance(group, list). Dict branch.
    Distinct from test_dict_turns_rejects_non_list_round: el round SÍ es lista,
    pero un grupo dentro de él no lo es.
    """
    config = {
        "assistants": ["a", "b"],
        "topology": {"a": ["b"], "b": ["a"]},
        "turns": {"0": [["a"], "not_a_list"]},
    }
    with pytest.raises(ValueError, match="Each turn must be a list of assistants"):
        validate_interaction_file(config)


@given(assistants=assistant_ids)
def test_dict_turns_rejects_empty_turn_group(assistants):
    """[FR-PROT-AC3] Hits: not group → 'turn cannot be empty'. Dict branch."""
    config = base_valid_config_dict(assistants)
    config["turns"] = {"0": [list(assistants), []]}
    with pytest.raises(ValueError, match="turn cannot be empty"):
        validate_interaction_file(config)


@given(assistants=assistant_ids)
def test_dict_turns_agent_turns_not_in_assist(assistants):
    """[FR-PROT-AC5] Hits: node not in assistants_set → 'not listed in assistants'. Dict branch."""
    config = base_valid_config_dict(assistants)
    config["turns"] = {"0": [["ghost"]]}
    with pytest.raises(ValueError, match="not listed in 'assistants'"):
        validate_interaction_file(config)


@given(assistants=assistant_ids)
def test_dict_turns_agent_twice_same_round(assistants):
    """[FR-PROT-AC6] Hits: node in seen_in_round → 'speaks more than once'. Dict branch."""
    if len(assistants) < 2:
        return
    a = assistants[0]
    others = [x for x in assistants if x != a]
    config = base_valid_config_dict(assistants)
    config["turns"] = {"0": [[a], others + [a]]}
    with pytest.raises(ValueError, match="speaks more than once in the same round"):
        validate_interaction_file(config)



# ---------------------------------------------------------------------------
# FR-TOP AC7, FR-PROT AC7: Valid configurations must always pass
# ---------------------------------------------------------------------------

@given(config=st.one_of(
    valid_interaction_config_list(),
    valid_interaction_config_dict(),
))
def test_valid_configuration_accepted(config):
    """[FR-TOP-AC7, FR-PROT-AC7] Validates that all valid configurations generated by strategies pass without error."""
    validate_interaction_file(config)