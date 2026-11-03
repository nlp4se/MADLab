"""Minimal FastAPI application placeholder.

This is intentionally minimal. The full application bootstrap — settings, CORS
for the frontend, DB initialization, router registration, and structured error
handlers — is implemented in task 6.1. For now this module only exposes a tiny
app factory and a health endpoint so the package imports cleanly and the web
layer has a defined entry point.

``fastapi`` is imported lazily inside :func:`create_app` so that importing this
module (e.g. during the scaffold smoke test) does not require FastAPI to be
installed.
"""

from __future__ import annotations

from typing import Any

from mad import __version__ as mad_version


def create_app() -> Any:
    """Create and return a minimal FastAPI application.

    Full bootstrap (routers, CORS, DB, error handlers) is added in task 6.1.
    """
    from fastapi import FastAPI

    app = FastAPI(
        title="MAD Platform API",
        version=mad_version,
        description="Multi-Agent Debate platform API (placeholder — see task 6.1).",
    )

    @app.get("/health")
    def health() -> dict[str, str]:
        return {"status": "ok", "mad_version": mad_version}

    return app
