"""Unit tests for the format layer (task 3.3).

Cover short-term memory assembly M(t) with topology filtering, the content
transform m̃=f(m) (verbatim / summarized / other), metadata-signal rendering,
and the syntax / memory under-development gating.

Validates: Requirements 2.6, 2.7, 2.8
"""

import pytest

from mad.engine import (
    AssembledContext,
    DebateGraph,
    HistoryRecord,
    assemble_context,
    render_message,
)
from mad.errors import UnderDevelopment
from mad.providers.base import Message
from mad.taxonomy.schema import ContentSpec, Edge, Format


# ---------------------------------------------------------------------------
# Graph helpers
# ---------------------------------------------------------------------------


def _chain_graph() -> DebateGraph:
    """a -> b -> c."""
    return DebateGraph(
        nodes=["a", "b", "c"],
        edges=[("a", "b"), ("b", "c")],
    )


def _fmt(
    *,
    strategy: str = "verbatim",
    metadata_signals: list[str] | None = None,
    syntax: str = "natural_language",
    memory: str = "short_term",
) -> Format:
    return Format(
        syntax=syntax,
        content=ContentSpec(
            strategy=strategy,
            metadata_signals=metadata_signals or [],
        ),
        memory=memory,
    )


def _history() -> list[HistoryRecord]:
    return [
        HistoryRecord(node_id="a", round_index=0, content="A speaks"),
        HistoryRecord(node_id="b", round_index=0, content="B speaks"),
    ]


# ---------------------------------------------------------------------------
# Short-term memory assembly + topology filtering
# ---------------------------------------------------------------------------


def test_short_term_assembles_predecessor_history_with_system_prompt_in_order():
    graph = _chain_graph()
    history = [
        HistoryRecord(node_id="a", round_index=0, content="first from a"),
        HistoryRecord(node_id="b", round_index=0, content="first from b"),
        HistoryRecord(node_id="a", round_index=1, content="second from a"),
    ]

    # b's predecessor is a -> b sees only a's turns, in order.
    result = assemble_context(
        history, node="b", format_spec=_fmt(), graph=graph,
        system_prompt="You are agent B.",
    )

    assert isinstance(result, AssembledContext)
    assert result.messages[0] == Message(role="system", content="You are agent B.")
    assert result.messages[1:] == [
        Message(role="user", content="first from a"),
        Message(role="user", content="second from a"),
    ]
    assert result.notes == []


def test_topology_filtering_chain_c_sees_only_b_not_a():
    graph = _chain_graph()
    history = _history()  # a and b have spoken

    # c's only predecessor is b; it must NOT see a's message directly.
    result = assemble_context(history, node="c", format_spec=_fmt(), graph=graph)

    contents = [m.content for m in result.messages]
    assert "B speaks" in contents
    assert "A speaks" not in contents
    assert all(m.role == "user" for m in result.messages)


def test_agent_does_not_see_its_own_turns():
    graph = _chain_graph()
    history = [
        HistoryRecord(node_id="a", round_index=0, content="A speaks"),
        HistoryRecord(node_id="b", round_index=0, content="B speaks"),
    ]
    # b's predecessor is a, so b never sees its own "B speaks".
    result = assemble_context(history, node="b", format_spec=_fmt(), graph=graph)
    contents = [m.content for m in result.messages]
    assert contents == ["A speaks"]


def test_no_system_prompt_omits_system_message():
    graph = _chain_graph()
    result = assemble_context(_history(), node="b", format_spec=_fmt(), graph=graph)
    assert all(m.role != "system" for m in result.messages)


# ---------------------------------------------------------------------------
# Content transform: verbatim
# ---------------------------------------------------------------------------


def test_verbatim_passes_content_through_unchanged():
    graph = _chain_graph()
    history = [HistoryRecord(node_id="a", round_index=0, content="unchanged text")]
    result = assemble_context(
        history, node="b", format_spec=_fmt(strategy="verbatim"), graph=graph
    )
    assert [m.content for m in result.messages] == ["unchanged text"]


# ---------------------------------------------------------------------------
# Content transform: summarized
# ---------------------------------------------------------------------------


def test_summarized_with_injected_summarizer_replaces_history():
    graph = _chain_graph()
    history = [
        HistoryRecord(node_id="a", round_index=0, content="long argument one"),
        HistoryRecord(node_id="a", round_index=1, content="long argument two"),
    ]

    captured: dict[str, list[Message]] = {}

    def summarizer(messages: list[Message]) -> str:
        captured["messages"] = messages
        return "SUMMARY"

    result = assemble_context(
        history, node="b", format_spec=_fmt(strategy="summarized"), graph=graph,
        summarizer=summarizer,
    )

    # The whole visible-history block is replaced by a single summary message.
    assert [m.content for m in result.messages] == ["SUMMARY"]
    assert result.notes == []
    # The summarizer received the verbatim visible messages (both a's turns).
    assert [m.content for m in captured["messages"]] == [
        "long argument one",
        "long argument two",
    ]


