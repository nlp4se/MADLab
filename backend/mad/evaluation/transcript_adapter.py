"""Bridge engine :class:`Transcript` decisions to evaluation predictions.

The evaluation layer scores *labels*: a flat per-instance prediction compared
against a ground-truth label. The engine, however, produces a rich
:class:`~mad.engine.transcript.Transcript` whose final decision is an
:class:`~mad.engine.agreement.AgreementResult` (which may be a bare string, a
number, or a structured ``{class: "F"}`` object). This module adapts the latter
into the former so the job runner can hand a list of transcripts plus a
ground-truth column straight to :func:`mad.evaluation.metrics.evaluate`.

Keeping this adapter in the evaluation package (rather than the engine) honours
the dependency direction: evaluation already depends on the engine's data
shapes, while the engine stays unaware of scoring. Like the rest of the package
it is headless and makes no model calls.
"""

from __future__ import annotations

from typing import Any, Optional, Sequence

from mad.engine.agreement import AgreementResult
from mad.engine.transcript import Transcript
from mad.evaluation.metrics import EvaluationResult, evaluate

__all__ = ["decision_label", "prediction_from_transcript", "evaluate_transcripts"]


def decision_label(result: Optional[AgreementResult]) -> Optional[Any]:
    """Reduce an :class:`AgreementResult` to a single comparable label.

    Resolution order:

    * ``None`` result (agreement never reached) -> ``None``.
    * A structured decision with exactly one property -> that property's value
      (the RE binary gold case: ``{"class": "F"}`` -> ``"F"``).
    * A dict decision with a single value -> that value; otherwise the dict is
      returned as-is (a multi-field decision is left for the caller to handle).
    * Any scalar decision (string / number) -> returned unchanged.

    Args:
        result: The transcript's final :class:`AgreementResult`, or ``None``.

    Returns:
        The label to score, or ``None`` when there is no usable decision.
    """
    if result is None:
        return None

    structured = result.structured
    if isinstance(structured, dict) and len(structured) == 1:
        return next(iter(structured.values()))

    decision = result.decision
    if isinstance(decision, dict):
        if len(decision) == 1:
            return next(iter(decision.values()))
        return decision
    return decision


def prediction_from_transcript(transcript: Transcript) -> Optional[Any]:
    """Extract the scored prediction label from a finished ``transcript``."""
    return decision_label(transcript.decision)


def evaluate_transcripts(
    transcripts: Sequence[Transcript],
    ground_truth: Sequence[Any],
) -> EvaluationResult:
    """Evaluate a batch of transcripts against a ground-truth column.

    Projects each transcript's final decision to a label
    (:func:`prediction_from_transcript`) and defers to
    :func:`mad.evaluation.metrics.evaluate` for the per-instance records and the
    aggregate metrics.

    Args:
        transcripts: One finished transcript per dataset row, in row order.
        ground_truth: The mapped ground-truth label per row (see
            :meth:`mad.input.dataset.Dataset.ground_truths`).

    Returns:
        The :class:`EvaluationResult` for the run.

    Raises:
        mad.errors.ExecutionError: when the counts are misaligned or empty.
    """
    predictions = [prediction_from_transcript(t) for t in transcripts]
    return evaluate(predictions, ground_truth)
