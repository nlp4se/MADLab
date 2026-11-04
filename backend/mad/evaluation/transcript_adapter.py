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

from mad.engine.agreement import AgreementResult, _single_enum_property
from mad.engine.transcript import Transcript
from mad.evaluation.metrics import EvaluationResult, evaluate
from mad.output_schema import unwrap_output_schema

__all__ = [
    "LABEL_KEYS",
    "decision_label",
    "prediction_from_transcript",
    "evaluate_transcripts",
]

# Keys that conventionally carry the label of a structured decision, in
# priority order (matched case-insensitively). Mirrors the frontend
# ``decisionDisplay`` helper so the scored label and the displayed pill agree.
LABEL_KEYS: tuple[str, ...] = (
    "class",
    "label",
    "classification",
    "final_classification",
    "decision",
    "answer",
    "verdict",
)


def _inner_schema(schema: Any) -> Optional[dict[str, Any]]:
    """Unwrap a provider-style ``{"name", "schema": {...}}`` wrapper.

    Users often paste the OpenAI ``response_format.json_schema`` envelope; the
    JSON schema proper then lives under ``"schema"``. Delegates to the shared
    normalizer (:func:`mad.output_schema.unwrap_output_schema`, task 11.13) so
    labels, validation and the provider request agree.
    """
    return unwrap_output_schema(schema)


def _is_scalar(value: Any) -> bool:
    return value is not None and isinstance(value, (str, int, float, bool))


def _label_from_object(
    obj: dict[str, Any], output_schema: Optional[dict[str, Any]]
) -> Optional[Any]:
    """Derive the label of a structured decision, or ``None``.

    Precedence: the schema's single enum (or lone) property, then a known label
    key (:data:`LABEL_KEYS`, case-insensitive), then the value of a
    single-property object. Only scalar values qualify as labels.
    """
    inner = _inner_schema(output_schema)
    if inner is not None:
        prop = _single_enum_property(inner)
        if prop is not None and _is_scalar(obj.get(prop)):
            return obj[prop]

    lowered = {str(k).lower(): k for k in obj}
    for key in LABEL_KEYS:
        original = lowered.get(key)
        if original is not None and _is_scalar(obj[original]):
            return obj[original]

    if len(obj) == 1:
        value = next(iter(obj.values()))
        if _is_scalar(value):
            return value
    return None


def decision_label(
    result: Optional[AgreementResult],
    output_schema: Optional[dict[str, Any]] = None,
) -> Optional[Any]:
    """Reduce an :class:`AgreementResult` to a single comparable label.

    Resolution order:

    * ``None`` result (agreement never reached) -> ``None``.
    * A structured (or dict) decision -> its label: the ``output_schema``'s
      single enum property, else a known label key (``class``, ``label``,
      ``final_classification``, ...), else the value of a single-property
      object (the RE binary gold case: ``{"class": "F"}`` -> ``"F"``). A
      multi-field object without a recognisable label yields ``None`` (no
      usable label) rather than the whole object.
    * Any scalar decision (string / number) -> returned unchanged.

    Args:
        result: The transcript's final :class:`AgreementResult`, or ``None``.
        output_schema: The agreement's ``output_schema`` (optionally wrapped in
            a ``{"name", "schema"}`` envelope), used to find the label property.

    Returns:
        The label to score, or ``None`` when there is no usable decision.
    """
    if result is None:
        return None

    for candidate in (result.structured, result.decision):
        if isinstance(candidate, dict):
            return _label_from_object(candidate, output_schema)

    return result.decision


def prediction_from_transcript(
    transcript: Transcript,
    output_schema: Optional[dict[str, Any]] = None,
) -> Optional[Any]:
    """Extract the scored prediction label from a finished ``transcript``."""
    return decision_label(transcript.decision, output_schema)


def evaluate_transcripts(
    transcripts: Sequence[Transcript],
    ground_truth: Sequence[Any],
    output_schema: Optional[dict[str, Any]] = None,
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
        output_schema: The run's agreement ``output_schema`` (see
            :func:`decision_label`).

    Returns:
        The :class:`EvaluationResult` for the run.

    Raises:
        mad.errors.ExecutionError: when the counts are misaligned or empty.
    """
    predictions = [prediction_from_transcript(t, output_schema) for t in transcripts]
    return evaluate(predictions, ground_truth)
