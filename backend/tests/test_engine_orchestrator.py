"""End-to-end tests for the orchestrator (:mod:`mad.engine.orchestrator`).

These drive a full ``run_debate`` over one instance with a deterministic,
offline :class:`~mad.providers.base.MockModelClient` wired through a
:class:`~mad.providers.registry.ProviderRegistry`. They assert the resulting
:class:`~mad.engine.transcript.Transcript` structure (rounds, per-agent
messages, aggregate usage, final decision) and the orchestrator's two owned
behaviours: per-call retry/backoff with per-instance error isolation (Req 9.5,
10.4) and usage roll-up (Req 9.4).

No network, no litellm: the registry uses an injected client factory returning
a mock, so every test runs fully offline and reproducibly.

Validates: Requirements 9.4, 9.5, 10.4
"""

from __future__ import annotations

import pytest

from mad.engine.orchestrator import RetryPolicy, run_debate
from mad.engine.transcript import Transcript
from mad.providers.base import Message, MockModelClient, ModelResponse
from mad.providers.registry import ProviderConfig, ProviderRegistry
from mad.taxonomy import templates
from mad.taxonomy.schema import (
    Agreement,
    BaseModelSpec,
    ContentSpec,
    Format,
    Interaction,
    MADConfig,
    Participants,
    ParticipantNode,
    Protocol,
)
from mad.taxonomy.templates import fully_connected_topology


# ---------------------------------------------------------------------------
# Helpers / fixtures
# ---------------------------------------------------------------------------


def _no_sleep(_seconds: float) -> None:
    """A no-op sleep so backoff never actually waits during tests."""


def _registry(client) -> ProviderRegistry:
    """Registry whose single provider always resolves to ``client``."""
    return ProviderRegistry(
        providers=[ProviderConfig(id="mock", name="Mock", kind="mock", models=["m"])],
        client_factory=lambda _config: client,
    )


def _bind(config: MADConfig, provider_id: str = "mock") -> MADConfig:
    """Bind every node's base model to ``provider_id`` so resolution succeeds."""
    for node in config.participants.nodes:
        node.base_model.provider_id = provider_id
        if not node.base_model.model_key:
            node.base_model.model_key = "m"
    return config


def _two_debater_consensus_config(max_rounds: int = 2) -> MADConfig:
    """A minimal 2-debater collective/consensus config over one round or more."""
    nodes = [
        ParticipantNode(id="a", label="A", roles=["debater"], system_prompt="You are A."),
        ParticipantNode(id="b", label="B", roles=["debater"], system_prompt="You are B."),
    ]
    ids = [n.id for n in nodes]
    return MADConfig(
        name="Two-debater consensus",
        participants=Participants(nodes=nodes),
        interaction=Interaction(
            topology=fully_connected_topology(ids),
            protocol=Protocol(
                mechanism="sequential", max_rounds=max_rounds, ordering="fixed", order=ids
            ),
            format=Format(content=ContentSpec(strategy="verbatim")),
        ),
        agreement=Agreement(authority="collective", resolution="consensus"),
    )


# ---------------------------------------------------------------------------
# Basic end-to-end structure
# ---------------------------------------------------------------------------


def test_run_debate_records_per_agent_messages_each_round():
    """Sequential 2-round debate records one message per agent per round."""
    config = _bind(_two_debater_consensus_config(max_rounds=2))
    # Distinct votes so consensus never triggers an early stop (runs both rounds).
    client = MockModelClient(
        responder=lambda messages, model, params, schema: "F"
        if "You are A." in _system_text(messages)
        else "NF"
    )
    transcript = run_debate(config, {}, _registry(client), sleep=_no_sleep)

    assert isinstance(transcript, Transcript)
    assert transcript.rounds == 2
    # 2 agents x 2 rounds = 4 debater messages.
    assert len(transcript.messages) == 4
    assert [m.node_id for m in transcript.messages] == ["a", "b", "a", "b"]
    assert sorted({m.round_index for m in transcript.messages}) == [0, 1]


