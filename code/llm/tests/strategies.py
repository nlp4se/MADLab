"""
Hypothesis strategies for generating synthetic configurations (valid and invalid)
for the multi-agent debate system.
Used by test_validators_hypothesis.py and test_execution_hypothesis.py to generate
test data for topologies, turns, and interaction configurations.
"""

import string
import hypothesis.strategies as st

MIN_ASSISTANTS = 2
MAX_ASSISTANTS = 5
MAX_ROUNDS = 3
MIN_ROUNDS = 1

_FIRST = string.ascii_letters
_REST = string.ascii_letters + string.digits

# Build a pubsub-safe assistant name: first character must be an ASCII letter,
# the rest (up to 9 characters) can be ASCII letters or digits.
_safe_assistant_name = st.builds(
    lambda first, rest: first + rest,
    st.sampled_from(_FIRST),
    st.text(alphabet=_REST, min_size=0, max_size=9),
)

assistant_ids = st.lists(
    _safe_assistant_name,
    min_size=MIN_ASSISTANTS,
    max_size=MAX_ASSISTANTS,
    unique=True,
)

@st.composite
def valid_topology(draw, assistants):
    """Builds a topology where each source points to a subset of the other assistants."""
    topology = {}
    for src in assistants:
        possible_targets = [a for a in assistants if a != src]
        targets = draw(
            st.lists(
                st.sampled_from(possible_targets),
                unique=True,
                max_size=len(possible_targets),
            )
        )
        topology[src] = targets
    return topology

@st.composite
def valid_turns_list_strategy(draw, assistants):
    """
    Returns a list of groups (turns) that partitions the assistants,
    such that each assistant appears in exactly one group.
    """
    perm = draw(st.permutations(assistants))
    number_of_groups = draw(st.integers(min_value=1, max_value=len(assistants)))
    if number_of_groups == 1:
        return [list(perm)]
    indexes_cuts = sorted(
        draw(
            st.lists(
                st.integers(min_value=1, max_value=len(assistants) - 1),
                min_size=number_of_groups - 1,
                max_size=number_of_groups - 1,
                unique=True,
            )
        )
    )
    # Take the shuffled list of assistants and slice it at the chosen cut points to form the turn groups.
    groups = []
    start = 0
    for index_cut in indexes_cuts:
        groups.append(list(perm[start:index_cut]))
        start = index_cut
    groups.append(list(perm[start:]))
    groups = [g for g in groups if g]
    return groups

@st.composite
def valid_interaction_config_list(draw):
    """
    Returns a valid interaction configuration with turns as a list of groups.
    """
    assistants = draw(assistant_ids)
    topology = draw(valid_topology(assistants))
    turns = draw(valid_turns_list_strategy(assistants))
    number_of_rounds = draw(st.integers(min_value=MIN_ROUNDS, max_value=MAX_ROUNDS))
    return {
        "assistants": assistants,
        "topology": topology,
        "turns": turns,
        "number_of_rounds": number_of_rounds,
    }

@st.composite
def valid_interaction_config_dict(draw):
    """
    Returns a valid interaction configuration with turns as a dictionary mapping round numbers to groups.
    """
    assistants = draw(assistant_ids)
    topology = draw(valid_topology(assistants))
    n_rounds = draw(st.integers(min_value=MIN_ROUNDS, max_value=MAX_ROUNDS))
    turns_dict = {}
    for i in range(n_rounds):
        turns_dict[str(i)] = draw(valid_turns_list_strategy(assistants))
    return {
        "assistants": assistants,
        "topology": topology,
        "turns": turns_dict,
        "number_of_rounds": n_rounds,
    }