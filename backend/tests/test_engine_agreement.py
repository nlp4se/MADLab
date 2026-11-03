"""Tests for the agreement layer (:mod:`mad.engine.agreement`).

Exercise each executable resolution strategy on synthetic agent outputs, the
authority routing (collective / judge_based / hybrid / other), output_schema
parsing/validation, and the RE binary gold-case wiring. No network, no provider
construction: judge-based paths use injected stub ``judge_fn`` callables.
"""

import pytest

from mad.engine.agreement import AgreementResult, resolve_agreement
from mad.errors import ExecutionError, UnderDevelopment
from mad.taxonomy.schema import Agreement
from mad.taxonomy.templates import re_binary_debate


# ---------------------------------------------------------------------------
# majority_vote
# ---------------------------------------------------------------------------


def test_majority_vote_picks_most_common():
    agreement = Agreement(authority="collective", resolution="majority_vote")
    outputs = [
        {"node_id": "a", "vote": "F"},
        {"node_id": "b", "vote": "F"},
        {"node_id": "c", "vote": "NF"},
    ]
    result = resolve_agreement(agreement, outputs)
    assert result.decision == "F"
    assert result.undecided is False
    assert result.authority == "collective"


def test_majority_vote_falls_back_to_content_field():
    agreement = Agreement(authority="collective", resolution="majority_vote")
    outputs = [{"content": "yes"}, {"content": "yes"}, {"content": "no"}]
    assert resolve_agreement(agreement, outputs).decision == "yes"


def test_majority_vote_tie_resolved_by_tie_breaker_param():
    agreement = Agreement(
        authority="collective",
        resolution="majority_vote",
        resolution_params={"tie_breaker": "NF"},
    )
    outputs = [{"vote": "F"}, {"vote": "NF"}]
    result = resolve_agreement(agreement, outputs)
    assert result.decision == "NF"
    assert "tie_breaker" in (result.detail or "")


def test_majority_vote_tie_deterministic_first_appearance():
    agreement = Agreement(authority="collective", resolution="majority_vote")
    outputs = [{"vote": "NF"}, {"vote": "F"}]  # tie; NF appears first
    result = resolve_agreement(agreement, outputs)
    assert result.decision == "NF"
    assert "first-appearance" in (result.detail or "")


def test_majority_vote_no_answers_raises():
    agreement = Agreement(authority="collective", resolution="majority_vote")
    with pytest.raises(ExecutionError):
        resolve_agreement(agreement, [{"numeric": 1.0}])


# ---------------------------------------------------------------------------
# average
# ---------------------------------------------------------------------------


def test_average_mean_of_numeric_outputs():
    agreement = Agreement(authority="collective", resolution="average")
    outputs = [{"numeric": 2.0}, {"numeric": 4.0}, {"numeric": 6.0}]
    result = resolve_agreement(agreement, outputs)
    assert result.decision == pytest.approx(4.0)
    assert result.undecided is False


def test_average_uses_scalar_score_when_numeric_absent():
    agreement = Agreement(authority="collective", resolution="average")
    outputs = [{"score": 1.0}, {"score": 3.0}]
    assert resolve_agreement(agreement, outputs).decision == pytest.approx(2.0)


def test_average_no_numeric_raises():
    agreement = Agreement(authority="collective", resolution="average")
    with pytest.raises(ExecutionError):
        resolve_agreement(agreement, [{"vote": "F"}])


# ---------------------------------------------------------------------------
# consensus
# ---------------------------------------------------------------------------


def test_consensus_unanimous_decides():
    agreement = Agreement(authority="collective", resolution="consensus")
    outputs = [{"vote": "F"}, {"vote": "F"}, {"vote": "F"}]
    result = resolve_agreement(agreement, outputs)
    assert result.decision == "F"
    assert result.undecided is False


def test_consensus_non_unanimous_is_undecided():
    agreement = Agreement(authority="collective", resolution="consensus")
    outputs = [{"vote": "F"}, {"vote": "NF"}]
    result = resolve_agreement(agreement, outputs)
    assert result.undecided is True
    assert result.decision is None


