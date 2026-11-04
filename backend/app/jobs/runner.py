"""Async execution job runner (task 6.6, Req 10.4-10.6, 11.1-11.3).

The runner is the background worker that turns a *queued* :class:`Execution`
row into a finished run. Given an execution id and a wired
:class:`~mad.providers.registry.ProviderRegistry`, it:

1. loads the execution's **immutable** ``config_snapshot`` (captured at launch,
   Req 11.3) and parses it back into a :class:`~mad.taxonomy.schema.MADConfig`;
2. materialises the instance list — a single ad-hoc instance (single mode) or
   the mapped rows of a dataset (batch mode, via the engine
   :class:`~mad.input.dataset.Dataset`);
3. runs each instance through the engine ``run_debate`` with **per-instance
   error isolation** (one failure never aborts the run, Req 10.6) and a
   **concurrency limit** (Req 10.5);
4. writes each instance's resolved input, transcript, final decision, ground
   truth and per-instance metrics to ``execution_instances``, bumping the
   execution's ``progress`` as instances complete (Req 10.5, 11.2);
5. computes **aggregate metrics** when a ground-truth column was mapped
   (reusing :mod:`mad.evaluation`, Req 10.7, 11.5);
6. sets the **final status** — ``completed`` (all ok), ``failed`` (all errored),
   or ``partial`` (a mix) (Req 10.6, 11.1).

Design (design.md "Open design decisions"): an in-process ``asyncio`` worker
with DB-backed progress and no external broker. The engine ``run_debate`` is
synchronous, so each instance runs in a worker thread (``asyncio.to_thread``)
guarded by a :class:`asyncio.Semaphore` for the concurrency cap. Each instance
writes through its own short-lived session so a slow debate never holds a write
transaction open across the whole run, and partial progress is visible to
pollers / the SSE stream mid-run.

Testability: the runner takes a pre-built ``registry`` (not a DB session) so
tests inject a :class:`~mad.providers.registry.ProviderRegistry` backed by a
:class:`~mad.providers.base.MockModelClient` — fully offline and deterministic.
A synchronous :func:`run_execution_sync` wrapper drives the async runner to
completion on a private event loop, which the service uses as the "run
synchronously in tests" seam so background jobs finish deterministically.
"""

from __future__ import annotations

import asyncio
from dataclasses import dataclass
from typing import Any, Optional

from sqlalchemy.orm import Session, sessionmaker

from app.db.models import Execution, ExecutionInstance, ExecutionStatus, InputMode
from app.db.session import get_sessionmaker, session_scope
from app.jobs.serialize import transcript_to_dict
from mad.engine.orchestrator import RetryPolicy, run_debate
from mad.engine.transcript import Transcript
from mad.errors import MADError
from mad.evaluation import evaluate_transcripts, prediction_from_transcript
from mad.input.dataset import Dataset as EngineDataset
from mad.input.template import resolve_template
from mad.providers.registry import ProviderRegistry
from mad.taxonomy.schema import MADConfig

# Default maximum number of instances executed concurrently (Req 10.5). Chosen
# conservatively so a batch does not fan out an unbounded number of provider
# calls at once; the service can override per launch.
DEFAULT_CONCURRENCY = 4


@dataclass
class _ResolvedInstance:
    """One instance to execute: its index, template inputs, and ground truth."""

    index: int
    instance: dict[str, Any]
    ground_truth: Optional[Any] = None


@dataclass
class _InstanceOutcome:
    """The result of running one instance: a transcript or an isolated error."""

    index: int
    instance: dict[str, Any]
    ground_truth: Optional[Any]
    transcript: Optional[Transcript] = None
    error: Optional[str] = None
    # The agreement output_schema, used to derive the scored label from a
    # structured decision (task 11.12).
    output_schema: Optional[dict[str, Any]] = None


# ---------------------------------------------------------------------------
# Public entry points
# ---------------------------------------------------------------------------


