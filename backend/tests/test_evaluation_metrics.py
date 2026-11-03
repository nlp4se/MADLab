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