# ---------------------------------------------------------------------------
# weighted_vote
# ---------------------------------------------------------------------------


def test_weighted_vote_weights_change_outcome_vs_plain_majority():
    # Plain majority would pick "F" (2 vs 1). Weights flip it to "NF".
    agreement = Agreement(
        authority="collective",
        resolution="weighted_vote",
        resolution_params={"weights": {"a": 1.0, "b": 1.0, "c": 5.0}},
    )
    outputs = [
        {"node_id": "a", "vote": "F"},
        {"node_id": "b", "vote": "F"},
        {"node_id": "c", "vote": "NF"},
    ]
    result = resolve_agreement(agreement, outputs)
    assert result.decision == "NF"


def test_weighted_vote_confidence_path():
    agreement = Agreement(
        authority="collective",
        resolution="weighted_vote",
        # non-empty params required by schema, but no weights -> confidence path
        resolution_params={"use_confidence": True},
    )
    outputs = [
        {"node_id": "a", "vote": "F", "confidence": 0.2},
        {"node_id": "b", "vote": "NF", "confidence": 0.9},
    ]
    result = resolve_agreement(agreement, outputs)
    assert result.decision == "NF"
    assert "confidence" in (result.detail or "")


# ---------------------------------------------------------------------------
# scoring
# ---------------------------------------------------------------------------


def test_scoring_best_aggregate_selected():
    agreement = Agreement(
        authority="collective",
        resolution="scoring",
        resolution_params={"aggregate": "sum"},
    )
    outputs = [
        {"node_id": "a", "score": {"F": 0.4, "NF": 0.6}},
        {"node_id": "b", "score": {"F": 0.3, "NF": 0.9}},
    ]
    result = resolve_agreement(agreement, outputs)
    assert result.decision == "NF"  # 1.5 vs 0.7


def test_scoring_requires_score_mappings():
    agreement = Agreement(
        authority="collective",
        resolution="scoring",
        resolution_params={"aggregate": "sum"},
    )
    with pytest.raises(ExecutionError):
        resolve_agreement(agreement, [{"vote": "F"}])


# ---------------------------------------------------------------------------
# judge_based / argument_evaluation
# ---------------------------------------------------------------------------


def test_judge_based_invokes_judge_fn_with_context():
    agreement = Agreement(authority="judge_based", resolution="argument_evaluation")
    seen = {}

    def judge_fn(context):
        seen["context"] = context
        return "F"

    result = resolve_agreement(
        agreement, outputs=[], context="the transcript", judge_fn=judge_fn
    )
    assert seen["context"] == "the transcript"
    assert result.decision == "F"
    assert result.authority == "judge_based"


def test_judge_based_without_judge_fn_raises():
    agreement = Agreement(authority="judge_based", resolution="argument_evaluation")
    with pytest.raises(ExecutionError):
        resolve_agreement(agreement, outputs=[], context="x", judge_fn=None)


def test_judge_based_output_schema_parses_structured_class_F():
    schema = {
        "type": "object",
        "properties": {"class": {"type": "string", "enum": ["F", "NF"]}},
    }
    agreement = Agreement(
        authority="judge_based",
        resolution="argument_evaluation",
        output_schema=schema,
    )
    result = resolve_agreement(
        agreement, outputs=[], judge_fn=lambda ctx: {"class": "F"}
    )
    assert result.structured == {"class": "F"}
    assert result.decision == {"class": "F"}
    assert result.undecided is False


def test_judge_based_bare_scalar_coerced_into_enum_property():
    schema = {
        "type": "object",
        "properties": {"class": {"type": "string", "enum": ["F", "NF"]}},
    }
    agreement = Agreement(
        authority="judge_based",
        resolution="argument_evaluation",
        output_schema=schema,
    )
    result = resolve_agreement(agreement, outputs=[], judge_fn=lambda ctx: "NF")
    assert result.structured == {"class": "NF"}


