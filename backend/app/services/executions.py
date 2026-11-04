"""Execution service layer (Req 10, 11, 7.5).

This service sits between the executions router and the things it coordinates:

* **persistence** — the :class:`app.db.models.Execution` /
  :class:`ExecutionInstance` rows, including the **immutable**
  ``config_snapshot`` captured at launch (Req 11.3);
* **engine** — the artifact schema (:class:`~mad.taxonomy.schema.MADConfig`) for
  snapshotting + the under-development pre-run gate (Req 7.5), the input
  template layer for single-run validation, and the dataset layer for batch
  validation;
* **jobs** — the background :mod:`app.jobs.runner`, wired to a provider registry
  built from the stored providers (:func:`app.services.providers.build_registry`).

It owns the launch lifecycle so the router stays a thin transport shell and the
engine/jobs layers stay web-agnostic (layering per Req 12.2: ``routers ->
services -> engine/persistence``).

Responsibilities:

* **Create / launch** (Req 10.4, 11.3, 7.5): snapshot the configuration
  immutably, run the under-development pre-run gate (reject non-executable
  selections *before* launching), validate the input binding (single template
  coverage / batch dataset + mapping), create the ``queued`` execution row, and
  launch the background job.
* **List / get** (Req 11.1, 11.2): summary rows with status + progress +
  aggregate metrics; detail with the snapshot, input ref, and per-instance
  transcripts/decisions/metrics.
* **Delete** (Req 11.4): remove an execution (its instances cascade).
* **Export** (Req 11.4): the full results payload as a JSON-serializable dict.

Launch seam (testability): the background launch is routed through an injectable
``launch`` callable. The default schedules the async runner; tests inject a
synchronous launcher (:func:`run_execution_sync`) so the job completes
deterministically and offline against a mock provider registry.
"""

from __future__ import annotations

import json
from datetime import datetime, timezone
from typing import Any, Callable, Optional

from sqlalchemy import func, select
from sqlalchemy.orm import Session, selectinload, sessionmaker

from app.db.models import (
    Configuration,
    Dataset as DatasetRow,
    Execution,
    ExecutionInstance,
    ExecutionStatus,
    InputMode,
)
from app.db.session import get_sessionmaker
from app.jobs.runner import run_execution_sync
from app.schemas.executions import (
    ExecutionCreateRequest,
    ExecutionDetail,
    ExecutionInstanceResult,
    ExecutionSummary,
    InstanceUsage,
)
from app.services.configs import ConfigNotFound
from app.services.execution_summary import (
    ACTIVE_STATUSES,
    instance_duration_from_transcript,
    instance_usage_from_parts,
    instance_usage_from_transcript,
    summarize_run,
)
from app.services.datasets import DatasetNotFound
from app.services.providers import build_registry, normalize_base_model_families
from mad.errors import MADError, TemplateError, UnderDevelopment
from mad.input.template import validate_template
from mad.providers.registry import ProviderRegistry
from mad.taxonomy.schema import MADConfig

# A launch callable: given an execution id and a wired registry, run (or
# schedule) the background job. Returns nothing. The default runs synchronously
# only when invoked that way; the router wires the async runner via FastAPI
# BackgroundTasks, and tests inject :func:`run_execution_sync` directly.
LaunchFn = Callable[[int, ProviderRegistry], None]


class ExecutionNotFound(MADError):
    """Raised when an execution id does not exist.

    Subclasses :class:`~mad.errors.MADError` so it flows through the domain
    error machinery; the router translates it to a 404 explicitly rather than
    relying on the default 500 mapping.
    """


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _iso(value: Any) -> Optional[str]:
    """Render a datetime column as an ISO-8601 string, or ``None``."""
    if value is None:
        return None
    try:
        return value.isoformat()
    except AttributeError:  # pragma: no cover - defensive
        return str(value)


def _get_row(session: Session, execution_id: int) -> Execution:
    row = session.get(Execution, execution_id)
    if row is None:
        raise ExecutionNotFound(f"execution {execution_id} not found")
    return row


def _iso_utc(value: Optional[datetime]) -> Optional[str]:
    """Render a UTC run timestamp as ISO-8601 with an explicit offset.

    SQLite drops the offset on read, so naive values are stamped as UTC to keep
    the client from reading them as local time.
    """
    if value is None:
        return None
    if value.tzinfo is None:
        value = value.replace(tzinfo=timezone.utc)
    return value.isoformat()


