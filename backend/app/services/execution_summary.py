"""Run summary: execution time and token usage of an execution (task 11.18).

Pure aggregation, no DB or web access: the executions service feeds it the
stored per-instance figures and the execution's run window, and it returns the
:class:`~app.schemas.executions.RunSummary` exposed on the detail and list
responses (Req 9.4, 11.1).

Per-instance figures come from the stored transcript JSON
(:func:`app.jobs.serialize.transcript_to_dict`): its ``usage`` roll-up (summed
over every model call), its ``calls`` count and its ``duration_s``. Transcripts
recorded before task 11.18 carry neither ``calls`` nor ``duration_s``; for those
the call count falls back to the number of messages (one call per recorded
turn) and the duration stays unknown.

The list endpoint never loads full transcripts: it extracts just these parts in
SQL and passes them to :func:`instance_usage_from_parts`; the detail endpoint
has the transcripts anyway and uses :func:`instance_usage_from_transcript`.
Both paths share the same normalisation.
"""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any, Iterable, Mapping, Optional

from app.schemas.executions import InstanceCounts, InstanceUsage, RunSummary

# Statuses during which the wall time is "elapsed so far".
ACTIVE_STATUSES = frozenset({"queued", "running"})


# ---------------------------------------------------------------------------
# Coercion helpers (stored JSON is free-form; never trust its types)
# ---------------------------------------------------------------------------


def _int(value: Any) -> int:
    if isinstance(value, bool):
        return 0
    if isinstance(value, (int, float)):
        return max(0, int(value))
    return 0


def _float_or_none(value: Any) -> Optional[float]:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        return None
    return float(value)


def _add_optional(total: Optional[float], value: Optional[float]) -> Optional[float]:
    """Sum that stays ``None`` until a value is reported."""
    if value is None:
        return total
    return (total or 0.0) + value


# ---------------------------------------------------------------------------
# Per-instance figures
# ---------------------------------------------------------------------------


def instance_usage_from_parts(
    *,
    usage: Optional[Mapping[str, Any]],
    calls: Any = None,
    message_count: Any = None,
) -> InstanceUsage:
    """Build one instance's :class:`InstanceUsage` from transcript parts.

    Args:
        usage: The transcript's ``usage`` roll-up (``prompt_tokens``,
            ``completion_tokens``, ``total_tokens``, ``cost_usd``,
            ``latency_s``); missing / malformed fields count as absent.
        calls: The transcript's ``calls`` count, when recorded (task 11.18).
        message_count: Number of transcript messages; the call count of
            transcripts that predate ``calls``.
    """
    usage = usage if isinstance(usage, Mapping) else {}
    input_tokens = _int(usage.get("prompt_tokens"))
    output_tokens = _int(usage.get("completion_tokens"))
    total = usage.get("total_tokens")
    total_tokens = (
        _int(total)
        if isinstance(total, (int, float)) and not isinstance(total, bool)
        else input_tokens + output_tokens
    )
    if isinstance(calls, (int, float)) and not isinstance(calls, bool):
        call_count = _int(calls)
    else:
        call_count = _int(message_count)
    return InstanceUsage(
        input_tokens=input_tokens,
        output_tokens=output_tokens,
        total_tokens=total_tokens,
        cost_usd=_float_or_none(usage.get("cost_usd")),
        model_time_s=_float_or_none(usage.get("latency_s")),
        calls=call_count,
    )


def instance_usage_from_transcript(
    transcript: Optional[Mapping[str, Any]],
) -> Optional[InstanceUsage]:
    """One instance's usage from its stored transcript, or ``None`` without one."""
    if not isinstance(transcript, Mapping):
        return None
    messages = transcript.get("messages")
    return instance_usage_from_parts(
        usage=transcript.get("usage"),
        calls=transcript.get("calls"),
        message_count=len(messages) if isinstance(messages, list) else 0,
    )


def instance_duration_from_transcript(
    transcript: Optional[Mapping[str, Any]],
) -> Optional[float]:
    """The debate's recorded wall-clock seconds, or ``None`` when unknown."""
    if not isinstance(transcript, Mapping):
        return None
    return _float_or_none(transcript.get("duration_s"))


# ---------------------------------------------------------------------------
# Run-level aggregation
# ---------------------------------------------------------------------------


def _as_utc(value: datetime) -> datetime:
    """Treat naive datetimes (SQLite drops the offset) as UTC."""
    if value.tzinfo is None:
        return value.replace(tzinfo=timezone.utc)
    return value.astimezone(timezone.utc)


def wall_time_s(
    *,
    status: str,
    started_at: Optional[datetime],
    finished_at: Optional[datetime],
    now: Optional[datetime] = None,
) -> Optional[float]:
    """Wall-clock seconds of a run.

    ``finished_at - started_at`` once finished; the elapsed time so far while
    the run is active; ``None`` without a ``started_at`` (executions recorded
    before the run timestamps existed) or for a terminal run missing its end.
    """
    if started_at is None:
        return None
    if finished_at is not None:
        end = _as_utc(finished_at)
    elif status in ACTIVE_STATUSES:
        end = _as_utc(now) if now is not None else datetime.now(timezone.utc)
    else:
        return None
    return max(0.0, (end - _as_utc(started_at)).total_seconds())


def summarize_run(
    *,
    status: str,
    started_at: Optional[datetime],
    finished_at: Optional[datetime],
    instances: Iterable[tuple[bool, Optional[InstanceUsage]]],
    expected_total: Optional[int] = None,
    now: Optional[datetime] = None,
) -> RunSummary:
    """Aggregate a run's :class:`RunSummary`.

    Args:
        status: The execution status (drives the "elapsed so far" wall time).
        started_at / finished_at: The run window; either may be ``None``.
        instances: One ``(failed, usage)`` pair per persisted instance;
            ``usage`` is ``None`` for an instance without a transcript.
        expected_total: The number of instances the run covers, when known
            (used while running, before every instance is persisted).
        now: Clock override for tests.
    """
    input_tokens = output_tokens = total_tokens = calls = 0
    cost: Optional[float] = None
    model_time: Optional[float] = None
    completed = failed = 0

    for errored, usage in instances:
        if errored:
            failed += 1
        else:
            completed += 1
        if usage is None:
            continue
        input_tokens += usage.input_tokens
        output_tokens += usage.output_tokens
        total_tokens += usage.total_tokens
        calls += usage.calls
        cost = _add_optional(cost, usage.cost_usd)
        model_time = _add_optional(model_time, usage.model_time_s)

    persisted = completed + failed
    total = max(persisted, expected_total or 0)
    return RunSummary(
        wall_time_s=wall_time_s(
            status=status, started_at=started_at, finished_at=finished_at, now=now
        ),
        model_time_s=model_time,
        input_tokens=input_tokens,
        output_tokens=output_tokens,
        total_tokens=total_tokens,
        cost_usd=cost,
        calls=calls,
        instances=InstanceCounts(total=total, completed=completed, failed=failed),
    )


__all__ = [
    "ACTIVE_STATUSES",
    "instance_usage_from_parts",
    "instance_usage_from_transcript",
    "instance_duration_from_transcript",
    "wall_time_s",
    "summarize_run",
]