def test_summarized_without_summarizer_falls_back_to_verbatim_with_note():
    graph = _chain_graph()
    history = [
        HistoryRecord(node_id="a", round_index=0, content="arg one"),
        HistoryRecord(node_id="a", round_index=1, content="arg two"),
    ]

    result = assemble_context(
        history, node="b", format_spec=_fmt(strategy="summarized"), graph=graph,
    )

    # Falls back to verbatim (no crash) and records a note.
    assert [m.content for m in result.messages] == ["arg one", "arg two"]
    assert len(result.notes) == 1
    assert "summariz" in result.notes[0].lower()
    assert "verbatim" in result.notes[0].lower()


def test_summarized_with_empty_visible_history_produces_no_block():
    graph = _chain_graph()

    def summarizer(messages: list[Message]) -> str:  # pragma: no cover - not called
        return "SUMMARY"

    # a has no predecessors -> nothing visible to summarize.
    result = assemble_context(
        [], node="a", format_spec=_fmt(strategy="summarized"), graph=graph,
        summarizer=summarizer, system_prompt="sys",
    )
    assert [m.content for m in result.messages] == ["sys"]


# ---------------------------------------------------------------------------
# Content transform: other -> under development
# ---------------------------------------------------------------------------


def test_other_strategy_raises_under_development():
    graph = _chain_graph()
    with pytest.raises(UnderDevelopment) as exc:
        assemble_context(
            _history(), node="b", format_spec=_fmt(strategy="other"), graph=graph
        )
    assert "other" in str(exc.value).lower()


# ---------------------------------------------------------------------------
# Syntax gating
# ---------------------------------------------------------------------------


def test_embeddings_syntax_raises_under_development():
    graph = _chain_graph()
    with pytest.raises(UnderDevelopment) as exc:
        assemble_context(
            _history(), node="b", format_spec=_fmt(syntax="embeddings"), graph=graph
        )
    assert "embeddings" in str(exc.value).lower()


# ---------------------------------------------------------------------------
# Memory gating
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("memory", ["long_term", "knowledge_retrieval", "parametric"])
def test_non_short_term_memory_raises_under_development(memory):
    graph = _chain_graph()
    with pytest.raises(UnderDevelopment) as exc:
        assemble_context(
            _history(), node="b", format_spec=_fmt(memory=memory), graph=graph
        )
    # The error names the offending memory scope and points to short_term.
    assert memory in str(exc.value)
    assert "short_term" in str(exc.value)


# ---------------------------------------------------------------------------
# Metadata signal rendering
# ---------------------------------------------------------------------------


def test_metadata_signal_rendered_into_context_when_configured():
    graph = _chain_graph()
    history = [
        HistoryRecord(
            node_id="a",
            round_index=0,
            content="Yes it is",
            metadata={"confidence": 0.8},
        )
    ]
    result = assemble_context(
        history,
        node="b",
        format_spec=_fmt(metadata_signals=["confidence"]),
        graph=graph,
    )
    assert result.messages[0].content == "[confidence: 0.8] Yes it is"


def test_metadata_signal_omitted_when_not_configured():
    graph = _chain_graph()
    history = [
        HistoryRecord(
            node_id="a",
            round_index=0,
            content="Yes it is",
            metadata={"confidence": 0.8},
        )
    ]
    # No metadata_signals configured -> plain content.
    result = assemble_context(history, node="b", format_spec=_fmt(), graph=graph)
    assert result.messages[0].content == "Yes it is"


def test_render_message_multiple_signals_in_order():
    rec = HistoryRecord(
        node_id="a",
        round_index=0,
        content="payload",
        metadata={"confidence": 0.9, "uncertainty": 0.1},
    )
    rendered = render_message(rec, ["uncertainty", "confidence"])
    assert rendered == "[uncertainty: 0.1] [confidence: 0.9] payload"


def test_render_message_skips_absent_signals():
    rec = HistoryRecord(
        node_id="a", round_index=0, content="payload", metadata={"confidence": 0.5}
    )
    # verifier_score requested but absent -> only confidence rendered.
    rendered = render_message(rec, ["confidence", "verifier_score"])
    assert rendered == "[confidence: 0.5] payload"


def test_render_message_empty_signals_returns_content_unchanged():
    rec = HistoryRecord(
        node_id="a", round_index=0, content="payload", metadata={"confidence": 0.5}
    )
    assert render_message(rec, []) == "payload"
