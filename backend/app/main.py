"""FastAPI application bootstrap (Req 12.1, 12.2).

This module owns the application factory :func:`create_app`, which assembles the
web layer:

* **Settings** (:mod:`app.config`) loaded from the environment / ``.env`` —
  database URL, server secret, CORS origins, OpenAPI metadata.
* **CORS middleware** allowing the configured frontend origin(s).
* **Database initialization** on startup: the configured engine is bound as the
  process-wide default (:func:`app.db.session.configure`) and the schema is
  created/stamped via :func:`app.db.session.init_db`.
* **Structured exception handlers** (:mod:`app.errors`) mapping engine domain
  errors (:mod:`mad.errors`) and request/pydantic validation errors to a single
  JSON envelope with the right HTTP status.
* **Routers** — registered under the ``/api`` prefix: health, taxonomy, configs,
  providers, datasets, and executions.

Layering (Req 12.2) is strictly ``routers -> services -> engine/persistence``;
the engine package (``mad/``) never imports FastAPI, and this module never
reaches past the service/persistence layer it coordinates.
"""

from __future__ import annotations

from contextlib import asynccontextmanager
from typing import AsyncIterator

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.config import Settings, get_settings
from app.db.session import configure, create_engine_for, init_db, session_scope
from app.errors import register_exception_handlers
from app.routers import assistant as assistant_router
from app.routers import configs as configs_router
from app.routers import datasets as datasets_router
from app.routers import executions as executions_router
from app.routers import health as health_router
from app.routers import providers as providers_router
from app.routers import taxonomy as taxonomy_router
from app.services.configs import seed_builtin_configs
from mad import __version__ as mad_version

# API prefix shared by every resource router (design: paths under ``/api``).
API_PREFIX = "/api"


def _make_lifespan(settings: Settings):
    """Build the lifespan context manager that initializes the database.

    On startup it binds a SQLAlchemy engine for ``settings.database_url`` as the
    process-wide default and runs the idempotent :func:`init_db` migration. The
    engine/sessionmaker are created here (not at import time) so tests can point
    the app at an in-memory database via settings overrides.
    """

    @asynccontextmanager
    async def lifespan(_app: FastAPI) -> AsyncIterator[None]:
        engine = create_engine_for(settings.database_url)
        configure(engine)
        init_db(engine)
        # Seed the built-in gold/template configs on first run (Req 5.7). The
        # seeding is idempotent, so running it on every startup is safe.
        with session_scope() as session:
            seed_builtin_configs(session)
        yield

    return lifespan


def create_app(settings: Settings | None = None) -> FastAPI:
    """Create and configure the MAD platform FastAPI application.

    Args:
        settings: Optional settings override. When omitted, the process-wide
            cached settings (env / ``.env``) are used. Passing explicit settings
            is the supported seam for tests (e.g. an in-memory database and a
            fixed CORS origin).
    """
    settings = settings or get_settings()

    app = FastAPI(
        title=settings.api_title,
        version=mad_version,
        description=settings.api_description,
        lifespan=_make_lifespan(settings),
    )

    # Bind the resolved settings to the ``get_settings`` dependency so routers
    # (e.g. datasets, which needs the dataset storage directory) observe this
    # app's settings — including an explicit test override — rather than the
    # process-wide cached instance.
    app.dependency_overrides[get_settings] = lambda: settings

    # CORS for the frontend. Credentials are allowed so cookie/Authorization
    # flows work from the configured origins; origins are never wildcarded when
    # credentials are enabled (that combination is rejected by browsers).
    if settings.cors_origins:
        app.add_middleware(
            CORSMiddleware,
            allow_origins=settings.cors_origins,
            allow_credentials=True,
            allow_methods=["*"],
            allow_headers=["*"],
        )

    # Structured error envelope for domain + validation errors.
    register_exception_handlers(app)

    # Routers. Resource routers (6.2+) are added here under the same prefix.
    app.include_router(health_router.router, prefix=API_PREFIX)
    app.include_router(taxonomy_router.router, prefix=API_PREFIX)
    app.include_router(configs_router.router, prefix=API_PREFIX)
    app.include_router(providers_router.router, prefix=API_PREFIX)
    app.include_router(datasets_router.router, prefix=API_PREFIX)
    app.include_router(executions_router.router, prefix=API_PREFIX)
    app.include_router(assistant_router.router, prefix=API_PREFIX)

    return app


__all__ = ["create_app", "API_PREFIX"]