# One persisted instance as the run summary sees it: (failed, usage or None).
_InstanceFigures = tuple[bool, Optional[InstanceUsage]]


def _expected_total(session: Session, row: Execution) -> Optional[int]:
    """How many instances an *active* run covers, before all are persisted.

    Single runs have one instance; batch runs cover the dataset rows (capped by
    the optional ``limit``). ``None`` for terminal runs (their persisted
    instances are the total) or when the dataset is gone.
    """
    if row.status not in ACTIVE_STATUSES:
        return None
    if row.input_mode == InputMode.SINGLE.value:
        return 1
    ref = row.input_ref or {}
    dataset_id = ref.get("dataset_id")
    dataset = session.get(DatasetRow, dataset_id) if dataset_id is not None else None
    if dataset is None:
        return None
    total = dataset.row_count
    limit = ref.get("limit")
    if isinstance(limit, int) and limit > 0:
        total = min(total, limit)
    return total


def _base_fields(
    session: Session, row: Execution, figures: list[_InstanceFigures]
) -> dict[str, Any]:
    """The fields shared by the list and detail shapes.

    ``instance_count`` / ``completed_count`` count persisted instances (each is
    written only once its debate finished, ok or errored); ``error_count`` is
    the subset carrying an isolated error (Req 10.6). ``summary`` is the run's
    execution time + token usage (task 11.18).
    """
    persisted = len(figures)
    errors = sum(1 for failed, _usage in figures if failed)
    return {
        "id": row.id,
        "config_id": row.config_id,
        "config_name": (row.config.name if row.config is not None else None),
        "input_mode": row.input_mode,
        "status": row.status,
        "progress": row.progress,
        "instance_count": persisted,
        "completed_count": persisted,
        "error_count": errors,
        "metrics": row.metrics,
        "created_at": _iso(row.created_at),
        "updated_at": _iso(row.updated_at),
        "started_at": _iso_utc(row.started_at),
        "finished_at": _iso_utc(row.finished_at),
        "summary": summarize_run(
            status=row.status,
            started_at=row.started_at,
            finished_at=row.finished_at,
            instances=figures,
            expected_total=_expected_total(session, row),
        ),
    }


def _instance_to_result(inst: ExecutionInstance) -> ExecutionInstanceResult:
    return ExecutionInstanceResult(
        instance_index=inst.instance_index,
        resolved_input=dict(inst.resolved_input or {}),
        transcript=inst.transcript,
        final_decision=inst.final_decision,
        ground_truth=inst.ground_truth,
        metrics=inst.metrics,
        error=inst.error,
        usage=instance_usage_from_transcript(inst.transcript),
        duration_s=instance_duration_from_transcript(inst.transcript),
    )


def _to_detail(session: Session, row: Execution) -> ExecutionDetail:
    results = [_instance_to_result(inst) for inst in row.instances]
    figures = [(r.error is not None, r.usage) for r in results]
    return ExecutionDetail(
        **_base_fields(session, row, figures),
        config_snapshot=dict(row.config_snapshot or {}),
        input_ref=dict(row.input_ref or {}),
        instances=results,
    )


def _list_figures(
    session: Session, execution_ids: list[int]
) -> dict[int, list[_InstanceFigures]]:
    """Per-instance ``(failed, usage)`` for many executions, in one query.

    The list never needs the transcripts themselves, only their usage roll-up
    and call count. On SQLite (the app's datastore, Req 14.3) those parts are
    extracted in SQL (``json_extract``), so a poll of the history list never
    moves the (potentially large) transcript blobs into Python. Other dialects
    fall back to loading the transcripts.
    """
    out: dict[int, list[_InstanceFigures]] = {eid: [] for eid in execution_ids}
    if not execution_ids:
        return out
    inst = ExecutionInstance
    failed = inst.error.is_not(None)
    where = inst.execution_id.in_(execution_ids)
    order = (inst.execution_id, inst.instance_index)

    if session.get_bind().dialect.name == "sqlite":
        stmt = (
            select(
                inst.execution_id,
                failed,
                func.json_type(inst.transcript),
                func.json_extract(inst.transcript, "$.usage"),
                func.json_extract(inst.transcript, "$.calls"),
                func.json_array_length(inst.transcript, "$.messages"),
            )
            .where(where)
            .order_by(*order)
        )
        for eid, errored, kind, usage_json, calls, n_messages in session.execute(stmt):
            usage: Optional[InstanceUsage] = None
            if kind == "object":
                usage = instance_usage_from_parts(
                    usage=_loads_object(usage_json),
                    calls=calls,
                    message_count=n_messages,
                )
            out[eid].append((bool(errored), usage))
        return out

    stmt = select(inst.execution_id, failed, inst.transcript).where(where).order_by(*order)
    for eid, errored, transcript in session.execute(stmt):  # pragma: no cover
        out[eid].append((bool(errored), instance_usage_from_transcript(transcript)))
    return out


