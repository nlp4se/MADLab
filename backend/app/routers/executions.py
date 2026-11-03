"""Executions router (Req 10.4, 10.5, 10.6, 11.1-11.4, 7.5).

The transport shell over the execution lifecycle: launch a run (single or
batch), list/inspect runs and their per-instance transcripts, stream live
progress, delete, and export results. It is deliberately thin — the immutable
config snapshot, the under-development pre-run gate, input validation, and the
background job runner all live in :mod:`app.services.executions` /
:mod:`app.jobs.runner`, keeping the layering ``routers -> services ->
engine/persistence`` (Req 12.2).

Routes (mounted under ``/api`` by :func:`app.main.create_app`):

* ``POST   /executions``              — launch a run (single or batch) (Req 10.4)
* ``GET    /executions``              — list runs w/ status + metrics (Req 11.1)
* ``GET    /executions/{id}``         — one run + per-instance transcripts (Req 11.2)
* ``GET    /executions/{id}/stream``  — SSE progress for a running run (Req 10.5)
* ``DELETE /executions/{id}``         — delete a run (Req 11.4)
* ``GET    /executions/{id}/export``  — export results as JSON (Req 11.4)

Async model (design "Open design decisions"): the launch schedules the async
runner on FastAPI :class:`~fastapi.BackgroundTasks`, with DB-backed progress the
list/stream endpoints read back. The provider registry is built once at launch
from the stored providers (:func:`app.services.providers.build_registry`,
decrypting keys at call time) and handed to the runner.

``ExecutionNotFound`` / ``ConfigNotFound`` / ``DatasetNotFound`` are translated
to 404 here; the under-development gate (409), template errors (422), and
provider errors flow through the global structured handler.
"""

from __future__ import annotations

import asyncio
import json
from typing import AsyncIterator

from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException, status
from fastapi.responses import StreamingResponse
from sqlalchemy.orm import Session

from app.db.session import get_sessionmaker, session_scope
from app.routers.dependencies import get_session
from app.schemas.executions import (
    ExecutionCreateRequest,
    ExecutionDeleteResponse,
    ExecutionDetail,
    ExecutionSummary,
)
from app.services import executions as execution_service
from app.services.configs import ConfigNotFound
from app.services.datasets import DatasetNotFound
from app.services.executions import ExecutionNotFound, LaunchFn
from app.services.providers import build_registry
from app.jobs.runner import run_execution_async
from mad.providers.registry import ProviderRegistry

router = APIRouter(prefix="/executions", tags=["executions"])


def _not_found(message: str) -> HTTPException:
    return HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=message)


# ---------------------------------------------------------------------------
# Dependency seams (overridable in tests via app.dependency_overrides)
# ---------------------------------------------------------------------------


def get_registry(session: Session = Depends(get_session)) -> ProviderRegistry:
    """Build the engine provider registry from the stored providers (Req 8, 9.2).

    Decrypts each stored key at call time (:func:`build_registry`). This is a
    dependency so tests can override it with a mock-backed registry
    (:class:`~mad.providers.base.MockModelClient`) for offline, deterministic
    runs; production uses the real LiteLLM-backed clients.
    """
    return build_registry(session)


def get_launcher(background_tasks: BackgroundTasks) -> LaunchFn:
    """Return the launch callable used to start the background job.

    The default schedules the async runner on FastAPI :class:`BackgroundTasks`
    so the request returns immediately while the job runs in-process (design
    "Open design decisions": in-process asyncio + DB-backed progress). Tests
    override this dependency with a synchronous launcher
    (:func:`app.services.executions.make_sync_launcher`) so the job completes
    deterministically before assertions run.
    """
    factory = get_sessionmaker()

    def _launch(execution_id: int, registry: ProviderRegistry) -> None:
        background_tasks.add_task(
            _run_in_background, execution_id, registry, factory
        )

    return _launch


async def _run_in_background(execution_id, registry, factory) -> None:
    """Background entry: run the async job runner to completion."""
    await run_execution_async(execution_id, registry, session_factory=factory)


