"""Request/response DTOs for the executions endpoints (Req 10, 11).

An *execution* binds an immutable snapshot of a configuration to a concrete
input — either a single ad-hoc instance or a CSV dataset batch — and runs the
MAD engine over each instance in the background, recording per-instance
transcripts, decisions, and metrics plus an aggregate roll-up (Req 10, 11).

These Pydantic models are the *transport contract* only; the launch gating, the
immutable snapshot, and the background job runner all live in the service +
jobs layers (:mod:`app.services.executions`, :mod:`app.jobs.runner`), keeping
the layering ``routers -> services -> engine/persistence`` (Req 12.2).

Shapes:

* :class:`ExecutionCreateRequest` — the launch inputs: a ``config_id`` plus one
  of a single ad-hoc ``input`` dict or a ``batch`` (dataset id + column mapping
  + optional ground-truth column).
* :class:`ExecutionSummary` — the list/read shape: status, progress, timestamps,
  and summary metrics (Req 11.1).
* :class:`ExecutionDetail` — a summary plus the immutable ``config_snapshot``,
  the resolved input reference, and the per-instance records (Req 11.2, 11.3).
* :class:`ExecutionInstanceResult` — one per-instance record: resolved input,
  transcript, final decision, ground truth, metrics and any error (Req 11.2).
"""

from __future__ import annotations

from typing import Any, Optional

from pydantic import BaseModel, Field, model_validator


class BatchInput(BaseModel):
    """A batch input binding: a dataset plus its column→placeholder mapping.

    ``mapping`` maps each dataset column name to the template placeholder it
    supplies (Req 10.3). ``ground_truth_column`` names an optional dataset
    column holding gold labels; when present the runner computes aggregate
    evaluation metrics after the run (Req 10.7, 11.5). ``limit`` optionally caps
    the number of rows executed (handy for quick trials over a large CSV).
    """

    dataset_id: int = Field(description="Id of the uploaded dataset to run over.")
    mapping: dict[str, str] = Field(
        description="Dataset column name → template placeholder name (Req 10.3).",
    )
    ground_truth_column: Optional[str] = Field(
        default=None,
        description="Optional dataset column holding gold labels (Req 10.7).",
    )
    limit: Optional[int] = Field(
        default=None,
        ge=1,
        description="Optional cap on the number of rows executed.",
    )


class ExecutionCreateRequest(BaseModel):
    """Inputs for launching an execution (Req 10).

    The caller supplies a ``config_id`` and exactly one input mode:

    * ``input`` — a single ad-hoc instance: ``{placeholder: value}`` resolved
      against the configuration's ``input_spec.template`` (single run); or
    * ``batch`` — a dataset id + column mapping (batch run over CSV rows).

    Exactly one of ``input`` / ``batch`` must be provided.
    """

    config_id: int = Field(description="Configuration to snapshot and run.")
    input: Optional[dict[str, Any]] = Field(
        default=None,
        description="Single ad-hoc instance values (placeholder → value).",
    )
    batch: Optional[BatchInput] = Field(
        default=None,
        description="Batch binding: dataset id + column mapping.",
    )

    @model_validator(mode="after")
    def _one_input_mode(self) -> "ExecutionCreateRequest":
        """Require exactly one of ``input`` / ``batch`` (Req 10)."""
        has_single = self.input is not None
        has_batch = self.batch is not None
        if has_single and has_batch:
            raise ValueError("Provide either input (single) or batch, not both.")
        if not has_single and not has_batch:
            raise ValueError("An input is required: provide input or batch.")
        return self


class InstanceUsage(BaseModel):
    """Token / time totals over every model call of one instance (task 11.18).

    Summed from the instance transcript's usage roll-up. ``cost_usd`` and
    ``model_time_s`` are ``None`` when no call reported them.
    """

    input_tokens: int = Field(default=0, description="Prompt tokens.")
    output_tokens: int = Field(default=0, description="Completion tokens.")
    total_tokens: int = Field(default=0, description="Total tokens as reported.")
    cost_usd: Optional[float] = Field(
        default=None, description="Summed cost, when any call reported one."
    )
    model_time_s: Optional[float] = Field(
        default=None, description="Summed per-call model latency (seconds)."
    )
    calls: int = Field(default=0, description="Successful model calls.")


