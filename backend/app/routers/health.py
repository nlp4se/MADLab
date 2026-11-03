"""Health/liveness router.

A dependency-free endpoint used for liveness checks and to confirm the app
factory wired routers correctly. Resource routers (taxonomy, configs,
providers, datasets, executions) are added in tasks 6.2+ and registered the
same way in :func:`app.main.create_app`.
"""

from __future__ import annotations

from fastapi import APIRouter

from mad import __version__ as mad_version

router = APIRouter(tags=["health"])


@router.get("/health", summary="Liveness check")
def health() -> dict[str, str]:
    """Return a simple liveness payload including the engine version."""
    return {"status": "ok", "mad_version": mad_version}


__all__ = ["router"]
