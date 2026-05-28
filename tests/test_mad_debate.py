"""
Hypothesis tests for FR-EXEC requirements.
Verifies that MadDebate properly respects topology and executes protocol,
and that the judge agent collects the full debate history.
"""

from unittest.mock import patch, MagicMock
from hypothesis import given, note, strategies as st
from code.domain.mad_debate import MadDebate, DebaterAgent
from pubsub import pub
from .strategies import assistant_ids, valid_topology, valid_turns_list_strategy, MIN_ROUNDS, MAX_ROUNDS


def _make_mock_caller():
    mock_caller = MagicMock()
    mock_caller.start_session.return_value = "fake-session-id"
    mock_caller.submit_message.return_value = ("mocked response", {
        "prompt_tokens": 0,
        "completion_tokens": 0,
        "total_tokens": 0,
        "execution_time": 0,
    })
    return mock_caller


# ---------------------------------------------------------------------------
# FR-EXEC AC2: Messages respect topology
# ---------------------------------------------------------------------------

@st.composite
def _topology_test_config(draw):
    """Random assistants, random topology shape, random turns format (50/50 list/dict)."""
    assistants = draw(assistant_ids)
    topology = draw(valid_topology(assistants))
    turns = draw(valid_turns_list_strategy(assistants))
    use_dict = draw(st.booleans())
    if use_dict:
        turns = {"0": turns}
    return assistants, topology, turns


@given(config=_topology_test_config())
def test_messages_respect_topology(config):
    """[FR-EXEC-AC2] Validates that messages are only delivered to agents in the receiver's topology.
    Topology shape varies each run (ring, mesh, partial...).
    Alternates ~50/50 between list-style and dict-style turns.
    At least 1 assistant per turn guaranteed by valid_turns_list_strategy.
    """
    assistants, topology, turns = config

    original_receive = DebaterAgent.receive_data
    received_messages = []

    def spy_receive(self, sender, content, round_number=None):
        received_messages.append((self.name, sender, content))
        original_receive(self, sender, content, round_number)

    with patch.object(DebaterAgent, "receive_data", spy_receive):

        debate = MadDebate(caller=_make_mock_caller())
        debate.run_debate(
            requirement="Test requirement",
            assistants=assistants,
            topology=topology,
            turns=turns,
            judge="Judge",
            n_iterations=0,
        )

    for receiver, sender, _ in received_messages:
        if sender == "Coordinator":
            continue
        assert receiver in topology, (
            f"Receiver '{receiver}' not found in topology"
        )
        assert sender in topology[receiver], (
            f"Agent '{receiver}' received a message from '{sender}', "
            f"but '{sender}' is not in topology['{receiver}'] = {topology[receiver]}"
        )


# ---------------------------------------------------------------------------
# FR-EXEC AC1: Protocol executed correctly — list turns
# ---------------------------------------------------------------------------

@st.composite
def _config_with_protocol_list(draw):
    assistants = draw(assistant_ids)
    topology = draw(valid_topology(assistants))
    turns = draw(valid_turns_list_strategy(assistants))
    n_rounds = draw(st.integers(min_value=MIN_ROUNDS, max_value=MAX_ROUNDS))
    return assistants, topology, turns, n_rounds


@given(config=_config_with_protocol_list())
def test_protocol_list_executed(config):
    """[FR-EXEC-AC1] Validates that the turn protocol is executed correctly when turns are a list."""
    assistants, topology, turns, n_rounds = config
    n_iterations = n_rounds - 1

    sent_messages = []
    original_send = pub.sendMessage

    def spy_send(topic, **kwargs):
        if topic.startswith("process_") or topic.startswith("send_"):
            sent_messages.append((topic, kwargs.get("round_number")))
        original_send(topic, **kwargs)

    with patch("pubsub.pub.sendMessage", side_effect=spy_send):

        debate = MadDebate(caller=_make_mock_caller())
        debate.run_debate(
            requirement="Test requirement",
            assistants=assistants,
            topology=topology,
            turns=turns,
            judge="Judge",
            n_iterations=n_iterations,
        )

    expected = []
    for round_num in range(n_rounds):
        for group in turns:
            for node in group:
                expected.append((f"process_{node}", round_num))
            for node in group:
                expected.append((f"send_{node}", round_num))

    note(f"assistants: {assistants}")
    note(f"turns: {turns}")
    note(f"n_rounds: {n_rounds}")
    note(f"expected: {expected}")
    note(f"got:      {sent_messages}")

    assert sent_messages == expected, (
        f"Wrong turn sequence.\nExpected: {expected}\nGot:      {sent_messages}"
    )


