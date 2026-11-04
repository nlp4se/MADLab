"""What every participant receives, per protocol and topology (task 11.14).

Message-level audit with a recording :class:`MockModelClient`:

* config 8's shape (2 debaters + 1 judge, debaters fully connected, both entry
  nodes, sequential fixed ordering, 3 rounds, judge_based +
  argument_evaluation): the exact list every debater call and the judge call
  receive, plus structural invariants over N rounds;
* simultaneous rounds (only previous rounds visible, concurrent turns replayed
  own-first) and a chain topology (predecessors only, non-entry nodes still get
  context);
* the judge context (task, all rounds, all speakers by label, failed turns
  noted, closing line, the judge's own system prompt + persona) for
  judge_based and hybrid;
* the summarizer's input (attributed verbatim history of the others);
* attribution with colliding / blank labels.

Validates: Requirements 2.1, 2.3, 2.7, 2.8, 3.1, 9.1
"""

from __future__ import annotations

import copy
from typing import Any, Optional

import pytest

from mad.engine.format import (
    TURN_PROMPT_NO_TASK,
    TURN_PROMPT_WITH_TASK,
    HistoryRecord,
    assemble_context,
    speaker_names,
)
from mad.engine.graph import DebateGraph
from mad.engine.orchestrator import (
    FAILED_TURN_NOTE,
    JUDGE_CLOSING,
    RetryPolicy,
    run_debate,
)
from mad.providers.base import Message, MockModelClient
from mad.providers.registry import ProviderConfig, ProviderRegistry
from mad.taxonomy import templates
from mad.taxonomy.schema import MADConfig, ParticipantNode

REQ = "The system shall refresh the display every 60 seconds."
TASK = f"Classify this requirement: {REQ}"

F_ID, NF_ID, JUDGE_ID = "participant-1", "participant-2", "participant-3"
F_NAME, NF_NAME = "Functional Debater", "Non-functional Debater"

# Config 8's stored config_snapshot (execution 4), copied read-only from
# backend/mad.db; the ``ui`` block and provider bindings are irrelevant here.
CONFIG_8: dict[str, Any] = {
    "schema_version": "1.0",
    "name": "RE@Next!Debate",
    "participants": {
        "base_model_heterogeneity": "heterogeneous",
        "persona_heterogeneity": "heterogeneous",
        "persona_assignment": "manual",
        "nodes": [
            {
                "id": F_ID,
                "label": F_NAME,
                "roles": ["debater"],
                "persona": {"stance": "Always in favour of the response functional (F)"},
                "base_model": {"model_key": "m", "family": "closed_weight"},
                "system_prompt": (
                    "You are a debater arguing that the received requirement is "
                    "functional (F)."
                ),
            },
            {
                "id": NF_ID,
                "label": NF_NAME,
                "roles": ["debater"],
                "persona": {
                    "stance": "Always in favour of the response non-functional (NF)"
                },
                "base_model": {"model_key": "m", "family": "closed_weight"},
                "system_prompt": (
                    "You are a debater arguing that the received requirement is "
                    "non-functional (NF)."
                ),
            },
            {
                "id": JUDGE_ID,
                "label": "Participant 3",
                "roles": ["judge"],
                "base_model": {"model_key": "m", "family": "closed_weight"},
                "system_prompt": (
                    "You are a moderator. There will be two debaters involved in a "
                    "debate competition. They will present their answers and discuss "
                    "their perspectives on whether a given requirement should be "
                    "classified as functional (F) or non-functional (NF). At the end "
                    "of each round, you will evaluate their answers and decide which "
                    "classification is more appropriate."
                ),
            },
        ],
    },
    "interaction": {
        "topology": {
            "adaptability": "static",
            "structure": "fully_connected",
            "edges": [
                {"source": F_ID, "target": NF_ID, "directed": True},
                {"source": NF_ID, "target": F_ID, "directed": True},
            ],
            "entry_nodes": [F_ID, NF_ID],
            "exit_nodes": None,
        },
        "protocol": {
            "mechanism": "sequential",
            "max_rounds": 3,
            "ordering": "fixed",
            "order": [],
        },
        "format": {
            "syntax": "natural_language",
            "content": {"strategy": "verbatim", "metadata_signals": []},
            "memory": "short_term",
        },
    },
    "agreement": {
        "authority": "judge_based",
        "resolution": "argument_evaluation",
        "output_schema": {
            "name": "requirements-schema",
            "description": "A schema for classifying requirements into categories",
            "schema": {
                "type": "object",
                "properties": {"class": {"type": "string", "enum": ["F", "NF"]}},
            },
        },
    },
    "input_spec": {
        "template": "Classify this requirement: {{requirement}}",
        "placeholders": ["requirement"],
        "ad_hoc_fields": [{"key": "requirement", "label": "requirement"}],
    },
}


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _no_sleep(_seconds: float) -> None:
    """No-op sleep so retry/backoff never waits."""


