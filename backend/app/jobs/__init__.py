"""Async execution job runner and progress tracking (task 6.6).

* :mod:`app.jobs.runner` — the in-process ``asyncio`` worker that turns a queued
  :class:`~app.db.models.Execution` into a finished run: it materialises the
  instance list (single / batch), runs each through the engine ``run_debate``
  with a concurrency limit and per-instance error isolation (Req 10.5, 10.6),
  writes DB-backed progress + per-instance records (Req 10.5, 11.2), computes
  aggregate metrics when ground truth is mapped (Req 10.7, 11.5), and sets the
  final status (completed / failed / partial).
* :mod:`app.jobs.serialize` — projects the engine
  :class:`~mad.engine.transcript.Transcript` into the JSON shape persisted on
  ``execution_instances.transcript`` and rendered by the history viewer.
"""