def test_run_debate_aggregates_usage_across_calls():
    """Transcript usage is the additive roll-up of every call's usage (Req 9.4)."""
    config = _bind(_two_debater_consensus_config(max_rounds=1))
    client = MockModelClient()  # default echo; non-zero word counts.
    transcript = run_debate(config, {}, _registry(client), sleep=_no_sleep)

    per_call_total = sum(m.usage.total_tokens for m in transcript.messages)
    assert transcript.usage.total_tokens == per_call_total
    assert transcript.usage.total_tokens > 0


def test_run_debate_resolves_template_into_prompt_and_decision():
    """The input template is resolved and a collective decision is produced."""
    config = _bind(_two_debater_consensus_config(max_rounds=1))
    config.input_spec.template = "Classify: {{requirement}}"
    config.input_spec.placeholders = ["requirement"]
    client = MockModelClient(responder=lambda *a: "yes")  # unanimous -> consensus

    transcript = run_debate(
        config, {"requirement": "The app loads in 2s"}, _registry(client), sleep=_no_sleep
    )

    assert transcript.resolved_input == "Classify: The app loads in 2s"
    assert transcript.decision is not None
    assert transcript.decision.decision == "yes"
    assert transcript.decision.undecided is False


# ---------------------------------------------------------------------------
# Early consensus stop
# ---------------------------------------------------------------------------


def test_run_debate_stops_early_on_consensus():
    """A unanimous first round stops a consensus debate before max_rounds."""
    config = _bind(_two_debater_consensus_config(max_rounds=5))
    client = MockModelClient(responder=lambda *a: "agree")  # always unanimous

    transcript = run_debate(config, {}, _registry(client), sleep=_no_sleep)

    assert transcript.rounds == 1  # stopped after round 0
    assert len(transcript.messages) == 2
    assert transcript.decision.decision == "agree"


# ---------------------------------------------------------------------------
# Retry / backoff + per-instance error isolation (Req 9.5)
# ---------------------------------------------------------------------------


class _FlakyClient:
    """Fails the first ``fail_times`` calls, then succeeds. Counts attempts."""

    def __init__(self, fail_times: int, reply: str = "ok"):
        self.fail_times = fail_times
        self.reply = reply
        self.attempts = 0

    def complete(self, messages, model, params=None, response_schema=None):
        self.attempts += 1
        if self.attempts <= self.fail_times:
            raise RuntimeError(f"transient failure #{self.attempts}")
        return ModelResponse(text=self.reply)


def test_retry_succeeds_within_policy():
    """A call that fails twice then succeeds is retried and recorded (Req 9.5)."""
    config = _bind(_two_debater_consensus_config(max_rounds=1))
    client = _FlakyClient(fail_times=2, reply="ok")
    policy = RetryPolicy(max_attempts=3, base_delay_s=0.01)

    delays: list[float] = []
    transcript = run_debate(
        config, {}, _registry(client), retry_policy=policy, sleep=delays.append
    )

    # First node: 2 failures + 1 success = 3 attempts. Second node: 1 success.
    assert client.attempts == 4
    assert len(transcript.messages) == 2
    assert transcript.errors == []
    # Two backoff sleeps happened before the two retries of the first node.
    assert len(delays) == 2
    assert delays[1] > delays[0]  # exponential backoff grows.


