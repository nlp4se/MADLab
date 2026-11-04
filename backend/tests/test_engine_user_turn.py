"""Every model call carries at least one non-system message (task 11.11).

A first-round turn with no visible history used to assemble a system-only
message list, which Anthropic rejects ("requires at least one non-system
message"). The orchestrator now routes every call (debater turns, judge,
summarizer) through :func:`mad.engine.format.ensure_user_turn`, which appends a
round prompt when no user/assistant turn exists. These tests cover the helper,
the first-round shapes for entry / non-entry nodes in sequential and
simultaneous rounds, the summarized path, the judge and summarizer callables,
the empty-system-prompt case, and an Anthropic-like client that rejects
system-only lists.

Validates: Requirements 9.1, 9.2, 9.5
"""

from __future__ import annotations

from typing import Optional

from mad.engine.format import (
    TURN_PROMPT_NO_TASK,
    TURN_PROMPT_WITH_TASK,
    assemble_context,
    ensure_user_turn,
    turn_prompt,
)
from mad.engine.graph import DebateGraph
from mad.engine.orchestrator import (
    RetryPolicy,
    _make_judge_fn,
    _make_summarizer,
    run_debate,
)
from mad.engine.transcript import Transcript
from mad.providers.base import Message, MockModelClient, ModelResponse
from mad.providers.registry import ProviderConfig, ProviderRegistry
from mad.taxonomy import templates
from mad.taxonomy.schema import (
    Agreement,
    ContentSpec,
    Format,
    Interaction,
    MADConfig,
    Participants,
    ParticipantNode,
    Protocol,
)
from mad.taxonomy.templates import fully_connected_topology

ROUND_1_WITH_TASK = TURN_PROMPT_WITH_TASK.format(round=1)
ROUND_1_NO_TASK = TURN_PROMPT_NO_TASK.format(round=1)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _no_sleep(_seconds: float) -> None:
    """No-op sleep so retry/backoff never waits."""


class AnthropicLikeClient:
    """Mock client that rejects lists without a non-blank non-system message.

    Mirrors Anthropic's request validation; otherwise delegates to a
    :class:`MockModelClient` (whose ``calls`` log only accepted requests).
    """

    def __init__(self, responder=None) -> None:
        self.inner = MockModelClient(responder=responder or (lambda *a: "F"))
        self.rejected = 0

    @property
    def calls(self):
        return self.inner.calls

    def complete(
        self,
        messages: list[Message],
        model: str,
        params: Optional[dict] = None,
        response_schema: Optional[dict] = None,
    ) -> ModelResponse:
        if not any(m.role != "system" and m.content.strip() for m in messages):
            self.rejected += 1
            raise RuntimeError(
                "AnthropicException - Anthropic requires at least one "
                "non-system message."
            )
        return self.inner.complete(messages, model, params, response_schema)


def _registry(client) -> ProviderRegistry:
    return ProviderRegistry(
        providers=[ProviderConfig(id="mock", name="Mock", kind="mock", models=["m"])],
        client_factory=lambda _config: client,
    )


def _bind(config: MADConfig) -> MADConfig:
    for node in config.participants.nodes:
        node.base_model.provider_id = "mock"
        if not node.base_model.model_key:
            node.base_model.model_key = "m"
    return config


def _config(
    *,
    mechanism: str = "sequential",
    entry_nodes=None,
    max_rounds: int = 1,
    prompts: Optional[dict[str, str]] = None,
    template: str = "Classify: {{x}}",
) -> MADConfig:
    """Two fully connected debaters ``a``/``b`` (prompt ``You are <id>.``)."""
    prompts = prompts if prompts is not None else {"a": "You are a.", "b": "You are b."}
    nodes = [
        ParticipantNode(id=i, label=i.upper(), roles=["debater"], system_prompt=p)
        for i, p in prompts.items()
    ]
    ids = [n.id for n in nodes]
    topology = fully_connected_topology(ids).model_copy(update={"entry_nodes": entry_nodes})
    config = MADConfig(
        name="user-turn",
        participants=Participants(nodes=nodes),
        interaction=Interaction(
            topology=topology,
            protocol=Protocol(
                mechanism=mechanism, max_rounds=max_rounds, ordering="fixed", order=ids
            ),
            format=Format(content=ContentSpec(strategy="verbatim")),
        ),
        agreement=Agreement(authority="collective", resolution="majority_vote"),
    )
    config.input_spec.template = template
    config.input_spec.placeholders = ["x"] if "{{x}}" in template else []
    return _bind(config)


