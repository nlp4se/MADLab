"""One-off data fix: mark a single stuck execution as ``failed`` (task 11.13).

Usage (from ``backend/``)::

    .venv\\Scripts\\python.exe scripts\\mark_execution_failed.py 3 [--db mad.db] [--note "..."]

Sets the execution's ``status`` to ``failed`` and ``progress`` to ``1.0``, and
records the note under ``metrics["error"]`` — the same shape the job runner
writes for a run that fails before it starts (``app.jobs.runner.
_mark_failed_to_prepare``); existing metric keys are kept. ``updated_at`` is
refreshed by the model's ``onupdate``. Only that one row is touched, in a
single short transaction. Back up the database before running it.
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

BACKEND = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(BACKEND))

from app.db.models import Execution, ExecutionStatus  # noqa: E402
from app.db.session import create_engine_for, session_scope  # noqa: E402
from sqlalchemy.orm import sessionmaker  # noqa: E402

DEFAULT_NOTE = (
    "Scoring crashed on an unscorable structured decision (fixed in task "
    "11.12); marked failed manually."
)


def mark_failed(db_path: Path, execution_id: int, note: str) -> str:
    """Mark ``execution_id`` failed; return its previous status."""
    engine = create_engine_for(f"sqlite:///{db_path}")
    factory = sessionmaker(bind=engine, autoflush=False, expire_on_commit=False)
    try:
        with session_scope(factory) as session:
            row = session.get(Execution, execution_id)
            if row is None:
                raise SystemExit(f"execution {execution_id} not found in {db_path}")
            previous = row.status
            metrics = dict(row.metrics) if isinstance(row.metrics, dict) else {}
            metrics["error"] = note
            row.status = ExecutionStatus.FAILED.value
            row.progress = 1.0
            row.metrics = metrics
    finally:
        engine.dispose()
    return previous


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("execution_id", type=int)
    parser.add_argument("--db", type=Path, default=BACKEND / "mad.db")
    parser.add_argument("--note", default=DEFAULT_NOTE)
    args = parser.parse_args(argv)

    if not args.db.is_file():
        raise SystemExit(f"database not found: {args.db}")
    previous = mark_failed(args.db.resolve(), args.execution_id, args.note)
    print(f"execution {args.execution_id}: {previous} -> {ExecutionStatus.FAILED.value}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
