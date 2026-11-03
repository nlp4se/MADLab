"""Gold-case *engine* tests — run the reference MAD systems end-to-end.

Task 3.6 (design.md "Testing Strategy" → "Gold-case tests (Req 4.4)"): drive the
two reference ("gold") configurations from :mod:`mad.taxonomy.templates` through
the orchestrator (:func:`mad.engine.orchestrator.run_debate`) with a
deterministic, offline :class:`~mad.providers.base.MockModelClient` wired via a
:class:`~mad.providers.registry.ProviderRegistry`, and assert:

* **RE binary debate** — the transcript structure (two debaters × ``max_rounds``
  turns plus exactly one judge turn) and the final decision (``judge_based`` /
  ``argument_evaluation`` with a schema-valid ``{"class": "F"|"NF"}``).
* **ChatEval S1/S2/S3** — each runs and produces a ``collective`` /
  ``majority_vote`` decision over the three debaters, and the three strategies
  differ at *runtime* in exactly the documented attributes (CSUR Table 3):
    - S1 (One-by-One): sequential activation → debater turns appear in the
      declared order ``alice → bob → carol`` within each round;
    - S2 (Simultaneous-Talk): same three debaters, no summarizer, no summarized
      context;
    - S3 (+ Summarizer): adds a summarizer node that produces a turn each round
      and the format layer compresses history (``summarized`` content),
      observable via the summarizer's recorded turns.

The static construction/validation and the config-level S1/S2/S3 attribute-delta
assertions live in ``test_templates_and_gold.py`` (task 1.4); this module is the
behavioural counterpart — it proves the gold cases *execute* and that the
documented attribute differences manifest in the produced transcripts.

Fully offline / reproducible: no network, no litellm — the registry resolves
every binding to an injected mock client.

Validates: Requirements 4.4, 12.5
"""

from __future__ import annotations

import pytest

from mad.engine.orchestrator import run_debate
from mad.engine.transcript import Transcript
from mad.providers.base import Message, MockModelClient
from mad.providers.registry import ProviderConfig, ProviderRegistry
from mad.taxonomy import templates
from mad.taxonomy.schema import MADConfig


# ---------------------------------------------------------------------------
# Offline wiring helpers (mirrors test_engine_orchestrator.py)
# ---------------------------------------------------------------------------


def _no_sleep(_seconds: float) -> None:
    """A no-op sleep so retry/backoff never actually waits during tests."""


def _registry(client) -> ProviderRegistry:
    """Registry whose single ``mock`` provider always resolves to ``client``."""
    return ProviderRegistry(
        providers=[ProviderConfig(id="mock", name="Mock", kind="mock", models=["m"])],
        client_factory=lambda _config: client,
    )


def _bind(config: MADConfig, provider_id: str = "mock") -> MADConfig:
    """Bind every node's base model to ``provider_id`` so resolution succeeds.

    The gold configs leave ``base_model.provider_id`` unset (bound at run time);
    tests pin it to the injected mock provider and give every node a model key.
    """
    for node in config.participants.nodes:
        node.base_model.provider_id = provider_id
        if not node.base_model.model_key:
            node.base_model.model_key = "m"
    return config


def _system_text(messages: list[Message]) -> str:
    """Concatenate the system messages' content (for responder branching)."""
    return " ".join(m.content for m in messages if m.role == "system")


# ---------------------------------------------------------------------------
# Gold case 1: RE binary debate (judge_based + output_schema)
# ---------------------------------------------------------------------------


def _re_responder(messages, model, params, response_schema):
    """A judge returns a schema-valid class; debaters argue their stance."""
    if response_schema is not None:  # the judge call carries the output schema
        return '{"class": "NF"}'
    return "I present my argument for this requirement."