def _calls_for(client, prompt: str):
    """Recorded calls whose system text starts with ``prompt``."""
    return [
        c for c in client.calls
        if any(m.role == "system" and m.content.startswith(prompt) for m in c.messages)
    ]


# ---------------------------------------------------------------------------
# Helper: wording + guarantee
# ---------------------------------------------------------------------------


def test_turn_prompt_wording_is_one_based_and_task_aware():
    assert turn_prompt(0, has_task=True) == "Round 1. Respond to the task above."
    assert turn_prompt(2, has_task=False) == (
        "Round 3. Give your contribution for this round."
    )


def test_ensure_user_turn_appends_to_system_only_list():
    system = Message(role="system", content="You are a.\n\nTask: t")
    out = ensure_user_turn([system], round_index=0, has_task=True)
    assert out == [system, Message(role="user", content=ROUND_1_WITH_TASK)]


def test_ensure_user_turn_handles_empty_list_and_blank_turns():
    assert ensure_user_turn([], round_index=0, has_task=False) == [
        Message(role="user", content=ROUND_1_NO_TASK)
    ]
    blank = [Message(role="system", content="s"), Message(role="user", content="  ")]
    assert ensure_user_turn(blank, round_index=1, has_task=False) == [
        Message(role="system", content="s"),
        Message(role="user", content=TURN_PROMPT_NO_TASK.format(round=2)),
    ]


def test_ensure_user_turn_leaves_lists_with_a_user_turn_untouched():
    messages = [Message(role="system", content="s"), Message(role="user", content="hi")]
    assert ensure_user_turn(messages, round_index=0, has_task=True) is messages


# ---------------------------------------------------------------------------
# Root cause: the format layer assembles a system-only list on round 1
# ---------------------------------------------------------------------------


def test_round_one_first_speaker_context_is_system_only_and_rejected():
    config = _config()
    assembled = assemble_context(
        history=[], node="a", format_spec=config.interaction.format,
        graph=DebateGraph.from_config(config), system_prompt="You are a.",
    )
    assert [m.role for m in assembled.messages] == ["system"]
    client = AnthropicLikeClient()
    try:
        client.complete(assembled.messages, "m")
    except RuntimeError as exc:
        assert "non-system" in str(exc)
    else:  # pragma: no cover - the mock must reject this shape
        raise AssertionError("Anthropic-like client accepted a system-only list")


# ---------------------------------------------------------------------------
# First-round messages through run_debate
# ---------------------------------------------------------------------------


def test_sequential_round_one_first_speaker_gets_task_prompt():
    client = AnthropicLikeClient()
    transcript = run_debate(_config(), {"x": "req"}, _registry(client), sleep=_no_sleep)

    first = client.calls[0].messages
    # System prompt unchanged (Task line stays in it); a round prompt follows.
    assert first == [
        Message(role="system", content="You are a.\n\nTask: Classify: req"),
        Message(role="user", content=ROUND_1_WITH_TASK),
    ]
    # The second speaker already sees a's turn: no prompt appended.
    second = client.calls[1].messages
    assert [m.role for m in second] == ["system", "user"]
    assert second[1].content == "[Round 1] A: F"  # attributed (task 11.14)
    assert transcript.errors == [] and client.rejected == 0


def test_non_entry_node_without_history_gets_neutral_prompt():
    client = AnthropicLikeClient()
    run_debate(
        _config(mechanism="simultaneous", entry_nodes=["a"]), {"x": "req"},
        _registry(client), sleep=_no_sleep,
    )
    (a_call,) = _calls_for(client, "You are a.")
    (b_call,) = _calls_for(client, "You are b.")
    assert a_call.messages[-1] == Message(role="user", content=ROUND_1_WITH_TASK)
    assert b_call.messages == [
        Message(role="system", content="You are b."),
        Message(role="user", content=ROUND_1_NO_TASK),
    ]