@router.post(
    "",
    response_model=ExecutionDetail,
    status_code=status.HTTP_201_CREATED,
    summary="Launch an execution (single or batch)",
)
def create_execution(
    body: ExecutionCreateRequest,
    session: Session = Depends(get_session),
    registry: ProviderRegistry = Depends(get_registry),
    launch: LaunchFn = Depends(get_launcher),
) -> ExecutionDetail:
    """Launch a debate execution (Req 10.4).

    Captures an immutable config snapshot (Req 11.3), runs the under-development
    pre-run gate (Req 7.5), validates the input binding, persists a ``queued``
    row, and schedules the background job. The response is the ``queued``
    execution; clients poll ``GET /executions/{id}`` or subscribe to
    ``/executions/{id}/stream`` for progress.
    """
    try:
        return execution_service.create_execution(
            session, body, launch=launch, registry=registry
        )
    except (ConfigNotFound, DatasetNotFound) as exc:
        raise _not_found(str(exc)) from exc


@router.get(
    "",
    response_model=list[ExecutionSummary],
    summary="List executions",
)
def list_executions(session: Session = Depends(get_session)) -> list[ExecutionSummary]:
    """List every execution with status, progress, and summary metrics (Req 11.1)."""
    return execution_service.list_executions(session)


@router.get(
    "/{execution_id}",
    response_model=ExecutionDetail,
    summary="Get an execution",
)
def get_execution(
    execution_id: int,
    session: Session = Depends(get_session),
) -> ExecutionDetail:
    """Return one execution with per-instance transcripts + metrics (Req 11.2)."""
    try:
        return execution_service.get_execution(session, execution_id)
    except ExecutionNotFound as exc:
        raise _not_found(str(exc)) from exc


@router.get(
    "/{execution_id}/stream",
    summary="Stream execution progress (SSE)",
)
async def stream_execution(execution_id: int) -> StreamingResponse:
    """Stream progress events for a running execution via SSE (Req 10.5).

    Emits a ``data:`` JSON event with the current status + progress whenever
    they change, and a final event once the execution reaches a terminal status
    (completed / failed / partial). Reads progress from the DB (the runner's
    DB-backed progress), so it reflects the live job without any shared memory.
    """

    async def _event_stream() -> AsyncIterator[bytes]:
        factory = get_sessionmaker()
        last_payload: str | None = None
        # Poll the DB-backed progress until terminal. A short interval keeps the
        # stream responsive without hammering SQLite.
        for _ in range(_MAX_STREAM_TICKS):
            snapshot = _read_progress(factory, execution_id)
            if snapshot is None:
                yield _sse({"error": "not_found", "execution_id": execution_id})
                return
            payload = json.dumps(snapshot)
            if payload != last_payload:
                last_payload = payload
                yield _sse(snapshot)
            if snapshot["status"] in _TERMINAL_STATUSES:
                return
            await asyncio.sleep(_STREAM_INTERVAL_S)

    return StreamingResponse(_event_stream(), media_type="text/event-stream")


@router.delete(
    "/{execution_id}",
    response_model=ExecutionDeleteResponse,
    summary="Delete an execution",
)
def delete_execution(
    execution_id: int,
    session: Session = Depends(get_session),
) -> ExecutionDeleteResponse:
    """Delete an execution and its per-instance records (Req 11.4)."""
    try:
        execution_service.delete_execution(session, execution_id)
    except ExecutionNotFound as exc:
        raise _not_found(str(exc)) from exc
    return ExecutionDeleteResponse(id=execution_id, deleted=True)


@router.get(
    "/{execution_id}/export",
    summary="Export execution results",
)
def export_execution(
    execution_id: int,
    session: Session = Depends(get_session),
) -> dict:
    """Return the full results payload for an execution as JSON (Req 11.4)."""
    try:
        return execution_service.export_execution(session, execution_id)
    except ExecutionNotFound as exc:
        raise _not_found(str(exc)) from exc


# ---------------------------------------------------------------------------
# SSE helpers
# ---------------------------------------------------------------------------

# Terminal statuses that end the SSE stream.
_TERMINAL_STATUSES = frozenset({"completed", "failed", "partial"})
# Poll interval + a generous tick cap so a stuck stream cannot run forever.
_STREAM_INTERVAL_S = 0.25
_MAX_STREAM_TICKS = 2400  # ~10 minutes at the default interval.


def _read_progress(factory, execution_id: int):
    """Read the execution's current status + progress from the DB, or ``None``."""
    from app.db.models import Execution  # local import: avoid a cycle at import.

    with session_scope(factory) as session:
        row = session.get(Execution, execution_id)
        if row is None:
            return None
        return {
            "execution_id": row.id,
            "status": row.status,
            "progress": row.progress,
        }


def _sse(data: dict) -> bytes:
    """Encode a dict as a single SSE ``data:`` event."""
    return f"data: {json.dumps(data)}\n\n".encode("utf-8")


__all__ = ["router"]