def _loads_object(value: Any) -> Optional[dict[str, Any]]:
    """Decode a ``json_extract`` object result (JSON text), or ``None``."""
    if isinstance(value, dict):
        return value
    if not isinstance(value, str):
        return None
    try:
        decoded = json.loads(value)
    except ValueError:
        return None
    return decoded if isinstance(decoded, dict) else None


# ---------------------------------------------------------------------------
# Pre-run gating + input validation
# ---------------------------------------------------------------------------


def _gate_under_development(config: MADConfig) -> None:
    """Reject a launch that selects non-executable taxonomy values (Req 7.5).

    The artifact may *carry* under-development values and still be saved; only
    execution is gated. Raises :class:`~mad.errors.UnderDevelopment` (mapped to
    409 by the web layer) listing the offending selections so the UI can tell
    the user exactly what to change before running.
    """
    gated = config.under_development_values()
    if gated:
        joined = ", ".join(gated)
        raise UnderDevelopment(
            "This configuration selects value(s) that are under development and "
            f"cannot be executed yet: {joined}. The configuration can still be "
            "saved; change these selections to run it."
        )


def _validate_single_input(config: MADConfig, instance: dict[str, Any]) -> None:
    """Validate that a single ad-hoc instance covers the template (Req 10.2).

    Ensures every ``{{placeholder}}`` the config's ``input_spec.template``
    references has a value in ``instance`` before launching, so a missing field
    fails fast at launch rather than mid-run. An empty template needs no fields.
    """
    template = config.input_spec.template or ""
    validate_template(template, list(instance.keys()))


def _validate_batch_input(
    session: Session, config: MADConfig, batch: dict[str, Any]
) -> None:
    """Validate a batch binding: dataset exists + mapping covers the template."""
    dataset_id = batch.get("dataset_id")
    mapping = dict(batch.get("mapping", {}) or {})
    ground_truth_column = batch.get("ground_truth_column")

    dataset_row = session.get(DatasetRow, dataset_id)
    if dataset_row is None:
        raise DatasetNotFound(f"dataset {dataset_id} not found")

    columns = set(dataset_row.columns or [])
    unknown = [col for col in mapping if col not in columns]
    if unknown:
        raise TemplateError(
            "Batch mapping references column(s) not in the dataset: "
            f"{', '.join(sorted(unknown))}. Available columns: "
            f"{', '.join(sorted(columns)) or '(none)'}."
        )
    if ground_truth_column and ground_truth_column not in columns:
        raise TemplateError(
            f"Ground-truth column {ground_truth_column!r} is not in the dataset."
        )

    template = config.input_spec.template or ""
    # Every template placeholder must be supplied by the mapping's placeholders.
    validate_template(template, list(mapping.values()))


# ---------------------------------------------------------------------------
# Create / launch (Req 10.4, 11.3, 7.5)
# ---------------------------------------------------------------------------