def test_simultaneous_round_one_prompts_everyone_round_two_sees_history():
    client = AnthropicLikeClient(responder=lambda messages, *a: (
        "F" if "You are a." in messages[0].content else "NF"
    ))
    transcript = run_debate(
        _config(mechanism="simultaneous", max_rounds=2), {"x": "req"},
        _registry(client), sleep=_no_sleep,
    )
    round_one, round_two = client.calls[:2], client.calls[2:]
    assert all(c.messages[-1].content == ROUND_1_WITH_TASK for c in round_one)
    assert all(c.messages[0].content.endswith("Task: Classify: req") for c in round_one)
    # Round 2: each sees the other's round-1 turn, so no fallback prompt.
    assert [c.messages[-1].content for c in round_two] == [
        "[Round 1] B: NF",
        "[Round 1] A: F",
    ]
    assert transcript.rounds == 2 and transcript.errors == []


def test_empty_system_prompt_still_sends_a_user_turn():
    client = AnthropicLikeClient()
    transcript = run_debate(
        _config(prompts={"a": "", "b": ""}, template=""), {},
        _registry(client), sleep=_no_sleep,
    )
    assert client.calls[0].messages == [Message(role="user", content=ROUND_1_NO_TASK)]
    assert transcript.errors == [] and client.rejected == 0


def test_summarized_path_with_summarizer_completes_on_anthropic_like_client():
    """ChatEval S3: simultaneous debaters + summarizer + summarized content."""
    config = _bind(templates.chateval_s3())
    client = AnthropicLikeClient(responder=lambda *a: "good")
    transcript = run_debate(
        config, {"response": "The answer is correct."}, _registry(client), sleep=_no_sleep,
    )
    assert client.rejected == 0
    assert transcript.errors == []
    assert transcript.decision is not None and transcript.decision.decision == "good"
    # Round-1 debaters had nothing to summarize; they got the round prompt.
    prompted = [c for c in client.calls if c.messages[-1].content == ROUND_1_WITH_TASK]
    assert len(prompted) == 3


# ---------------------------------------------------------------------------
# Judge / summarizer callables
# ---------------------------------------------------------------------------


def test_judge_call_keeps_its_context_message():
    config = _bind(templates.re_binary_debate())
    client = AnthropicLikeClient(responder=lambda m, model, p, schema: (
        '{"class": "NF"}' if schema is not None else "argument"
    ))
    transcript = run_debate(
        config, {"requirement": "Login must be fast"}, _registry(client), sleep=_no_sleep,
    )
    (judge_call,) = [c for c in client.calls if c.response_schema is not None]
    assert judge_call.messages[-1].role == "user"
    assert judge_call.messages[-1].content.startswith("Task: ")
    assert transcript.decision.structured == {"class": "NF"}


def test_judge_and_summarizer_get_the_guarantee_on_empty_input():
    config = _bind(templates.chateval_s3())
    judge_config = _bind(templates.re_binary_debate())
    client = AnthropicLikeClient(responder=lambda *a: "ok")
    registry = _registry(client)
    policy = RetryPolicy(max_attempts=1)

    summarize = _make_summarizer(
        config, DebateGraph.from_config(config), registry, policy,
        Transcript(config_id=config.id, config_name=config.name), _no_sleep,
    )
    assert summarize([]) == "ok"
    assert client.calls[-1].messages[-1] == Message(role="user", content=ROUND_1_NO_TASK)

    judge_fn = _make_judge_fn(
        judge_config, DebateGraph.from_config(judge_config), registry, policy,
        Transcript(config_id=judge_config.id, config_name=judge_config.name), _no_sleep,
    )
    judge_fn("")
    assert client.calls[-1].messages[-1] == Message(role="user", content=ROUND_1_NO_TASK)
    assert client.rejected == 0


# ---------------------------------------------------------------------------
# The reported scenario: an Anthropic participant on the RE binary debate
# ---------------------------------------------------------------------------


def test_re_binary_debate_completes_on_anthropic_like_client():
    config = _bind(templates.re_binary_debate())
    client = AnthropicLikeClient(responder=lambda m, model, p, schema: (
        '{"class": "F"}' if schema is not None else "my argument"
    ))
    transcript = run_debate(
        config,
        {"requirement": "The system shall have a MDI form that allows for the "
                        "viewing of the graph and the data table."},
        _registry(client), sleep=_no_sleep,
    )
    assert client.rejected == 0
    assert transcript.errors == []
    assert len([m for m in transcript.messages if m.role == "debater"]) == 4
    assert transcript.decision.decision == {"class": "F"}
