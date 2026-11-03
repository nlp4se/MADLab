"""Evaluation metrics for dataset runs (task 4.3).

A headless refactor of the research scripts in ``code/evaluation``: the
provider-specific batch driver (``baseline.py``) is superseded by the new
engine/providers layer, so only the reusable metric logic is ported. The
package computes per-instance and aggregate classification metrics when a
ground-truth column is mapped (Req 10.7, 11.5), reusing the original
``compute_metrics`` output shape verbatim.

* :mod:`mad.evaluation.metrics` — the ported metrics: :func:`compute_metrics`
  (faithful port), :func:`per_instance_results`, and :func:`evaluate`.
* :mod:`mad.evaluation.transcript_adapter` — bridges the engine's
  :class:`~mad.engine.transcript.Transcript` decisions to prediction labels and
  evaluates a batch of transcripts against a ground-truth column.
"""

from mad.evaluation.metrics import (
    EvaluationResult,
    InstanceResult,
    compute_metrics,
    evaluate,
    per_instance_results,
)
from mad.evaluation.transcript_adapter import (
    decision_label,
    evaluate_transcripts,
    prediction_from_transcript,
)

__all__ = [
    "compute_metrics",
    "per_instance_results",
    "evaluate",
    "InstanceResult",
    "EvaluationResult",
    "decision_label",
    "prediction_from_transcript",
    "evaluate_transcripts",
]
