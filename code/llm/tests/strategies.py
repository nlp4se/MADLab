"""
Hypothesis strategies for generating synthetic configurations (valid and invalid)
for the multi-agent debate system.
Used by test_validators_hypothesis.py and test_execution_hypothesis.py to generate
test data for topologies, turns, and interaction configurations.
"""

import string
import hypothesis.strategies as st

MIN_ASSISTANTS = 2
MAX_ASSISTANTS = 3
MAX_ROUNDS = 2
MIN_ROUNDS = 1

_FIRST = string.ascii_letters
_REST = string.ascii_letters + string.digits

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
    """Builds a topology where each node points to a non-empty subset of the other assistants,
    with no self-references and no duplicate edges."""
    topology = {}
    for src in assistants:
        possible_targets = [a for a in assistants if a != src]
        targets = draw(
            st.lists(
                st.sampled_from(possible_targets),
                unique=True,
                min_size=1,
                max_size=len(possible_targets),
            )
        )
        topology[src] = targets
    return topology


@st.composite
def valid_turns_list_strategy(draw, assistants):
    """
    Returns a list of non-empty turn groups where each group contains at least
    one assistant. Assistants can appear at most once across all groups in the
    round (no duplicates), but not all assistants need to appear.
    """
    # Draw a non-empty subset of assistants (at least 1).
    n = len(assistants)
    subset_size = draw(st.integers(min_value=1, max_value=n))
    perm = draw(st.permutations(assistants))
    selected = list(perm[:subset_size])

    if subset_size == 1 or draw(st.booleans()):
        return [selected]

    # Partition selected into non-empty groups via unique cut points.
    number_of_groups = draw(st.integers(min_value=1, max_value=subset_size))
    if number_of_groups == 1:
        return [selected]

    cut_points = sorted(
        draw(
            st.lists(
                st.integers(min_value=1, max_value=subset_size - 1),
                min_size=number_of_groups - 1,
                max_size=number_of_groups - 1,
                unique=True,
            )
        )
    )

    groups = []
    start = 0
    for cut in cut_points:
        groups.append(selected[start:cut])
        start = cut
    groups.append(selected[start:])

    return [g for g in groups if g]


@st.composite
def valid_interaction_config_list(draw):
    """
    Returns a valid interaction configuration where turns is a list of groups.
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
    Returns a valid interaction configuration where turns is a dict mapping
    consecutive string keys "0".."n-1" to independently drawn round turn lists.
    number_of_rounds is intentionally omitted: the validator does not require it
    when turns is already a dict.
    """
    assistants = draw(assistant_ids)
    topology = draw(valid_topology(assistants))
    n_rounds = draw(st.integers(min_value=MIN_ROUNDS, max_value=MAX_ROUNDS))
    turns_dict = {
        str(i): draw(valid_turns_list_strategy(assistants))
        for i in range(n_rounds)
    }
    return {
        "assistants": assistants,
        "topology": topology,
        "turns": turns_dict,
    }