def test_failure_is_isolated_and_recorded():
    """A node whose calls all fail is recorded; the run continues (Req 9.5)."""
    nodes = [
        ParticipantNode(id="a", label="A", roles=["debater"], system_prompt="A",
                        base_model=BaseModelSpec(provider_id="bad", model_key="m")),
        ParticipantNode(id="b", label="B", roles=["debater"], system_prompt="B",
                        base_model=BaseModelSpec(provider_id="good", model_key="m")),
    ]
    ids = [n.id for n in nodes]
    config = MADConfig(
        name="isolation",
        participants=Participants(nodes=nodes),
        interaction=Interaction(
            topology=fully_connected_topology(ids),
            protocol=Protocol(mechanism="sequential", max_rounds=1, ordering="fixed", order=ids),
            format=Format(content=ContentSpec(strategy="verbatim")),
        ),
        agreement=Agreement(authority="collective", resolution="majority_vote"),
    )

    always_fail = _FlakyClient(fail_times=99)
    good = MockModelClient(responder=lambda *a: "NF")

    def factory(provider_config):
        return always_fail if provider_config.id == "bad" else good

    registry = ProviderRegistry(
        providers=[
            ProviderConfig(id="bad", name="Bad", kind="mock", models=["m"]),
            ProviderConfig(id="good", name="Good", kind="mock", models=["m"]),
        ],
        client_factory=factory,
    )

    policy = RetryPolicy(max_attempts=2, base_delay_s=0.0)
    transcript = run_debate(config, {}, registry, retry_policy=policy, sleep=_no_sleep)

    # Node 'a' failed entirely; only 'b' produced a message.
    assert [m.node_id for m in transcript.messages] == ["b"]
    assert len(transcript.errors) == 1
    error = transcript.errors[0]
    assert error.node_id == "a"
    assert error.attempts == 2
    # The run still produced a decision from the surviving debater.
    assert transcript.decision is not None
    assert transcript.decision.decision == "NF"


# ---------------------------------------------------------------------------
# Gold case: RE binary debate (judge-based, output_schema) end-to-end
# ---------------------------------------------------------------------------


def test_re_binary_gold_case_runs_end_to_end():
    """The RE binary gold case runs with a judge returning a schema-valid class."""
    config = _bind(templates.re_binary_debate())

    def responder(messages, model, params, response_schema):
        # The judge call carries the output_schema; return a schema-valid reply.
        if response_schema is not None:
            return '{"class": "NF"}'
        return "I argue my stance."

    client = MockModelClient(responder=responder)
    transcript = run_debate(config, {"requirement": "Login must be fast"},
                            _registry(client), sleep=_no_sleep)

    assert transcript.rounds == 2
    # Two debaters x two rounds = 4 debater turns, plus one judge turn.
    debater_turns = [m for m in transcript.messages if m.role == "debater"]
    judge_turns = [m for m in transcript.messages if m.role == "judge"]
    assert len(debater_turns) == 4
    assert len(judge_turns) == 1

    decision = transcript.decision
    assert decision is not None
    assert decision.authority == "judge_based"
    assert decision.structured == {"class": "NF"}
    assert decision.decision == {"class": "NF"}


# ---------------------------------------------------------------------------
# Start/End IO connections: topology.entry_nodes / exit_nodes (task 11.2)
# ---------------------------------------------------------------------------


def _io_config(
    *,
    roles: dict[str, list[str]],
    authority: str = "collective",
    resolution: str = "majority_vote",
    max_rounds: int = 1,
    entry_nodes=None,
    exit_nodes=None,
) -> MADConfig:
    """A config over ``roles`` (id -> roles) with optional IO overrides.

    Every node's system prompt is ``"You are <id>."`` so a responder (and the
    recorded calls) can tell nodes apart. The input template is fixed so the
    "Task: ..." line is easy to detect.
    """
    nodes = [
        ParticipantNode(id=i, label=i.upper(), roles=r, system_prompt=f"You are {i}.")
        for i, r in roles.items()
    ]
    ids = [n.id for n in nodes]
    topology = fully_connected_topology(ids).model_copy(
        update={"entry_nodes": entry_nodes, "exit_nodes": exit_nodes}
    )
    config = MADConfig(
        name="io",
        participants=Participants(nodes=nodes),
        interaction=Interaction(
            topology=topology,
            protocol=Protocol(
                mechanism="sequential", max_rounds=max_rounds, ordering="fixed", order=ids
            ),
            format=Format(content=ContentSpec(strategy="verbatim")),
        ),
        agreement=Agreement(authority=authority, resolution=resolution),
    )
    config.input_spec.template = "Classify: {{x}}"
    config.input_spec.placeholders = ["x"]
    return _bind(config)