def _registry(client) -> ProviderRegistry:
    return ProviderRegistry(
        providers=[ProviderConfig(id="mock", name="Mock", kind="mock", models=["m"])],
        client_factory=lambda _config: client,
    )


def _bind(config: MADConfig) -> MADConfig:
    for node in config.participants.nodes:
        node.base_model.provider_id = "mock"
        node.base_model.model_key = "m"
    return config


def _config8(**protocol: Any) -> MADConfig:
    data = copy.deepcopy(CONFIG_8)
    data["interaction"]["protocol"].update(protocol)
    return _bind(MADConfig.model_validate(data))


def _system(messages: list[Message]) -> str:
    return messages[0].content if messages and messages[0].role == "system" else ""


def _speaker_of(messages: list[Message]) -> str:
    """Short tag of the calling node, read from its system prompt."""
    system = _system(messages)
    if "(NF)." in system:
        return "NF"
    if "(F)." in system:
        return "F"
    return system.split(".", 1)[0]


class Debate:
    """Recording client whose debaters reply ``<tag><n>`` (n = own turn count)."""

    def __init__(self, fail: Optional[set[tuple[str, int]]] = None) -> None:
        self.counts: dict[str, int] = {}
        self.fail = fail or set()
        self.client = MockModelClient(responder=self._respond)

    def _respond(self, messages, model, params, schema):
        if schema is not None:
            return '{"class": "NF"}'
        tag = _speaker_of(messages)
        n = self.counts.get(tag, 0) + 1
        self.counts[tag] = n
        if (tag, n) in self.fail:
            raise RuntimeError("simulated outage")
        return f"{tag}{n}"

    @property
    def calls(self):
        return self.client.calls

    def debater_calls(self):
        return [c for c in self.calls if c.response_schema is None]

    def judge_calls(self):
        return [c for c in self.calls if c.response_schema is not None]


def _run(config: MADConfig, debate: Debate, **kwargs):
    return run_debate(
        config, {"requirement": REQ}, _registry(debate.client),
        sleep=_no_sleep, **kwargs,
    )


def _u(content: str) -> Message:
    return Message(role="user", content=content)


def _a(content: str) -> Message:
    return Message(role="assistant", content=content)


def _sys(node: ParticipantNode, task: str = TASK) -> Message:
    parts = [node.system_prompt, f"Stance: {node.persona.stance}"]
    if task:
        parts.append(f"Task: {task}")
    return Message(role="system", content="\n\n".join(parts))


# ---------------------------------------------------------------------------
# Config 8: the stored shape
# ---------------------------------------------------------------------------


def test_config8_snapshot_shape_is_what_the_audit_covers():
    config = _config8()
    graph = DebateGraph.from_config(config)
    topology = config.interaction.topology
    assert graph.predecessors(F_ID) == [NF_ID]
    assert graph.predecessors(NF_ID) == [F_ID]
    # The judge is outside the debate graph: it decides from the whole transcript.
    assert graph.predecessors(JUDGE_ID) == [] and graph.successors(JUDGE_ID) == []
    assert topology.entry_nodes == [F_ID, NF_ID] and topology.exit_nodes is None
    protocol = config.interaction.protocol
    assert (protocol.mechanism, protocol.ordering, protocol.order) == (
        "sequential", "fixed", []
    )
    assert protocol.max_rounds == 3
    assert (config.agreement.authority, config.agreement.resolution) == (
        "judge_based", "argument_evaluation"
    )