def create_execution(
    session: Session,
    body: ExecutionCreateRequest,
    *,
    launch: LaunchFn,
    registry: ProviderRegistry,
) -> ExecutionDetail:
    """Snapshot, gate, persist, and launch an execution (Req 10.4, 11.3, 7.5).

    Steps:

    1. Load the referenced configuration and validate its artifact into a
       :class:`MADConfig`.
    2. Run the under-development pre-run gate (Req 7.5) — reject before launch.
    3. Validate the input binding (single template coverage / batch dataset +
       mapping).
    4. Capture the **immutable** ``config_snapshot`` and persist the ``queued``
       execution row (Req 11.3).
    5. Launch the background job via the injected ``launch`` callable, wired to
       ``registry``.

    Args:
        session: Active DB session.
        body: The launch request (config id + single input or batch binding).
        launch: Callable that runs/schedules the background job.
        registry: Engine provider registry (built from stored providers, or a
            mock in tests) handed to the runner.

    Returns:
        The created execution's detail (``queued`` at return time unless the
        injected ``launch`` ran synchronously, in which case it reflects the
        finished state).
    """
    config_row = session.get(Configuration, body.config_id)
    if config_row is None:
        raise ConfigNotFound(f"configuration {body.config_id} not found")

    # Validate the stored artifact back into a MADConfig (it was validated on
    # save, so this is a normalisation step that also drives the gate).
    config = MADConfig.model_validate(config_row.artifact)

    # Pre-run gate BEFORE any row is created (Req 7.5): nothing is persisted for
    # a configuration that cannot execute.
    _gate_under_development(config)

    if body.input is not None:
        input_mode = InputMode.SINGLE
        _validate_single_input(config, body.input)
        input_ref: dict[str, Any] = {"input": dict(body.input)}
    else:
        input_mode = InputMode.BATCH
        batch = body.batch.model_dump()
        _validate_batch_input(session, config, batch)
        input_ref = batch

    # Immutable snapshot of the exact artifact used (Req 11.3), with each bound
    # node's base-model family derived from its provider as it is at launch
    # (task 11.9) so the record reflects the backends actually used.
    normalize_base_model_families(session, config)
    snapshot = config.model_dump(mode="json")

    row = Execution(
        config_id=config_row.id,
        config_snapshot=snapshot,
        input_mode=input_mode.value,
        input_ref=input_ref,
        status=ExecutionStatus.QUEUED.value,
        progress=0.0,
    )
    session.add(row)
    session.flush()  # assign the id before launching the job.
    execution_id = row.id

    # Commit now so the background runner (which opens its own session) sees the
    # queued row even though this request's session has not yet returned.
    session.commit()

    # Launch the job. The default launcher schedules the async runner; a test
    # launcher runs it synchronously. Either way the registry is already wired.
    launch(execution_id, registry)

    # Re-read so the response reflects any synchronous launch outcome.
    session.expire_all()
    return _to_detail(session, _get_row(session, execution_id))


# ---------------------------------------------------------------------------
# Read / list (Req 11.1, 11.2)
# ---------------------------------------------------------------------------


def list_executions(session: Session) -> list[ExecutionSummary]:
    """Return all executions as summary rows (Req 11.1), newest first.

    Instance counts and the run summary come from one query over the instance
    table that reads only the transcripts' usage parts (:func:`_list_figures`),
    so the list does not load per-instance records or transcripts.
    """
    rows = session.scalars(
        select(Execution)
        .options(selectinload(Execution.config))
        .order_by(Execution.id.desc())
    ).all()
    figures = _list_figures(session, [row.id for row in rows])
    return [
        ExecutionSummary(**_base_fields(session, row, figures[row.id]))
        for row in rows
    ]


def get_execution(session: Session, execution_id: int) -> ExecutionDetail:
    """Return the full execution record incl. per-instance results (Req 11.2)."""
    return _to_detail(session, _get_row(session, execution_id))


# ---------------------------------------------------------------------------
# Delete / export (Req 11.4)
# ---------------------------------------------------------------------------


def delete_execution(session: Session, execution_id: int) -> None:
    """Delete an execution and its instances (cascade), or raise if missing."""
    row = _get_row(session, execution_id)
    session.delete(row)
    session.flush()


def export_execution(session: Session, execution_id: int) -> dict[str, Any]:
    """Return the full results payload for an execution as a JSON dict (Req 11.4)."""
    detail = _to_detail(session, _get_row(session, execution_id))
    return detail.model_dump(mode="json")


# ---------------------------------------------------------------------------
# Default launcher wiring
# ---------------------------------------------------------------------------


def make_sync_launcher(
    *, session_factory: Optional[sessionmaker[Session]] = None, **runner_kwargs: Any
) -> LaunchFn:
    """Build a launcher that runs the job synchronously (test/CLI seam).

    The returned callable runs :func:`app.jobs.runner.run_execution_sync` to
    completion before returning, so callers observe the finished execution
    immediately. Extra ``runner_kwargs`` (e.g. ``sleep``) are forwarded.
    """
    factory = session_factory or get_sessionmaker()

    def _launch(execution_id: int, registry: ProviderRegistry) -> None:
        run_execution_sync(
            execution_id,
            registry,
            session_factory=factory,
            **runner_kwargs,
        )

    return _launch


__all__ = [
    "ExecutionNotFound",
    "LaunchFn",
    "create_execution",
    "list_executions",
    "get_execution",
    "delete_execution",
    "export_execution",
    "make_sync_launcher",
]