def _node_of(messages: list[Message]) -> str:
    """Recover the calling node id from its ``You are <id>.`` system prompt."""
    text = _system_text(messages)
    return text.split("You are ", 1)[1].split(".", 1)[0]


def _votes(table: dict[str, str]):
    """Responder replying with ``table[node_id]``."""
    return lambda messages, model, params, schema: table[_node_of(messages)]


def _task_receivers(client: MockModelClient) -> set[str]:
    """Node ids whose (debate-turn) system prompt carried the task line."""
    return {
        _node_of(call.messages)
        for call in client.calls
        if "Task: Classify: req" in _system_text(call.messages)
    }


def test_entry_nodes_none_gives_every_speaker_the_task():
    """Default (entry_nodes=None): every speaking participant receives the input."""
    config = _io_config(roles={"a": ["debater"], "b": ["debater"], "c": ["debater"]})
    client = MockModelClient(responder=lambda *a: "F")
    run_debate(config, {"x": "req"}, _registry(client), sleep=_no_sleep)
    assert _task_receivers(client) == {"a", "b", "c"}


def test_entry_nodes_restrict_which_system_prompts_contain_the_task():
    """Only entry nodes get the "Task: <input>" line in their system prompt."""
    config = _io_config(
        roles={"a": ["debater"], "b": ["debater"], "c": ["debater"]},
        entry_nodes=["a"],
    )
    client = MockModelClient(responder=lambda *a: "F")
    run_debate(config, {"x": "req"}, _registry(client), sleep=_no_sleep)

    assert _task_receivers(client) == {"a"}
    # Non-entry nodes still keep their own prompt; only the task line is gone.
    b_call = next(c for c in client.calls if _node_of(c.messages) == "b")
    assert _system_text(b_call.messages).strip() == "You are b."


def test_exit_nodes_restrict_collective_aggregation():
    """Collective majority aggregates only the exit nodes' latest outputs."""
    roles = {"a": ["debater"], "b": ["debater"], "c": ["debater"]}
    table = {"a": "F", "b": "NF", "c": "NF"}

    default = run_debate(
        _io_config(roles=roles), {"x": "req"},
        _registry(MockModelClient(responder=_votes(table))), sleep=_no_sleep,
    )
    assert default.decision.decision == "NF"  # 2 of 3 debaters

    restricted = run_debate(
        _io_config(roles=roles, exit_nodes=["a"]), {"x": "req"},
        _registry(MockModelClient(responder=_votes(table))), sleep=_no_sleep,
    )
    assert restricted.decision.decision == "F"  # only 'a' feeds End


def test_exit_nodes_filter_the_early_consensus_probe():
    """The consensus early-stop probe uses the same exit-filtered set."""
    roles = {"a": ["debater"], "b": ["debater"]}
    table = {"a": "yes", "b": "no"}

    default = run_debate(
        _io_config(roles=roles, resolution="consensus", max_rounds=3), {"x": "req"},
        _registry(MockModelClient(responder=_votes(table))), sleep=_no_sleep,
    )
    assert default.rounds == 3  # a and b never agree
    assert default.decision.undecided is True

    restricted = run_debate(
        _io_config(roles=roles, resolution="consensus", max_rounds=3, exit_nodes=["a"]),
        {"x": "req"},
        _registry(MockModelClient(responder=_votes(table))), sleep=_no_sleep,
    )
    assert restricted.rounds == 1  # 'a' alone is unanimous -> early stop
    assert restricted.decision.decision == "yes"


