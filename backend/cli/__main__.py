"""CLI entry point for the headless ``mad`` console script.

Delegates to :func:`cli.app.main`, which implements the full command set
(create-config, run, classify, evaluate) over the same services/engine the
FastAPI web layer uses — the headless research path (Req 12.4, 12.5). The
``version`` command is preserved from the original stub.
"""

from __future__ import annotations

from cli.app import main

if __name__ == "__main__":
    raise SystemExit(main())