class InstanceCounts(BaseModel):
    """Instance counts of a run (task 11.18).

    ``total`` is the number of instances the run covers (known up front for
    running executions); ``completed`` succeeded, ``failed`` errored, and the
    remainder is still pending.
    """

    total: int = 0
    completed: int = 0
    failed: int = 0


class RunSummary(BaseModel):
    """Execution time + token usage of a run (task 11.18, Req 9.4, 11.1).

    Computed from the stored per-instance transcripts, so executions recorded
    before the run timestamps existed still get token totals.

    * ``wall_time_s`` — ``finished_at - started_at``, or the elapsed time so
      far while running; ``None`` without a ``started_at``.
    * ``model_time_s`` — the summed latency of every model call. Calls of
      concurrent instances overlap, so it can exceed the wall time; overhead
      outside model calls makes it lower.
    * token totals and ``calls`` cover every model call (debater turns, the
      judge, summarizer compressions); ``cost_usd`` is ``None`` when no call
      reported a cost.
    """

    wall_time_s: Optional[float] = None
    model_time_s: Optional[float] = None
    input_tokens: int = 0
    output_tokens: int = 0
    total_tokens: int = 0
    cost_usd: Optional[float] = None
    calls: int = 0
    instances: InstanceCounts = Field(default_factory=InstanceCounts)


class ExecutionSummary(BaseModel):
    """The execution list/read shape (Req 11.1).

    Carries lifecycle status, progress fraction, timestamps, and the aggregate
    summary metrics so the history list can render status + metrics without
    loading every per-instance record. ``summary`` holds the run's execution
    time and token usage (task 11.18).
    """

    id: int
    config_id: Optional[int] = None
    config_name: Optional[str] = None
    input_mode: str
    status: str
    progress: float = Field(ge=0.0, le=1.0)
    instance_count: int = Field(
        default=0, description="Number of instances in this execution."
    )
    completed_count: int = Field(
        default=0, description="Number of instances that finished (ok or error)."
    )
    error_count: int = Field(
        default=0, description="Number of instances that failed (Req 10.6)."
    )
    metrics: Optional[dict[str, Any]] = Field(
        default=None, description="Aggregate metrics when ground truth present."
    )
    created_at: Optional[str] = None
    updated_at: Optional[str] = None
    started_at: Optional[str] = Field(
        default=None, description="When the job started running (UTC)."
    )
    finished_at: Optional[str] = Field(
        default=None, description="When the job reached a terminal status (UTC)."
    )
    summary: RunSummary = Field(
        default_factory=RunSummary,
        description="Execution time and token usage of the run (task 11.18).",
    )


class ExecutionInstanceResult(BaseModel):
    """One per-instance debate record (Req 11.2).

    ``usage`` / ``duration_s`` surface the transcript's token totals and the
    debate's wall-clock time (task 11.18); ``None`` without a transcript.
    """

    instance_index: int
    resolved_input: dict[str, Any] = Field(default_factory=dict)
    transcript: Optional[dict[str, Any]] = None
    final_decision: Optional[dict[str, Any]] = None
    ground_truth: Optional[str] = None
    metrics: Optional[dict[str, Any]] = None
    error: Optional[str] = None
    usage: Optional[InstanceUsage] = None
    duration_s: Optional[float] = None


class ExecutionDetail(ExecutionSummary):
    """A full execution: summary + snapshot + input ref + per-instance records.

    ``config_snapshot`` is the immutable configuration artifact captured at
    launch (Req 11.3); ``input_ref`` is the ad-hoc values or dataset binding the
    run used; ``instances`` carries the per-instance transcripts/decisions/
    metrics (Req 11.2).
    """

    config_snapshot: dict[str, Any] = Field(default_factory=dict)
    input_ref: dict[str, Any] = Field(default_factory=dict)
    instances: list[ExecutionInstanceResult] = Field(default_factory=list)


class ExecutionDeleteResponse(BaseModel):
    """Acknowledgement returned by ``DELETE /api/executions/{id}`` (Req 11.4)."""

    id: int
    deleted: bool = True


__all__ = [
    "BatchInput",
    "ExecutionCreateRequest",
    "InstanceUsage",
    "InstanceCounts",
    "RunSummary",
    "ExecutionSummary",
    "ExecutionInstanceResult",
    "ExecutionDetail",
    "ExecutionDeleteResponse",
]