def test_re_binary_gold_case_transcript_structure_and_decision():
    """RE binary runs end-to-end with the expected transcript + judge decision."""
    config = _bind(templates.re_binary_debate())
    client = MockModelClient(responder=_re_responder)

    transcript = run_debate(
        config, {"requirement": "The system shall respond within 2 seconds"},
        _registry(client), sleep=_no_sleep,
    )

    assert isinstance(transcript, Transcript)
    # max_rounds == 2 and no early-stop (judge_based is not a consensus stop).
    assert transcript.rounds == 2

    # Two debaters × two rounds = 4 debater turns; exactly one judge turn.
    debater_turns = [m for m in transcript.messages if m.role == "debater"]
    judge_turns = [m for m in transcript.messages if m.role == "judge"]
    assert len(debater_turns) == 4
    assert len(judge_turns) == 1

    # Debater turns alternate stance-by-stance in the declared sequential order.
    assert [m.node_id for m in debater_turns] == [
        "functional-debater",
        "non-functional-debater",
        "functional-debater",
        "non-functional-debater",
    ]
    # Both rounds executed (0 and 1).
    assert sorted({m.round_index for m in debater_turns}) == [0, 1]

    # The decision is the judge's schema-constrained classification.
    decision = transcript.decision
    assert decision is not None
    assert decision.authority == "judge_based"
    assert decision.resolution == "argument_evaluation"
    assert decision.structured == {"class": "NF"}
    assert decision.decision == {"class": "NF"}
    assert decision.undecided is False

    # Usage rolled up additively over every recorded call (Req 9.4 wiring).
    per_call_total = sum(m.usage.total_tokens for m in transcript.messages)
    assert transcript.usage.total_tokens == per_call_total
    assert transcript.usage.total_tokens > 0

    # Clean run: no recoverable errors.
    assert transcript.errors == []


def test_re_binary_judge_sees_output_schema_and_both_stances():
    """The judge call carries the output schema; debaters see their stances."""
    config = _bind(templates.re_binary_debate())
    client = MockModelClient(responder=_re_responder)

    run_debate(config, {"requirement": "Login must be fast"},
               _registry(client), sleep=_no_sleep)

    schema_calls = [c for c in client.calls if c.response_schema is not None]
    assert len(schema_calls) == 1  # only the judge receives the output schema
    assert schema_calls[0].response_schema["properties"]["class"]["enum"] == ["F", "NF"]

    # Both debater stances reach the model as system prompts during the debate.
    system_blobs = [_system_text(c.messages).lower() for c in client.calls]
    assert any("requirement is functional (f)" in s for s in system_blobs)
    assert any("requirement is non-functional (nf)" in s for s in system_blobs)


# ---------------------------------------------------------------------------
# Gold case 2: ChatEval S1/S2/S3 — behavioural differences at run time
# ---------------------------------------------------------------------------


def _vote_responder(vote: str):
    """A responder that makes every debater emit the same categorical ``vote``.

    Summarizer turns (no explicit stance) fall through to the same reply; the
    collective majority_vote resolution keys off the debaters' content.
    """

    def responder(messages, model, params, response_schema):
        return vote

    return responder


def _run_chateval(factory, vote: str = "good") -> tuple[Transcript, MockModelClient]:
    """Run a ChatEval gold case over one instance and return (transcript, client)."""
    config = _bind(factory())
    client = MockModelClient(responder=_vote_responder(vote))
    transcript = run_debate(
        config, {"response": "The answer is well-structured and correct."},
        _registry(client), sleep=_no_sleep,
    )
    return transcript, client


def _debater_turns(transcript: Transcript):
    return [m for m in transcript.messages if m.role == "debater"]


def _summarizer_turns(transcript: Transcript):
    return [m for m in transcript.messages if m.role == "summarizer"]