def test_judge_based_uses_first_judge_listed_in_exit_nodes():
    """judge_based: the deciding judge is the first judge listed in exit_nodes."""
    roles = {"a": ["debater"], "j1": ["judge"], "j2": ["judge"]}
    table = {"a": "argument", "j1": "J1", "j2": "J2"}

    default = run_debate(
        _io_config(roles=roles, authority="judge_based", resolution="argument_evaluation"),
        {"x": "req"}, _registry(MockModelClient(responder=_votes(table))), sleep=_no_sleep,
    )
    assert default.decision.decision == "J1"  # first judge in declaration order

    listed = run_debate(
        _io_config(
            roles=roles, authority="judge_based", resolution="argument_evaluation",
            exit_nodes=["a", "j2"],
        ),
        {"x": "req"}, _registry(MockModelClient(responder=_votes(table))), sleep=_no_sleep,
    )
    assert listed.decision.decision == "J2"
    assert [m.node_id for m in listed.messages if m.role == "judge"] == ["j2"]


def test_hybrid_exit_nodes_without_a_judge_disable_the_fallback():
    """hybrid: a tie escalates to the judge only if the judge is an exit node."""
    roles = {"a": ["debater"], "b": ["debater"], "j": ["judge"]}
    table = {"a": "F", "b": "NF", "j": "JUDGED"}

    default = run_debate(
        _io_config(roles=roles, authority="hybrid"), {"x": "req"},
        _registry(MockModelClient(responder=_votes(table))), sleep=_no_sleep,
    )
    assert default.decision.decision == "JUDGED"  # tie -> fell back to judge

    no_judge = run_debate(
        _io_config(roles=roles, authority="hybrid", exit_nodes=["a", "b"]), {"x": "req"},
        _registry(MockModelClient(responder=_votes(table))), sleep=_no_sleep,
    )
    assert no_judge.decision.undecided is True
    assert all(m.node_id != "j" for m in no_judge.messages)

    with_judge = run_debate(
        _io_config(roles=roles, authority="hybrid", exit_nodes=["a", "b", "j"]),
        {"x": "req"}, _registry(MockModelClient(responder=_votes(table))), sleep=_no_sleep,
    )
    assert with_judge.decision.decision == "JUDGED"


def test_retry_policy_delay_schedule():
    """RetryPolicy backoff grows exponentially and is capped."""
    policy = RetryPolicy(max_attempts=5, base_delay_s=1.0, backoff_factor=2.0, max_delay_s=5.0)
    assert policy.delay_before(1) == 0.0
    assert policy.delay_before(2) == 1.0
    assert policy.delay_before(3) == 2.0
    assert policy.delay_before(4) == 4.0
    assert policy.delay_before(5) == 5.0  # capped at max_delay_s (would be 8.0)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _system_text(messages: list[Message]) -> str:
    """Concatenate the system messages' content for responder branching."""
    return " ".join(m.content for m in messages if m.role == "system")


# ---------------------------------------------------------------------------
# Presentation-only ``ui`` layout (task 11.4): the engine ignores it.
# ---------------------------------------------------------------------------


def test_ui_layout_does_not_affect_the_run():
    """A config carrying ``ui`` runs identically to the same config without it."""
    from mad.taxonomy.schema import UiLayout

    def responder(messages, model, params, response_schema):
        if response_schema is not None:
            return '{"class": "NF"}'
        return f"turn for {_system_text(messages)[:20]}"

    def run(config: MADConfig) -> Transcript:
        return run_debate(
            config, {"requirement": "Login must be fast"},
            _registry(MockModelClient(responder=responder)), sleep=_no_sleep,
        )

    plain = _bind(templates.re_binary_debate())
    with_ui = _bind(templates.re_binary_debate())
    with_ui.id = plain.id
    with_ui.ui = UiLayout.model_validate({
        "nodes": {n.id: {"x": 10.0 * i, "y": 5.0} for i, n in
                  enumerate(with_ui.participants.nodes)} | {"__start__": {"x": -200, "y": 0}},
        "edges": {"__start__->x": {"x": 12.5, "y": -30}},
    })

    a, b = run(plain), run(with_ui)
    assert a.rounds == b.rounds
    assert [(m.node_id, m.round_index, m.role, m.content) for m in a.messages] == [
        (m.node_id, m.round_index, m.role, m.content) for m in b.messages
    ]
    assert a.decision == b.decision
    assert a.errors == b.errors