# ---------------------------------------------------------------------------
# FR-EXEC AC1: Protocol executed correctly — dict turns
# ---------------------------------------------------------------------------

@st.composite
def _config_with_protocol_dict(draw):
    assistants = draw(assistant_ids)
    topology = draw(valid_topology(assistants))
    n_rounds = draw(st.integers(min_value=MIN_ROUNDS, max_value=MAX_ROUNDS))
    turns_dict = {
        str(i): draw(valid_turns_list_strategy(assistants))
        for i in range(n_rounds)
    }
    return assistants, topology, turns_dict, n_rounds


@given(config=_config_with_protocol_dict())
def test_protocol_dict_executed(config):
    """[FR-EXEC-AC1] Validates that the turn protocol is executed correctly when turns are a dict."""
    assistants, topology, turns_dict, n_rounds = config
    n_iterations = n_rounds - 1

    sent_messages = []
    original_send = pub.sendMessage

    def spy_send(topic, **kwargs):
        if topic.startswith("process_") or topic.startswith("send_"):
            sent_messages.append((topic, kwargs.get("round_number")))
        original_send(topic, **kwargs)

    with patch("pubsub.pub.sendMessage", side_effect=spy_send):

        debate = MadDebate(caller=_make_mock_caller())
        debate.run_debate(
            requirement="Test requirement",
            assistants=assistants,
            topology=topology,
            turns=turns_dict,
            judge="Judge",
            n_iterations=n_iterations,
        )

    expected = []
    for round_num in range(n_rounds):
        groups = turns_dict[str(round_num)]
        for group in groups:
            for node in group:
                expected.append((f"process_{node}", round_num))
            for node in group:
                expected.append((f"send_{node}", round_num))

    note(f"assistants: {assistants}")
    note(f"turns_dict: {turns_dict}")
    note(f"n_rounds: {n_rounds}")
    note(f"expected: {expected}")
    note(f"got:      {sent_messages}")

    assert sent_messages == expected, (
        f"Wrong turn sequence.\nExpected: {expected}\nGot:      {sent_messages}"
    )


# ---------------------------------------------------------------------------
# FR-EXEC AC3: Judge collects entire debate
# ---------------------------------------------------------------------------

@st.composite
def _full_debate_config(draw):
    """Random assistants, topology, n_rounds, and 50/50 list/dict turns."""
    assistants = draw(assistant_ids)
    topology = draw(valid_topology(assistants))
    n_rounds = draw(st.integers(min_value=MIN_ROUNDS, max_value=MAX_ROUNDS))
    use_dict = draw(st.booleans())

    if use_dict:
        turns = {
            str(i): draw(valid_turns_list_strategy(assistants))
            for i in range(n_rounds)
        }
    else:
        turns = draw(valid_turns_list_strategy(assistants))

    return assistants, topology, turns, n_rounds


@given(config=_full_debate_config())
def test_judge_collects_entire_debate(config):
    """
    [FR-EXEC-AC3] Validates that the judge receives exactly one response per (assistant, round)
    pair for every assistant that actually spoke in that round.
    """
    assistants, topology, turns, n_rounds = config
    n_iterations = n_rounds - 1

    debate = MadDebate(caller=_make_mock_caller())
    responses, metrics = debate.run_debate(
        requirement="Test requirement",
        assistants=assistants,
        topology=topology,
        turns=turns,
        judge="Judge",
        n_iterations=n_iterations,
    )

    note(f"assistants: {assistants}")
    note(f"n_rounds:   {n_rounds}")
    note(f"turns:      {turns}")
    note(f"responses:  {responses}")

    expected_pairs = set()
    for round_num in range(n_rounds):
        if isinstance(turns, dict):
            groups = turns[str(round_num)]
        else:
            groups = turns
        for group in groups:
            for node in group:
                expected_pairs.add((node, round_num))

    recorded_pairs = {(sender, rn) for sender, _, rn in responses}

    missing = expected_pairs - recorded_pairs
    assert not missing, (
        f"Judge is missing responses for: {missing}\n"
        f"Recorded: {recorded_pairs}"
    )

    assert len(responses) == len(expected_pairs), (
        f"Expected {len(expected_pairs)} responses, "
        f"got {len(responses)}"
    )