async def run_execution_async(
    execution_id: int,
    registry: ProviderRegistry,
    *,
    session_factory: Optional[sessionmaker[Session]] = None,
    concurrency: int = DEFAULT_CONCURRENCY,
    retry_policy: Optional[RetryPolicy] = None,
    sleep=None,
) -> str:
    """Run an execution to completion, returning its final status string.

    Args:
        execution_id: The queued :class:`Execution` row to run.
        registry: Engine provider registry wired to the stored providers (or a
            mock registry in tests).
        session_factory: Sessionmaker for the short-lived per-step sessions.
            Defaults to the process-wide one (:func:`get_sessionmaker`).
        concurrency: Maximum instances executed in parallel (Req 10.5).
        retry_policy: Per-call retry/backoff policy forwarded to ``run_debate``
            (Req 9.5). Defaults to the engine default.
        sleep: Optional sleep hook forwarded to ``run_debate`` backoff (tests
            pass a no-op). Defaults to the engine's ``time.sleep``.

    Returns:
        The final execution status (``completed`` / ``failed`` / ``partial``).
        A snapshot/instance-materialisation failure sets ``failed`` and the
        execution error is recorded on the row's metrics payload.
    """
    factory = session_factory or get_sessionmaker()

    # Phase 1: load the snapshot + materialise the instance list. A failure here
    # (bad snapshot, dataset gone, mapping mismatch) marks the whole run failed.
    try:
        config, instances = _prepare(factory, execution_id)
    except Exception as exc:  # noqa: BLE001 - surface as a failed run, not a crash.
        _mark_failed_to_prepare(factory, execution_id, exc)
        return ExecutionStatus.FAILED.value

    _set_status(factory, execution_id, ExecutionStatus.RUNNING, progress=0.0)

    total = len(instances)
    if total == 0:
        _finalize(factory, execution_id, outcomes=[], ground_truth_present=False)
        return ExecutionStatus.COMPLETED.value

    semaphore = asyncio.Semaphore(max(1, concurrency))
    completed = 0
    lock = asyncio.Lock()

    async def _run_one(resolved: _ResolvedInstance) -> _InstanceOutcome:
        nonlocal completed
        async with semaphore:
            outcome = await asyncio.to_thread(
                _execute_instance,
                config,
                resolved,
                registry,
                retry_policy,
                sleep,
            )
        # Persist this instance + bump progress under a lock so concurrent
        # workers never interleave a progress write.
        async with lock:
            completed += 1
            _write_instance(factory, execution_id, outcome)
            _set_progress(factory, execution_id, completed / total)
        return outcome

    outcomes = await asyncio.gather(*[_run_one(r) for r in instances])
    outcomes = sorted(outcomes, key=lambda o: o.index)

    ground_truth_present = any(o.ground_truth is not None for o in instances_with_gt(instances))
    _finalize(
        factory,
        execution_id,
        outcomes=list(outcomes),
        ground_truth_present=ground_truth_present,
    )
    return _status_for_outcomes(outcomes).value


def run_execution_sync(
    execution_id: int,
    registry: ProviderRegistry,
    *,
    session_factory: Optional[sessionmaker[Session]] = None,
    concurrency: int = DEFAULT_CONCURRENCY,
    retry_policy: Optional[RetryPolicy] = None,
    sleep=None,
) -> str:
    """Synchronous wrapper around :func:`run_execution_async`.

    Drives the async runner to completion on a private event loop. Used by the
    service's synchronous launch seam (tests) so background jobs complete
    deterministically before assertions run.
    """
    return asyncio.run(
        run_execution_async(
            execution_id,
            registry,
            session_factory=session_factory,
            concurrency=concurrency,
            retry_policy=retry_policy,
            sleep=sleep,
        )
    )


# ---------------------------------------------------------------------------
# Instance preparation
# ---------------------------------------------------------------------------


def _prepare(
    factory: sessionmaker[Session], execution_id: int
) -> tuple[MADConfig, list[_ResolvedInstance]]:
    """Load the snapshot + materialise the instance list for ``execution_id``."""
    with session_scope(factory) as session:
        row = session.get(Execution, execution_id)
        if row is None:
            raise MADError(f"execution {execution_id} not found")
        # Parse the immutable snapshot back into a MADConfig (Req 11.3). The
        # snapshot was validated at launch, so this should always succeed.
        config = MADConfig.model_validate(row.config_snapshot)
        input_mode = row.input_mode
        input_ref = dict(row.input_ref or {})

    if input_mode == InputMode.SINGLE.value:
        instances = [_ResolvedInstance(index=0, instance=dict(input_ref.get("input", {})))]
        return config, instances

    # Batch: load the dataset and map its rows to instances.
    return config, _batch_instances(factory, input_ref)