@pytest.mark.parametrize("factory", [templates.chateval_s1, templates.chateval_s2])
def test_chateval_s1_s2_collective_decision_over_three_debaters(factory):
    """S1 and S2: three debaters, no summarizer, collective majority_vote."""
    transcript, _ = _run_chateval(factory, vote="good")

    assert transcript.rounds == 2
    # 3 debaters × 2 rounds = 6 debater turns; no summarizer in S1/S2.
    assert len(_debater_turns(transcript)) == 6
    assert _summarizer_turns(transcript) == []

    decision = transcript.decision
    assert decision is not None
    assert decision.authority == "collective"
    assert decision.resolution == "majority_vote"
    # Unanimous "good" vote -> confident majority decision.
    assert decision.decision == "good"
    assert decision.undecided is False
    assert transcript.errors == []


def test_chateval_s1_activates_debaters_in_declared_sequential_order():
    """S1 (One-by-One) is sequential: order is alice -> bob -> carol each round."""
    transcript, _ = _run_chateval(templates.chateval_s1)

    round0 = [m.node_id for m in transcript.messages_in_round(0) if m.role == "debater"]
    round1 = [m.node_id for m in transcript.messages_in_round(1) if m.role == "debater"]
    assert round0 == ["alice", "bob", "carol"]
    assert round1 == ["alice", "bob", "carol"]


def test_chateval_s3_adds_summarizer_turns_and_summarized_context():
    """S3 (+ Summarizer): a summarizer turn each round; history is summarized."""
    transcript, client = _run_chateval(templates.chateval_s3)

    assert transcript.rounds == 2
    # 3 debaters × 2 rounds = 6 debater turns.
    assert len(_debater_turns(transcript)) == 6
    # The summarizer is activated once per round (hybrid phase).
    summarizer_turns = _summarizer_turns(transcript)
    assert len(summarizer_turns) == 2
    assert {m.node_id for m in summarizer_turns} == {"summarizer"}
    # One summarizer turn per round.
    assert sorted(m.round_index for m in summarizer_turns) == [0, 1]

    decision = transcript.decision
    assert decision is not None
    assert decision.authority == "collective"
    assert decision.resolution == "majority_vote"
    # The collective decision excludes the summarizer (debaters-only aggregate).
    assert decision.decision == "good"
    assert transcript.errors == []


def test_chateval_s2_vs_s3_differ_only_by_the_summarizer_at_runtime():
    """At run time, S3 differs from S2 by the presence of summarizer turns.

    Both run the same three debaters simultaneously and reach the same
    collective majority_vote decision; the ONLY observable transcript delta is
    S3's per-round summarizer turns (the documented Table-3 differentiator:
    + Summarizer node, + its edges, + summarized content).
    """
    s2_transcript, _ = _run_chateval(templates.chateval_s2)
    s3_transcript, _ = _run_chateval(templates.chateval_s3)

    # Identical debater participation and identical decision.
    s2_debaters = {m.node_id for m in _debater_turns(s2_transcript)}
    s3_debaters = {m.node_id for m in _debater_turns(s3_transcript)}
    assert s2_debaters == s3_debaters == {"alice", "bob", "carol"}
    assert len(_debater_turns(s2_transcript)) == len(_debater_turns(s3_transcript)) == 6
    assert s2_transcript.decision.decision == s3_transcript.decision.decision == "good"

    # The delta: S2 has no summarizer turns, S3 has exactly one per round.
    assert _summarizer_turns(s2_transcript) == []
    assert len(_summarizer_turns(s3_transcript)) == 2


def test_all_gold_cases_run_without_errors():
    """Smoke: every registered gold case executes end-to-end and decides."""
    for key, factory in templates.gold_cases().items():
        config = _bind(factory())

        if config.agreement.authority == "judge_based":
            client = MockModelClient(responder=_re_responder)
            instance = {"requirement": "The system shall be available 99.9% of the time"}
        else:
            client = MockModelClient(responder=_vote_responder("good"))
            instance = {"response": "A concise, correct answer."}

        transcript = run_debate(config, instance, _registry(client), sleep=_no_sleep)

        assert transcript.rounds >= 1, f"{key} executed no rounds"
        assert transcript.decision is not None, f"{key} produced no decision"
        assert transcript.errors == [], f"{key} recorded unexpected errors"
