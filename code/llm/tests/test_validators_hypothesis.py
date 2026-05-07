"""
Hypothesis tests for FR-TOP and FR-PROT requirements.
Verifies that `validators.py` rejects invalid configurations
and accepts valid ones, without duplicating validation logic.
"""

import pytest
from hypothesis import given, strategies as st
from ..validators import validate_interaction_file, validate_turns
from .strategies import (
    assistant_ids,
    valid_interaction_config_list,
    valid_interaction_config_dict,
    MIN_ROUNDS,
)

def base_valid_config(assistants):
    """Creates a simple valid configuration (empty topology, one round, one turn with all agents)."""
    return {
        "assistants": assistants,
        "topology": {a: [] for a in assistants},
        "turns": [assistants],
        "number_of_rounds": MIN_ROUNDS,
    }

@given(assistants=assistant_ids)
# FR-TOP AC2
def test_missing_topology_key(assistants):
    """Validates that missing 'topology' key is rejected."""
    config = base_valid_config(assistants)
    del config["topology"]
    with pytest.raises(ValueError, match="Missing mandatory attribute 'topology'"):
        validate_interaction_file(config)

@given(assistants=assistant_ids)
# FR-TOP AC6
def test_self_reference_rejected(assistants):
    """Validates that self-referencing topology edges are rejected."""
    config = base_valid_config(assistants)
    config["topology"] = {a: [] for a in assistants}
    config["topology"][assistants[0]] = [assistants[0]]
    with pytest.raises(ValueError, match="cannot point to itself"):
        validate_interaction_file(config)

@given(assistants=assistant_ids)
# FR-TOP AC5
def test_duplicate_targets_rejected(assistants):
    """Validates that duplicate edges in topology are rejected."""
    config = base_valid_config(assistants)
    a, b = assistants[0], assistants[1]
    config["topology"] = {x: [] for x in assistants}
    config["topology"][a] = [b, b]
    with pytest.raises(ValueError, match=r"(?s)Duplicate edges detected for node '.*'"):
        validate_interaction_file(config)

@given(assistants=assistant_ids)
# FR-TOP AC4
def test_nonexistent_source_node(assistants):
    """Validates that nonexistent source nodes in topology are rejected."""
    config = base_valid_config(assistants)
    config["topology"] = {"ghost": []}
    with pytest.raises(ValueError, match="Source node 'ghost' .* does not exist"):
        validate_interaction_file(config)

@given(assistants=assistant_ids)
# FR-TOP AC4
def test_nonexistent_target_node(assistants):
    """Validates that nonexistent target nodes in topology are rejected."""
    config = base_valid_config(assistants)
    config["topology"] = {a: [] for a in assistants}
    config["topology"][assistants[0]] = ["ghost"]
    with pytest.raises(ValueError, match="Target node 'ghost' .* does not exist"):
        validate_interaction_file(config)

@given(assistants=assistant_ids)
# FR-PROT AC2
def test_turns_list_missing_rounds(assistants):
    """Validates that missing 'number_of_rounds' is rejected."""
    config = base_valid_config(assistants)
    del config["number_of_rounds"]
    with pytest.raises(ValueError, match="'number_of_rounds' must be specified"):
        validate_interaction_file(config)

@given(assistants=assistant_ids, invalid_rounds=st.integers(min_value=-5, max_value=0))
# FR-PROT AC2
def test_turns_list_invalid_rounds(assistants, invalid_rounds):
    """Validates that invalid 'number_of_rounds' (≤0) is rejected."""
    config = base_valid_config(assistants)
    config["number_of_rounds"] = invalid_rounds
    with pytest.raises(ValueError, match="'number_of_rounds' must be greater than 0"):
        validate_interaction_file(config)

@given(assistants=assistant_ids)
# FR-PROT AC3
def test_turns_dict_wrong_keys(assistants):
    """Validates that turns dict with non-consecutive keys is rejected."""
    config = {
        "assistants": assistants,
        "topology": {a: [] for a in assistants},
        "turns": {"0": [assistants], "2": [assistants]},
    }
    with pytest.raises(ValueError, match="Keys in 'turns' dict must go strictly"):
        validate_interaction_file(config)

@given(assistants=assistant_ids)
# FR-PROT AC6
def test_agent_speaks_twice_in_round(assistants):
    """Validates that an agent speaking twice in one round is rejected."""
    if len(assistants) < 2:
        return
    config = base_valid_config(assistants)
    a = assistants[0]
    others = [x for x in assistants if x != a]
    config["turns"] = [[a], others + [a]]
    with pytest.raises(ValueError, match="speaks more than once in the same round"):
        validate_interaction_file(config)

@given(assistants=assistant_ids)
# FR-PROT AC5
def test_unknown_agent_in_turns(assistants):
    """Validates that agents in turns not listed in 'assistants' are rejected."""
    config = base_valid_config(assistants)
    config["turns"] = [["ghost"]]
    with pytest.raises(ValueError, match="not listed in 'assistants'"):
        validate_interaction_file(config)

# FR-TOP AC2
def test_assistants_not_list():
    """Validates that non-list 'assistants' is rejected."""
    config = {"assistants": "soy_string", "topology": {}, "turns": []}
    with pytest.raises(ValueError, match="'assistants' must be a list"):
        validate_interaction_file(config)

# FR-TOP AC2
def test_topology_not_dict():
    """Validates that non-dict 'topology' is rejected."""
    config = {"assistants": [], "topology": "no_soy_dict", "turns": []}
    with pytest.raises(ValueError, match="'topology' must be a dictionary"):
        validate_interaction_file(config)

# FR-PROT AC2
def test_turns_not_list_nor_dict():
    """Validates that 'turns' must be either list or dict."""
    config = {"assistants": [], "topology": {}, "turns": 123}
    with pytest.raises(ValueError, match="'turns' must be a list or a dictionary"):
        validate_interaction_file(config)

# FR-PROT AC3
def test_round_not_list():
    """Validates that non-list rounds in turns dict are rejected."""
    config = {
        "assistants": ["a", "b"],
        "topology": {},
        "turns": {"0": "no_soy_lista"}
    }
    with pytest.raises(ValueError, match="Turns for a round must be a list of lists"):
        validate_interaction_file(config)

# FR-PROT AC3
def test_group_not_list():
    """Validates that non-list groups within turns are rejected."""
    config = {
        "assistants": ["a", "b"],
        "topology": {},
        "turns": {"0": [["a"], "no_soy_lista"]}
    }
    with pytest.raises(ValueError, match="Each turn must be a list of assistants"):
        validate_interaction_file(config)

@given(config=st.one_of(
    valid_interaction_config_list(),
    valid_interaction_config_dict(),
))
# FR-TOP AC7, FR-PROT AC7
def test_valid_configuration_accepted(config):
    """Validates that all valid configurations pass without error."""
    validate_interaction_file(config)