def test_config8_sequential_three_rounds_exact_messages():
    config = _config8()
    f_node, nf_node, judge_node = config.participants.nodes
    debate = Debate()
    transcript = _run(config, debate)

    p1 = TURN_PROMPT_WITH_TASK.format(round=1)
    f = lambda r, t: _u(f"[Round {r}] {F_NAME}: {t}")  # noqa: E731
    nf = lambda r, t: _u(f"[Round {r}] {NF_NAME}: {t}")  # noqa: E731

    expected = [
        # Round 1: F opens on the task; NF already sees F's same-round turn.
        [_sys(f_node), _u(p1)],
        [_sys(nf_node), f(1, "F1")],
        # Round 2: own prior turns replayed as assistant, the other's attributed.
        [_sys(f_node), _u(p1), _a("F1"), nf(1, "NF1")],
        [_sys(nf_node), f(1, "F1"), _a("NF1"), f(2, "F2")],
        # Round 3.
        [_sys(f_node), _u(p1), _a("F1"), nf(1, "NF1"), _a("F2"), nf(2, "NF2")],
        [_sys(nf_node), f(1, "F1"), _a("NF1"), f(2, "F2"), _a("NF2"), f(3, "F3")],
    ]
    assert [c.messages for c in debate.debater_calls()] == expected

    # The judge is never scheduled as a debater turn; it is called once, last.
    assert len(debate.calls) == 7 and debate.calls[-1].response_schema is not None
    (judge_call,) = debate.judge_calls()
    turns = [
        f"[Round {r}] {name}: {tag}{r}"
        for r in (1, 2, 3)
        for name, tag in ((F_NAME, "F"), (NF_NAME, "NF"))
    ]
    assert judge_call.messages == [
        Message(role="system", content=judge_node.system_prompt),
        _u(f"Task: {TASK}\n\nDebate transcript:\n" + "\n".join(turns)
           + f"\n\n{JUDGE_CLOSING}"),
    ]
    assert transcript.decision.decision == {"class": "NF"}
    assert transcript.errors == []


@pytest.mark.parametrize("rounds", [1, 2, 4])
def test_config8_sequential_invariants_over_n_rounds(rounds):
    debate = Debate()
    transcript = _run(_config8(max_rounds=rounds), debate)
    calls = debate.debater_calls()
    assert len(calls) == 2 * rounds
    for i, call in enumerate(calls):
        tag, other_tag = ("F", "NF") if i % 2 == 0 else ("NF", "F")
        other_name = NF_NAME if tag == "F" else F_NAME
        msgs = call.messages
        # Entry node: the task travels in the system prompt.
        assert msgs[0].role == "system" and msgs[0].content.endswith(f"Task: {TASK}")
        roles = [m.role for m in msgs[1:]]
        # Never opens on / stacks assistant turns; always ends on a user turn.
        assert roles[0] == "user" and roles[-1] == "user"
        assert all(not (a == b == "assistant") for a, b in zip(roles, roles[1:]))
        # Own prior turns, in order.
        own_done = i // 2
        assert [m.content for m in msgs if m.role == "assistant"] == [
            f"{tag}{n}" for n in range(1, own_done + 1)
        ]
        # Every turn the other debater produced before this call, attributed.
        other_done = own_done + (1 if tag == "NF" else 0)
        assert [m.content for m in msgs if m.content.startswith("[Round")] == [
            f"[Round {n}] {other_name}: {other_tag}{n}"
            for n in range(1, other_done + 1)
        ]
    (judge_call,) = debate.judge_calls()
    context = judge_call.messages[-1].content
    for n in range(1, rounds + 1):
        assert f"[Round {n}] {F_NAME}: F{n}" in context
        assert f"[Round {n}] {NF_NAME}: NF{n}" in context
    assert transcript.rounds == rounds


