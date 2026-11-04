"""Tests for the evaluation layer (:mod:`mad.evaluation`).

The headline guarantee is parity with the research code: the ported
:func:`mad.evaluation.metrics.compute_metrics` must reproduce, on a known
sample, exactly what ``code/evaluation/metrics.py`` produced — the same dict
shape and the same numbers computed straight from scikit-learn. The remaining
tests cover the per-instance view, the batch :func:`evaluate` roll-up, the
transcript adapter that bridges engine decisions to labels, and the error
guards. All of it is headless: no network, no provider construction.
"""

import pytest
from sklearn.metrics import accuracy_score, classification_report

from mad.engine.agreement import AgreementResult
from mad.engine.transcript import Transcript
from mad.errors import ExecutionError
from mad.evaluation import (
    EvaluationResult,
    InstanceResult,
    compute_metrics,
    decision_label,
    evaluate,
    evaluate_transcripts,
    per_instance_results,
    prediction_from_transcript,
)


# A known classification sample (RE binary: F / NF), with two mistakes.
# The 'type' column is the truth, the 'judge' column is the prediction — the
# exact column roles the research CLI used.
SAMPLE_TRUTH = ["F", "F", "NF", "NF", "F", "NF", "F", "NF"]
SAMPLE_PRED = ["F", "NF", "NF", "NF", "F", "F", "F", "NF"]


def _oracle_metrics(y_true, y_pred):
    """Recompute metrics exactly as ``code/evaluation/metrics.py`` did.

    This mirrors the original research ``compute_metrics`` line for line so the
    test pins the ported implementation to the historical output rather than to
    itself.
    """
    accuracy = accuracy_score(y_true, y_pred)
    report = classification_report(y_true, y_pred, output_dict=True)
    metrics = {"overall": {"accuracy": accuracy}, "per_class": {}}
    for class_name, class_metrics in report.items():
        if class_name not in ["accuracy", "macro avg", "weighted avg"]:
            metrics["per_class"][class_name] = {
                "precision": class_metrics["precision"],
                "recall": class_metrics["recall"],
                "f1-score": class_metrics["f1-score"],
                "support": class_metrics["support"],
            }
    return metrics


# ---------------------------------------------------------------------------
# compute_metrics parity with the research code
# ---------------------------------------------------------------------------


def test_compute_metrics_matches_research_output_on_known_sample():
    expected = _oracle_metrics(SAMPLE_TRUTH, SAMPLE_PRED)
    actual = compute_metrics(SAMPLE_TRUTH, SAMPLE_PRED)
    assert actual == expected


def test_compute_metrics_shape_and_keys():
    metrics = compute_metrics(SAMPLE_TRUTH, SAMPLE_PRED)
    assert set(metrics) == {"overall", "per_class"}
    assert set(metrics["overall"]) == {"accuracy"}
    # Both labels present; no sklearn aggregate rows leaked in.
    assert set(metrics["per_class"]) == {"F", "NF"}
    for row in metrics["per_class"].values():
        assert set(row) == {"precision", "recall", "f1-score", "support"}


def test_compute_metrics_accuracy_value():
    # 6 of 8 correct.
    metrics = compute_metrics(SAMPLE_TRUTH, SAMPLE_PRED)
    assert metrics["overall"]["accuracy"] == pytest.approx(6 / 8)


def test_compute_metrics_perfect_prediction():
    metrics = compute_metrics(["F", "NF", "F"], ["F", "NF", "F"])
    assert metrics["overall"]["accuracy"] == pytest.approx(1.0)
    for row in metrics["per_class"].values():
        assert row["precision"] == pytest.approx(1.0)
        assert row["recall"] == pytest.approx(1.0)
        assert row["f1-score"] == pytest.approx(1.0)


def test_compute_metrics_length_mismatch_raises():
    with pytest.raises(ExecutionError):
        compute_metrics(["F", "NF"], ["F"])


def test_compute_metrics_empty_raises():
    with pytest.raises(ExecutionError):
        compute_metrics([], [])


# ---------------------------------------------------------------------------
# per_instance_results
# ---------------------------------------------------------------------------


def test_per_instance_results_flags_correctness():
    results = per_instance_results(SAMPLE_PRED, SAMPLE_TRUTH)
    assert [r.correct for r in results] == [
        True, False, True, True, True, False, True, True
    ]
    assert [r.index for r in results] == list(range(len(SAMPLE_PRED)))
    assert results[1].prediction == "NF"
    assert results[1].ground_truth == "F"


def test_per_instance_results_normalizes_whitespace_and_type():
    # A numpy-ish/str prediction with surrounding whitespace still matches.
    results = per_instance_results([" F ", "NF"], ["F", "NF"])
    assert all(r.correct for r in results)


def test_per_instance_results_length_mismatch_raises():
    with pytest.raises(ExecutionError):
        per_instance_results(["F"], ["F", "NF"])


# ---------------------------------------------------------------------------
# evaluate roll-up
# ---------------------------------------------------------------------------


def test_evaluate_combines_metrics_and_per_instance():
    result = evaluate(SAMPLE_PRED, SAMPLE_TRUTH)
    assert isinstance(result, EvaluationResult)
    assert result.count == len(SAMPLE_PRED)
    assert result.metrics == _oracle_metrics(SAMPLE_TRUTH, SAMPLE_PRED)
    assert isinstance(result.per_instance[0], InstanceResult)
    assert sum(1 for r in result.per_instance if r.correct) == 6