def _batch_instances(
    factory: sessionmaker[Session], input_ref: dict[str, Any]
) -> list[_ResolvedInstance]:
    """Materialise the batch instance list from a dataset + column mapping."""
    from app.db.models import Dataset as DatasetRow  # local import: avoid cycle

    dataset_id = input_ref.get("dataset_id")
    mapping = dict(input_ref.get("mapping", {}) or {})
    ground_truth_column = input_ref.get("ground_truth_column")
    limit = input_ref.get("limit")

    with session_scope(factory) as session:
        dataset_row = session.get(DatasetRow, dataset_id)
        if dataset_row is None:
            raise MADError(f"dataset {dataset_id} not found for batch execution")
        stored_path = dataset_row.stored_path

    engine_dataset = EngineDataset.from_csv(stored_path)
    # Validate the mapping once up front so a bad mapping fails preparation
    # rather than every instance.
    engine_dataset.map_columns(mapping)

    row_count = engine_dataset.row_count
    if isinstance(limit, int) and limit > 0:
        row_count = min(row_count, limit)

    resolved: list[_ResolvedInstance] = []
    for index in range(row_count):
        instance = engine_dataset.instance(index, mapping)
        instance = {k: _jsonable(v) for k, v in instance.items()}
        gt = None
        if ground_truth_column:
            gt = _jsonable(engine_dataset.ground_truth(index, ground_truth_column))
        resolved.append(_ResolvedInstance(index=index, instance=instance, ground_truth=gt))
    return resolved


def instances_with_gt(instances: list[_ResolvedInstance]) -> list[_ResolvedInstance]:
    """Return the instances carrying a ground-truth label (helper for metrics)."""
    return [i for i in instances if i.ground_truth is not None]


# ---------------------------------------------------------------------------
# Per-instance execution (runs in a worker thread)
# ---------------------------------------------------------------------------


def _execute_instance(
    config: MADConfig,
    resolved: _ResolvedInstance,
    registry: ProviderRegistry,
    retry_policy: Optional[RetryPolicy],
    sleep,
) -> _InstanceOutcome:
    """Run one instance through ``run_debate`` with per-instance error isolation.

    Any exception from the engine (provider resolution, under-dev gating that
    somehow slipped past the pre-run gate, or an execution error) is caught and
    recorded as the instance's ``error`` so the rest of the run continues
    (Req 10.6). This is the isolation boundary.
    """
    kwargs: dict[str, Any] = {}
    if retry_policy is not None:
        kwargs["retry_policy"] = retry_policy
    if sleep is not None:
        kwargs["sleep"] = sleep
    try:
        transcript = run_debate(config, resolved.instance, registry, **kwargs)
    except Exception as exc:  # noqa: BLE001 - isolate: record + continue.
        return _InstanceOutcome(
            index=resolved.index,
            instance=resolved.instance,
            ground_truth=resolved.ground_truth,
            error=f"{type(exc).__name__}: {exc}",
        )
    return _InstanceOutcome(
        index=resolved.index,
        instance=resolved.instance,
        ground_truth=resolved.ground_truth,
        transcript=transcript,
        output_schema=config.agreement.output_schema,
    )


# ---------------------------------------------------------------------------
# Persistence helpers (each in its own short-lived transaction)
# ---------------------------------------------------------------------------


def _write_instance(
    factory: sessionmaker[Session], execution_id: int, outcome: _InstanceOutcome
) -> None:
    """Persist one :class:`ExecutionInstance` row for a finished instance."""
    transcript_json = (
        transcript_to_dict(outcome.transcript) if outcome.transcript else None
    )
    final_decision = (
        transcript_json["decision"] if transcript_json else None
    )
    prediction = (
        prediction_from_transcript(outcome.transcript, outcome.output_schema)
        if outcome.transcript is not None
        else None
    )
    per_metrics: Optional[dict[str, Any]] = None
    if outcome.ground_truth is not None and prediction is not None:
        per_metrics = {
            "prediction": _jsonable(prediction),
            "ground_truth": _jsonable(outcome.ground_truth),
            "correct": str(prediction).strip() == str(outcome.ground_truth).strip(),
        }

    with session_scope(factory) as session:
        session.add(
            ExecutionInstance(
                execution_id=execution_id,
                instance_index=outcome.index,
                resolved_input={k: _jsonable(v) for k, v in outcome.instance.items()},
                transcript=transcript_json,
                final_decision=final_decision,
                ground_truth=(
                    None if outcome.ground_truth is None else str(outcome.ground_truth)
                ),
                metrics=per_metrics,
                error=outcome.error,
            )
        )