# ---------------------------------------------------------------------------
# Simultaneous and chain variants
# ---------------------------------------------------------------------------


def test_simultaneous_sees_only_previous_rounds_and_replays_own_turn_first():
    config = _config8(mechanism="simultaneous", max_rounds=2)
    f_node, nf_node, _judge = config.participants.nodes
    debate = Debate()
    _run(config, debate)

    p1 = TURN_PROMPT_WITH_TASK.format(round=1)
    assert [c.messages for c in debate.debater_calls()] == [
        # Round 1: nobody sees anyone (concurrent).
        [_sys(f_node), _u(p1)],
        [_sys(nf_node), _u(p1)],
        # Round 2: own round-1 turn first (spoken before hearing the other),
        # then the other's round-1 turn; no round-2 turn is visible.
        [_sys(f_node), _u(p1), _a("F1"), _u(f"[Round 1] {NF_NAME}: NF1")],
        [_sys(nf_node), _u(p1), _a("NF1"), _u(f"[Round 1] {F_NAME}: F1")],
    ]


def _chain_config(max_rounds: int = 2) -> MADConfig:
    nodes = [
        ParticipantNode(id=i, label=i.upper(), roles=["debater"], system_prompt=f"You are {i}.")
        for i in ("a", "b", "c")
    ]
    topology = templates.build_topology("chain", ["a", "b", "c"]).model_copy(
        update={"entry_nodes": ["a"]}
    )
    config = _config8()
    config.participants.nodes = nodes
    config.interaction.topology = topology
    config.interaction.protocol.max_rounds = max_rounds
    config.agreement = config.agreement.model_copy(
        update={"authority": "collective", "resolution": "majority_vote",
                "output_schema": None}
    )
    return _bind(config)


def test_chain_topology_sees_only_predecessors_and_non_entry_nodes_get_context():
    debate = Debate()
    _run(_chain_config(), debate)
    by_node = {"a": [], "b": [], "c": []}
    for call in debate.debater_calls():
        by_node[_speaker_of(call.messages).split()[-1]].append(call.messages)

    p = lambda r, task: TURN_PROMPT_WITH_TASK.format(round=r) if task else (  # noqa: E731
        TURN_PROMPT_NO_TASK.format(round=r)
    )
    sys = lambda i, task="": Message(  # noqa: E731
        role="system", content=f"You are {i}." + (f"\n\nTask: {TASK}" if task else "")
    )
    # a (entry, no predecessors): only its own turns, each after its round prompt.
    assert by_node["a"] == [
        [sys("a", TASK), _u(p(1, True))],
        [sys("a", TASK), _u(p(1, True)), _a("You are a1"), _u(p(2, True))],
    ]
    # b (non-entry): no task line, but a's turns arrive attributed.
    assert by_node["b"] == [
        [sys("b"), _u("[Round 1] A: You are a1")],
        [sys("b"), _u("[Round 1] A: You are a1"), _a("You are b1"),
         _u("[Round 2] A: You are a2")],
    ]
    # c sees b only, never a.
    assert by_node["c"] == [
        [sys("c"), _u("[Round 1] B: You are b1")],
        [sys("c"), _u("[Round 1] B: You are b1"), _a("You are c1"),
         _u("[Round 2] B: You are b2")],
    ]


