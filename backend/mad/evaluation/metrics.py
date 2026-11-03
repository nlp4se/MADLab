"""Classification metrics for dataset runs (refactor of ``code/evaluation``).

This is the headless port of the research script ``code/evaluation/metrics.py``.
The original computed, for a CSV with a *truth* column and a *prediction*
column, an accuracy score plus a per-class precision/recall/F1/support report
(via :mod:`sklearn`), and wrote the result out in JSON/TXT/CSV. The provider-
specific driver that *produced* those predictions (``code/evaluation/baseline.py``,
an OpenAI-Assistants batch classifier) is superseded by the new
engine/providers layer, so only the reusable metric logic is ported here.

Three layers are exposed, smallest to largest:

* :func:`compute_metrics` — the faithful port. Given aligned ``y_true`` /
  ``y_pred`` sequences it returns the exact same ``{"overall": {"accuracy"},
  "per_class": {label: {precision, recall, f1-score, support}}}`` dict shape the
  research code produced, so downstream artifacts stay byte-compatible.
* :func:`per_instance_results` — the per-instance view (Req 10.7 /11.5): one
  record per row carrying its prediction, its ground-truth label, and whether
  they matched. This is what the execution-history detail view renders per row.
* :func:`evaluate` — the batch roll-up: aligns predictions with ground truth,
  builds the per-instance records, and computes the aggregate
  :func:`compute_metrics`, returning an :class:`EvaluationResult`.

The module is headless: it imports only pandas + scikit-learn (both backend
dependencies) and the domain error type. It makes no model calls and has no web
dependency, so it stays usable from the CLI batch path and from the job runner
alike. When a dataset carries no ground-truth column, callers simply skip
evaluation (there is nothing to score against), matching the design: metrics are
produced "when ground-truth labels are present".
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Sequence

from sklearn.metrics import accuracy_score, classification_report

from mad.errors import ExecutionError

__all__ = [
    "InstanceResult",
    "EvaluationResult",
    "compute_metrics",
    "per_instance_results",
    "evaluate",
]


# Report keys scikit-learn adds alongside the per-class rows; excluded from the
# per_class section to match the original research output exactly.
_AGGREGATE_REPORT_KEYS = ("accuracy", "macro avg", "weighted avg")


def compute_metrics(
    y_true: Sequence[Any], y_pred: Sequence[Any]
) -> dict[str, Any]:
    """Compute classification metrics as the research code did (faithful port).

    Mirrors ``code/evaluation/metrics.py``'s ``compute_metrics``: overall
    accuracy plus a per-class precision/recall/F1/support breakdown derived from
    :func:`sklearn.metrics.classification_report`. The returned dict shape is
    preserved verbatim so JSON/CSV artifacts remain identical:

    ``{"overall": {"accuracy": float},
       "per_class": {label: {"precision", "recall", "f1-score", "support"}}}``

    Args:
        y_true: Ground-truth labels, aligned positionally with ``y_pred``.
        y_pred: Predicted labels, aligned positionally with ``y_true``.

    Returns:
        The metrics dict described above.

    Raises:
        mad.errors.ExecutionError: when the two sequences differ in length or are
            empty (sklearn cannot score misaligned / empty inputs).
    """
    true_list = list(y_true)
    pred_list = list(y_pred)

    if len(true_list) != len(pred_list):
        raise ExecutionError(
            "compute_metrics requires y_true and y_pred of equal length; got "
            f"{len(true_list)} truth label(s) and {len(pred_list)} prediction(s)."
        )
    if not true_list:
        raise ExecutionError(
            "compute_metrics requires at least one (y_true, y_pred) pair; both "
            "sequences were empty."
        )

    # Overall accuracy.
    accuracy = accuracy_score(true_list, pred_list)

    # Detailed per-class report (dict form), zero_division kept at sklearn's
    # default so behaviour matches the original research script.
    report = classification_report(true_list, pred_list, output_dict=True)

    metrics: dict[str, Any] = {
        "overall": {"accuracy": accuracy},
        "per_class": {},
    }

    for class_name, class_metrics in report.items():
        if class_name in _AGGREGATE_REPORT_KEYS:
            continue
        metrics["per_class"][class_name] = {
            "precision": class_metrics["precision"],
            "recall": class_metrics["recall"],
            "f1-score": class_metrics["f1-score"],
            "support": class_metrics["support"],
        }

    return metrics


@dataclass
class InstanceResult:
    """Per-instance evaluation record (Req 10.7 / 11.5).

    One record per dataset row: the model's prediction, the row's ground-truth
    label, and whether they matched. ``index`` is the zero-based row position so
    the history viewer can line records up with the transcript list.

    Attributes:
        index: Zero-based instance/row index.
        prediction: The debate's final decision for this instance (as a label).
        ground_truth: The gold label for this instance.
        correct: ``True`` when ``prediction`` equals ``ground_truth``.
    """

    index: int
    prediction: Any
    ground_truth: Any
    correct: bool


@dataclass
class EvaluationResult:
    """Aggregate + per-instance evaluation of a dataset run.

    Attributes:
        metrics: The aggregate :func:`compute_metrics` dict (overall accuracy +
            per-class breakdown).
        per_instance: One :class:`InstanceResult` per scored row, in row order.
        count: Number of scored instances (``len(per_instance)``).
    """

    metrics: dict[str, Any]
    per_instance: list[InstanceResult] = field(default_factory=list)

    @property
    def count(self) -> int:
        """Number of scored instances."""
        return len(self.per_instance)


def _normalize_label(value: Any) -> Any:
    """Normalise a label for equality comparison.

    Ground-truth labels come from pandas cells (which may be ``numpy`` scalars)
    while predictions arrive as engine decision strings. Compare on a trimmed
    string form so ``"F"`` matches ``numpy.str_("F")`` and whitespace/casing of
    surrounding storage does not cause false mismatches. ``None`` stays ``None``.
    """
    if value is None:
        return None
    return str(value).strip()


def per_instance_results(
    predictions: Sequence[Any],
    ground_truth: Sequence[Any],
) -> list[InstanceResult]:
    """Build the per-instance correctness records (Req 10.7 / 11.5).

    Args:
        predictions: Per-row predicted labels, aligned with ``ground_truth``.
        ground_truth: Per-row gold labels, aligned with ``predictions``.

    Returns:
        One :class:`InstanceResult` per row, in order.

    Raises:
        mad.errors.ExecutionError: when the two sequences differ in length.
    """
    preds = list(predictions)
    truths = list(ground_truth)
    if len(preds) != len(truths):
        raise ExecutionError(
            "per_instance_results requires predictions and ground_truth of "
            f"equal length; got {len(preds)} prediction(s) and {len(truths)} "
            "ground-truth label(s)."
        )

    results: list[InstanceResult] = []
    for index, (pred, truth) in enumerate(zip(preds, truths)):
        results.append(
            InstanceResult(
                index=index,
                prediction=pred,
                ground_truth=truth,
                correct=_normalize_label(pred) == _normalize_label(truth),
            )
        )
    return results


def evaluate(
    predictions: Sequence[Any],
    ground_truth: Sequence[Any],
) -> EvaluationResult:
    """Evaluate a dataset run: per-instance records + aggregate metrics.

    This is the single entry point the batch job runner calls once a run
    finishes and a ground-truth column was mapped (Req 10.7 / 11.5). It pairs
    each instance's final decision with its gold label, records the per-instance
    correctness, and computes the aggregate :func:`compute_metrics`.

    Args:
        predictions: The engine's final decision per instance (a label string),
            aligned with ``ground_truth`` by row order.
        ground_truth: The mapped ground-truth label per instance.

    Returns:
        An :class:`EvaluationResult` carrying the aggregate metrics dict and the
        per-instance records.

    Raises:
        mad.errors.ExecutionError: when the sequences are misaligned or empty.
    """
    instances = per_instance_results(predictions, ground_truth)
    metrics = compute_metrics(list(ground_truth), list(predictions))
    return EvaluationResult(metrics=metrics, per_instance=instances)