def _set_status(
    factory: sessionmaker[Session],
    execution_id: int,
    status: ExecutionStatus,
    *,
    progress: Optional[float] = None,
) -> None:
    """Set an execution's status (and optionally its progress)."""
    with session_scope(factory) as session:
        row = session.get(Execution, execution_id)
        if row is None:  # pragma: no cover - defensive
            return
        row.status = status.value
        if progress is not None:
            row.progress = progress


def _set_progress(
    factory: sessionmaker[Session], execution_id: int, progress: float
) -> None:
    """Update an execution's progress fraction (Req 10.5)."""
    with session_scope(factory) as session:
        row = session.get(Execution, execution_id)
        if row is None:  # pragma: no cover - defensive
            return
        row.progress = max(0.0, min(1.0, progress))


def _finalize(
    factory: sessionmaker[Session],
    execution_id: int,
    *,
    outcomes: list[_InstanceOutcome],
    ground_truth_present: bool,
) -> None:
    """Set the final status, progress, and aggregate metrics for a run."""
    status = _status_for_outcomes(outcomes)
    metrics = _aggregate_metrics(outcomes) if ground_truth_present else None

    with session_scope(factory) as session:
        row = session.get(Execution, execution_id)
        if row is None:  # pragma: no cover - defensive
            return
        row.status = status.value
        row.progress = 1.0
        if metrics is not None:
            row.metrics = metrics


def _mark_failed_to_prepare(
    factory: sessionmaker[Session], execution_id: int, exc: Exception
) -> None:
    """Mark an execution failed when instance preparation itself failed."""
    with session_scope(factory) as session:
        row = session.get(Execution, execution_id)
        if row is None:  # pragma: no cover - defensive
            return
        row.status = ExecutionStatus.FAILED.value
        row.progress = 1.0
        row.metrics = {"error": f"{type(exc).__name__}: {exc}"}


# ---------------------------------------------------------------------------
# Aggregation / status
# ---------------------------------------------------------------------------


def _status_for_outcomes(outcomes: list[_InstanceOutcome]) -> ExecutionStatus:
    """Derive the final status from per-instance outcomes (Req 10.6, 11.1).

    * all instances succeeded -> ``completed``
    * all instances errored   -> ``failed``
    * a mix                   -> ``partial``
    """
    if not outcomes:
        return ExecutionStatus.COMPLETED
    errored = sum(1 for o in outcomes if o.error is not None)
    if errored == 0:
        return ExecutionStatus.COMPLETED
    if errored == len(outcomes):
        return ExecutionStatus.FAILED
    return ExecutionStatus.PARTIAL


def _aggregate_metrics(outcomes: list[_InstanceOutcome]) -> Optional[dict[str, Any]]:
    """Compute aggregate evaluation metrics over the scored instances.

    Only instances that both produced a transcript and carry a ground-truth
    label are scored (errored or label-less instances are skipped), reusing the
    evaluation layer (Req 10.7, 11.5). Returns ``None`` when nothing is scorable.
    """
    scorable = [
        o
        for o in outcomes
        if o.transcript is not None and o.ground_truth is not None
    ]
    if not scorable:
        return None
    transcripts = [o.transcript for o in scorable]
    ground_truth = [o.ground_truth for o in scorable]
    try:
        result = evaluate_transcripts(
            transcripts, ground_truth, scorable[0].output_schema
        )
    except (MADError, ValueError, TypeError):
        # sklearn rejects unscorable label mixes (e.g. a missing prediction
        # next to string labels). Omit the aggregate rather than crash the
        # finalize step, which would leave the run stuck in "running".
        return None
    return {
        "scored_count": result.count,
        **result.metrics,
    }


def _jsonable(value: Any) -> Any:
    """Coerce a pandas/NumPy cell value into a JSON-serializable scalar."""
    item = getattr(value, "item", None)
    if callable(item):
        try:
            return item()
        except (ValueError, TypeError):  # pragma: no cover - defensive
            return str(value)
    return value


__all__ = [
    "DEFAULT_CONCURRENCY",
    "run_execution_async",
    "run_execution_sync",
]