def test_judge_based_invalid_reply_is_undecided_not_raised():
    schema = {
        "type": "object",
        "properties": {"class": {"type": "string", "enum": ["F", "NF"]}},
    }
    agreement = Agreement(
        authority="judge_based",
        resolution="argument_evaluation",
        output_schema=schema,
    )
    result = resolve_agreement(agreement, outputs=[], judge_fn=lambda ctx: "MAYBE")
    assert result.undecided is True
    assert result.decision == "MAYBE"  # raw text preserved
    assert result.structured is None


# ---------------------------------------------------------------------------
# hybrid
# ---------------------------------------------------------------------------


def test_hybrid_collective_decides_without_judge():
    agreement = Agreement(authority="hybrid", resolution="consensus")
    outputs = [{"vote": "F"}, {"vote": "F"}]
    judge_called = {"n": 0}

    def judge_fn(ctx):
        judge_called["n"] += 1
        return "NF"

    result = resolve_agreement(agreement, outputs, judge_fn=judge_fn)
    assert result.decision == "F"
    assert judge_called["n"] == 0  # judge not consulted


def test_hybrid_no_consensus_falls_back_to_judge():
    agreement = Agreement(authority="hybrid", resolution="consensus")
    outputs = [{"vote": "F"}, {"vote": "NF"}]

    def judge_fn(ctx):
        return "F"

    result = resolve_agreement(agreement, outputs, context="t", judge_fn=judge_fn)
    assert result.decision == "F"
    assert result.undecided is False
    assert "fell back to judge" in (result.detail or "")


def test_hybrid_tie_falls_back_to_judge():
    agreement = Agreement(authority="hybrid", resolution="majority_vote")
    outputs = [{"vote": "F"}, {"vote": "NF"}]  # 1-1 tie

    def judge_fn(ctx):
        return "NF"

    result = resolve_agreement(agreement, outputs, judge_fn=judge_fn)
    assert result.decision == "NF"
    assert result.undecided is False


def test_hybrid_inconclusive_without_judge_is_undecided():
    agreement = Agreement(authority="hybrid", resolution="consensus")
    outputs = [{"vote": "F"}, {"vote": "NF"}]
    result = resolve_agreement(agreement, outputs, judge_fn=None)
    assert result.undecided is True


def test_hybrid_argument_evaluation_routes_to_judge():
    agreement = Agreement(authority="hybrid", resolution="argument_evaluation")
    result = resolve_agreement(
        agreement, outputs=[{"vote": "F"}], judge_fn=lambda ctx: "NF"
    )
    assert result.decision == "NF"


# ---------------------------------------------------------------------------
# authority 'other' -> under development
# ---------------------------------------------------------------------------


def test_authority_other_raises_under_development():
    agreement = Agreement(authority="other", resolution="majority_vote")
    with pytest.raises(UnderDevelopment):
        resolve_agreement(agreement, [{"vote": "F"}])


# ---------------------------------------------------------------------------
# collective + argument_evaluation needs a judge -> execution error
# ---------------------------------------------------------------------------


def test_collective_argument_evaluation_without_judge_raises():
    agreement = Agreement(authority="collective", resolution="argument_evaluation")
    with pytest.raises(ExecutionError):
        resolve_agreement(agreement, [{"vote": "F"}])


# ---------------------------------------------------------------------------
# RE binary gold case wiring
# ---------------------------------------------------------------------------


def test_re_binary_gold_case_judge_returns_class_F():
    config = re_binary_debate()
    agreement = config.agreement
    assert agreement.authority == "judge_based"
    assert agreement.resolution == "argument_evaluation"

    result = resolve_agreement(
        agreement,
        outputs=[],
        context="functional vs non-functional transcript",
        judge_fn=lambda ctx: {"class": "F"},
    )
    assert isinstance(result, AgreementResult)
    assert result.structured == {"class": "F"}
    assert result.structured["class"] == "F"
    assert result.undecided is False


def test_re_binary_gold_case_bare_reply_resolves_to_class():
    config = re_binary_debate()
    result = resolve_agreement(
        config.agreement, outputs=[], judge_fn=lambda ctx: "F"
    )
    assert result.structured == {"class": "F"}