# ---------------------------------------------------------------------------
# Judge context
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("authority", ["judge_based", "hybrid"])
def test_judge_context_has_task_all_turns_labels_and_failed_turns(authority):
    config = _config8(max_rounds=2)
    config.agreement = config.agreement.model_copy(update={"authority": authority})
    judge_node = config.participants.nodes[2]
    judge_node.persona.stance = "Impartial."
    # NF's second turn fails after retries.
    debate = Debate(fail={("NF", 2)})
    transcript = _run(config, debate, retry_policy=RetryPolicy(max_attempts=1))
    assert [(e.node_id, e.round_index) for e in transcript.errors] == [(NF_ID, 1)]

    (judge_call,) = debate.judge_calls()
    system, context = judge_call.messages
    # The judge's own prompt + persona; no Task line (it is in the context).
    assert system == Message(
        role="system", content=f"{judge_node.system_prompt}\n\nStance: Impartial."
    )
    assert context == _u(
        f"Task: {TASK}\n\nDebate transcript:\n"
        f"[Round 1] {F_NAME}: F1\n"
        f"[Round 1] {NF_NAME}: NF1\n"
        f"[Round 2] {F_NAME}: F2\n"
        f"[Round 2] {NF_NAME}: {FAILED_TURN_NOTE}\n\n"
        f"{JUDGE_CLOSING}"
    )
    # Ids never leak into the judge context when labels exist.
    assert F_ID not in context.content and NF_ID not in context.content


# ---------------------------------------------------------------------------
# Summarizer input
# ---------------------------------------------------------------------------


def test_summarizer_gets_attributed_history_and_debaters_keep_own_turns():
    config = _bind(templates.chateval_s3())

    def respond(messages, model, params, schema):
        system = _system(messages)
        if system.startswith("Summarize the debate so far concisely."):
            return "SUMMARY"
        for name in ("meticulous", "pragmatic", "open-minded"):
            if name in system:
                return f"{name} view"
        return "summarizer turn"

    client = MockModelClient(responder=respond)
    run_debate(config, {"response": "ok"}, _registry(client), sleep=_no_sleep)

    summarize_calls = [
        c for c in client.calls
        if _system(c.messages).startswith("Summarize the debate so far concisely.")
    ]
    assert summarize_calls, "the summarizer callable was never used"
    # The summarizer node's persona rides along with the default instruction.
    assert "Background: A summarizer" in _system(summarize_calls[0].messages)
    inputs = [c.messages[1:] for c in summarize_calls]
    # The summarizer node's own round-1 turn: all three debaters, attributed.
    assert inputs[0] == [
        _u("[Round 1] Alice: meticulous view"),
        _u("[Round 1] Bob: pragmatic view"),
        _u("[Round 1] Carol: open-minded view"),
    ]
    # Alice's round-2 context: Bob's and Carol's round-1 turns, attributed
    # (her own turn is not summarized) ...
    assert [
        _u("[Round 1] Bob: pragmatic view"),
        _u("[Round 1] Carol: open-minded view"),
    ] in inputs
    # ... and Alice receives her own turn verbatim, then the summary.
    alice_r2 = [
        c for c in client.calls
        if "meticulous" in _system(c.messages) and len(c.messages) > 2
    ][0]
    assert alice_r2.messages[1:] == [
        _u(TURN_PROMPT_WITH_TASK.format(round=1)),
        _a("meticulous view"),
        _u("SUMMARY"),
    ]


# ---------------------------------------------------------------------------
# Attribution with colliding / blank labels
# ---------------------------------------------------------------------------


def test_speaker_names_disambiguate_colliding_and_blank_labels():
    nodes = [
        ParticipantNode(id="a", label="Debater"),
        ParticipantNode(id="b", label="debater "),
        ParticipantNode(id="c", label="Judge"),
        ParticipantNode(id="d", label=" "),
    ]
    assert speaker_names(nodes) == {
        "a": "Debater (a)",
        "b": "debater (b)",
        "c": "Judge",
        "d": "d",
    }


def test_colliding_labels_keep_speakers_apart_in_context():
    nodes = [ParticipantNode(id=i, label="Debater") for i in ("x", "y", "z")]
    graph = DebateGraph(nodes=["x", "y", "z"], edges=[("x", "z"), ("y", "z")])
    history = [
        HistoryRecord(node_id="x", round_index=0, content="yes"),
        HistoryRecord(node_id="y", round_index=0, content="no"),
    ]
    assembled = assemble_context(
        history, node="z", format_spec=_config8().interaction.format, graph=graph,
        speakers=speaker_names(nodes),
    )
    assert assembled.messages == [
        _u("[Round 1] Debater (x): yes"),
        _u("[Round 1] Debater (y): no"),
    ]