# ---------------------------------------------------------------------------
# transcript adapter
# ---------------------------------------------------------------------------


def _transcript_with_decision(decision):
    t = Transcript(config_id="c1", config_name="cfg")
    t.decision = decision
    return t


def test_decision_label_from_structured_single_property():
    result = AgreementResult(
        decision={"class": "F"},
        authority="judge_based",
        resolution="argument_evaluation",
        structured={"class": "F"},
    )
    assert decision_label(result) == "F"


def test_decision_label_from_scalar_decision():
    result = AgreementResult(
        decision="NF", authority="collective", resolution="majority_vote"
    )
    assert decision_label(result) == "NF"


def test_decision_label_none_when_no_decision():
    assert decision_label(None) is None


def test_prediction_from_transcript_uses_structured_class():
    decision = AgreementResult(
        decision={"class": "NF"},
        authority="judge_based",
        resolution="argument_evaluation",
        structured={"class": "NF"},
    )
    transcript = _transcript_with_decision(decision)
    assert prediction_from_transcript(transcript) == "NF"


def test_evaluate_transcripts_matches_direct_evaluate():
    labels = ["F", "NF", "F", "NF"]
    truth = ["F", "F", "F", "NF"]  # one mistake at index 1
    transcripts = [
        _transcript_with_decision(
            AgreementResult(
                decision={"class": label},
                authority="judge_based",
                resolution="argument_evaluation",
                structured={"class": label},
            )
        )
        for label in labels
    ]
    result = evaluate_transcripts(transcripts, truth)
    assert result.count == 4
    assert sum(1 for r in result.per_instance if r.correct) == 3
    assert result.metrics == evaluate(labels, truth).metrics


# ---------------------------------------------------------------------------
# structured-decision label extraction (task 11.12)
# ---------------------------------------------------------------------------

# Execution 3's agreement output_schema: the provider-style envelope with the
# JSON schema proper under "schema" (a lone enum property "class").
EXEC3_SCHEMA = {
    "name": "requirements-schema",
    "description": "A schema for classifying requirements into categories",
    "schema": {
        "type": "object",
        "properties": {"class": {"type": "string", "enum": ["F", "NF"]}},
    },
}

# Execution 3, instance 0: the judge ignored the enum property and replied with
# a multi-field object (accepted because the schema has no "required").
EXEC3_DECISION = {
    "requirement": "The system shall have a MDI form that allows for the "
    "viewing of the graph and the data table.",
    "debaters_arguments": [
        "Debater 1: This is a Functional requirement because it describes a "
        "specific system feature.",
        "Debater 2: This is a Non-Functional requirement (Usability / "
        "Interface).",
    ],
    "moderator_evaluation": "Its primary purpose is to provide the operational "
    "capability for users to view data tables and graphs.",
    "final_classification": "Functional",
}


def _judge_result(obj):
    return AgreementResult(
        decision=obj,
        authority="judge_based",
        resolution="argument_evaluation",
        structured=obj,
    )


def test_decision_label_uses_known_label_key_for_multi_field_object():
    assert decision_label(_judge_result(EXEC3_DECISION), EXEC3_SCHEMA) == "Functional"
    assert decision_label(_judge_result(EXEC3_DECISION)) == "Functional"


def test_decision_label_uses_wrapped_schema_enum_property():
    assert decision_label(_judge_result({"class": "F"}), EXEC3_SCHEMA) == "F"


def test_decision_label_prefers_schema_enum_property_over_label_keys():
    schema = {
        "type": "object",
        "properties": {
            "category": {"type": "string", "enum": ["F", "NF"]},
            "reason": {"type": "string"},
        },
    }
    obj = {"reason": "Describes behaviour.", "answer": "maybe", "category": "NF"}
    assert decision_label(_judge_result(obj), schema) == "NF"
    # Without the schema the known key wins.
    assert decision_label(_judge_result(obj)) == "maybe"


def test_decision_label_matches_label_keys_case_insensitively():
    obj = {"Rationale": "Because.", "Verdict": "NF"}
    assert decision_label(_judge_result(obj)) == "NF"


def test_decision_label_none_for_multi_field_object_without_label():
    obj = {"summary": "Long text.", "notes": ["a", "b"]}
    assert decision_label(_judge_result(obj)) is None


def test_runner_aggregate_metrics_omitted_instead_of_crashing():
    """An unscorable label mix must not crash finalize (execution 3 got stuck)."""
    from app.jobs.runner import _InstanceOutcome, _aggregate_metrics

    outcomes = [
        _InstanceOutcome(
            index=i,
            instance={},
            ground_truth="F",
            transcript=_transcript_with_decision(_judge_result(obj)),
            output_schema=EXEC3_SCHEMA,
        )
        for i, obj in enumerate(
            [{"summary": "no label", "notes": "x"}, {"class": "F"}]
        )
    ]
    assert _aggregate_metrics(outcomes) is None

    outcomes[0].transcript = _transcript_with_decision(_judge_result(EXEC3_DECISION))
    metrics = _aggregate_metrics(outcomes)
    assert metrics is not None
    assert metrics["scored_count"] == 2
    assert metrics["overall"]["accuracy"] == 0.5
