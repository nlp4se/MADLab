"""
Hypothesis tests for FR-EXEC requirements.
Verifies that coordinator properly respects topology and executes protocol,
and that the judge agent collects the full debate history.
"""

from unittest.mock import patch, MagicMock
from hypothesis import given, note, strategies as st
from code.llm.coordinator import LLMCoordinator, AssistantAgent
from pubsub import pub
from .strategies import assistant_ids, valid_topology, valid_turns_list_strategy, MIN_ROUNDS, MAX_ROUNDS


def _make_mock_caller():
    mock_caller = MagicMock()
    mock_caller.create_thread.return_value = "fake-thread-id"
    mock_caller.send_message.return_value = ("mocked response", {
        "prompt_tokens": 0,
        "completion_tokens": 0,
        "total_tokens": 0,
        "execution_time": 0,
    })
    return mock_caller


@st.composite
def _assistants_and_topology(draw):
    assistants = draw(assistant_ids)
    topology = draw(valid_topology(assistants))
    turns = draw(valid_turns_list_strategy(assistants))
    n_rounds = draw(st.integers(min_value=MIN_ROUNDS, max_value=MAX_ROUNDS))
    return assistants, topology, turns, n_rounds


@given(config=_assistants_and_topology())
# FR-EXEC AC2
def test_messages_respect_topology(config):
    """Validates that messages are only delivered to agents in the receiver's topology."""
    assistants, topology, turns, n_rounds = config

    original_receive = AssistantAgent.receive_data
    received_messages = []

    # Spy function: replaces AssistantAgent.receive_data with spy_receive.
    # spy_receive appends each message to received_messages for spying, then calls the original receive_data.
    def spy_receive(self, sender, content, round_number=None):
        received_messages.append((self.name, sender, content))
        original_receive(self, sender, content, round_number)

    with patch("code.llm.coordinator.OpenAIAssistantCaller", return_value=_make_mock_caller()), \
         patch.object(AssistantAgent, "receive_data", spy_receive):

        coordinator = LLMCoordinator(api_key="fake")
        coordinator.run_debate(
            requirement="Test requirement",
            assistants=assistants,
            topology=topology,
            turns=turns,
            n_iterations=n_rounds - 1,
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


@st.composite
def _config_with_protocol_list(draw):
    assistants = draw(assistant_ids)
    topology = draw(valid_topology(assistants))
    turns = draw(valid_turns_list_strategy(assistants))
    n_rounds = draw(st.integers(min_value=MIN_ROUNDS, max_value=MAX_ROUNDS))
    return assistants, topology, turns, n_rounds


@given(config=_config_with_protocol_list())
# FR-EXEC AC1
def test_protocol_list_executed(config):
    """Validates that the turn protocol is executed correctly when turns are a list."""
    assistants, topology, turns, n_rounds = config
    n_iterations = n_rounds - 1

    sent_messages = []
    original_send = pub.sendMessage

    # Spy function: replaces pub.sendMessage with spy_send.
    # spy_send appends protocol events (process_/send_ topics) to sent_messages for spying, then calls the original sendMessage.
    def spy_send(topic, **kwargs):
        if topic.startswith("process_") or topic.startswith("send_"):
            sent_messages.append((topic, kwargs.get("round_number")))
        original_send(topic, **kwargs)

    with patch("code.llm.coordinator.OpenAIAssistantCaller", return_value=_make_mock_caller()), \
         patch("pubsub.pub.sendMessage", side_effect=spy_send):

        coordinator = LLMCoordinator(api_key="fake")
        coordinator.run_debate(
            requirement="Test requirement",
            assistants=assistants,
            topology=topology,
            turns=turns,
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


@st.composite
def _config_with_protocol_dict(draw):
    assistants = draw(assistant_ids)
    topology = draw(valid_topology(assistants))
    n_rounds = draw(st.integers(min_value=MIN_ROUNDS, max_value=MAX_ROUNDS))
    turns_dict = {}
    for i in range(n_rounds):
        turns_dict[str(i)] = draw(valid_turns_list_strategy(assistants))
    return assistants, topology, turns_dict, n_rounds


@given(config=_config_with_protocol_dict())
# FR-EXEC AC1
def test_protocol_dict_executed(config):
    """Validates that the turn protocol is executed correctly when turns are a dict."""
    assistants, topology, turns_dict, n_rounds = config
    n_iterations = n_rounds - 1

    sent_messages = []
    original_send = pub.sendMessage

    # Spy function: replaces pub.sendMessage with spy_send.
    # spy_send appends protocol events (process_/send_ topics) to sent_messages for spying, then calls the original sendMessage.
    def spy_send(topic, **kwargs):
        if topic.startswith("process_") or topic.startswith("send_"):
            sent_messages.append((topic, kwargs.get("round_number")))
        original_send(topic, **kwargs)

    with patch("code.llm.coordinator.OpenAIAssistantCaller", return_value=_make_mock_caller()), \
         patch("pubsub.pub.sendMessage", side_effect=spy_send):

        coordinator = LLMCoordinator(api_key="fake")
        coordinator.run_debate(
            requirement="Test requirement",
            assistants=assistants,
            topology=topology,
            turns=turns_dict,
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


@st.composite
def _full_debate_config(draw):
    """
    Returns (assistants, topology, turns, n_rounds) where turns is
    randomly either a list (list-mode) or a dict (dict-mode).
    """
    assistants = draw(assistant_ids)
    topology   = draw(valid_topology(assistants))
    n_rounds   = draw(st.integers(min_value=MIN_ROUNDS, max_value=MAX_ROUNDS))
    use_dict   = draw(st.booleans())

    if use_dict:
        turns = {
            str(i): draw(valid_turns_list_strategy(assistants))
            for i in range(n_rounds)
        }
    else:
        turns = draw(valid_turns_list_strategy(assistants))

    return assistants, topology, turns, n_rounds

@given(config=_full_debate_config())
# FR-EXEC AC3
def test_judge_collects_entire_debate(config):
    """
    Validates that the judge agent receives one response per (assistant, round) pair
    regardless of topology or turn format (list vs dict).
    """
    assistants, topology, turns, n_rounds = config
    n_iterations = n_rounds - 1

    with patch("code.llm.coordinator.OpenAIAssistantCaller",
               return_value=_make_mock_caller()):

        coordinator = LLMCoordinator(api_key="fake")
        responses, metrics = coordinator.run_debate(
            requirement="Test requirement",
            assistants=assistants,
            topology=topology,
            turns=turns,
            n_iterations=n_iterations,
        )

    note(f"assistants: {assistants}")
    note(f"n_rounds:   {n_rounds}")
    note(f"responses:  {responses}")

    expected_pairs = {
        (name, round_num)
        for name in assistants
        for round_num in range(n_rounds)
    }
    recorded_pairs = {(sender, rn) for sender, _, rn in responses}

    missing = expected_pairs - recorded_pairs
    assert not missing, (
        f"Judge is missing responses for: {missing}\n"
        f"Recorded: {recorded_pairs}"
    )

    assert len(responses) == len(assistants) * n_rounds, (
        f"Expected {len(assistants) * n_rounds} responses, "
        f"got {len(responses)}"
    )



   