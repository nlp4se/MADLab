"""Tests for the FastAPI app bootstrap (task 6.1).

Covers the application factory, settings/CORS wiring, the health endpoint, DB
initialization on startup, and the structured error envelope for both engine
domain errors (:mod:`mad.errors`) and request/pydantic validation errors.

Each test builds its own app via :func:`app.main.create_app` with an in-memory
SQLite database so the suite leaves no on-disk state and tests stay isolated.
"""

from __future__ import annotations

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from pydantic import BaseModel

from app.config import Settings
from app.errors import register_exception_handlers
from app.main import API_PREFIX, create_app
from mad import __version__ as mad_version
from mad.errors import (
    ConfigValidationError,
    ExecutionError,
    MADError,
    ProviderError,
    TemplateError,
    UnderDevelopment,
)

FRONTEND_ORIGIN = "http://localhost:5173"


def _settings() -> Settings:
    """Settings pointed at an in-memory DB with a known frontend origin."""
    return Settings(
        database_url="sqlite:///:memory:",
        cors_origins=[FRONTEND_ORIGIN],
        secret_key="test-secret",
    )


@pytest.fixture()
def client() -> TestClient:
    """A TestClient over a freshly built app (triggers startup/lifespan)."""
    app = create_app(_settings())
    with TestClient(app) as test_client:
        yield test_client


# --------------------------------------------------------------------------- #
# App creation & OpenAPI metadata
# --------------------------------------------------------------------------- #


def test_create_app_returns_fastapi_instance():
    app = create_app(_settings())
    assert isinstance(app, FastAPI)
    assert app.title == "MAD Platform API"
    assert app.version == mad_version
    assert app.description  # non-empty OpenAPI description


def test_openapi_schema_exposes_health(client: TestClient):
    resp = client.get("/openapi.json")
    assert resp.status_code == 200
    schema = resp.json()
    assert schema["info"]["title"] == "MAD Platform API"
    assert f"{API_PREFIX}/health" in schema["paths"]


# --------------------------------------------------------------------------- #
# Health endpoint
# --------------------------------------------------------------------------- #


def test_health_endpoint(client: TestClient):
    resp = client.get(f"{API_PREFIX}/health")
    assert resp.status_code == 200
    body = resp.json()
    assert body["status"] == "ok"
    assert body["mad_version"] == mad_version


# --------------------------------------------------------------------------- #
# CORS
# --------------------------------------------------------------------------- #


def test_cors_headers_for_allowed_origin(client: TestClient):
    resp = client.get(
        f"{API_PREFIX}/health",
        headers={"Origin": FRONTEND_ORIGIN},
    )
    assert resp.status_code == 200
    assert resp.headers.get("access-control-allow-origin") == FRONTEND_ORIGIN


def test_cors_preflight(client: TestClient):
    resp = client.options(
        f"{API_PREFIX}/health",
        headers={
            "Origin": FRONTEND_ORIGIN,
            "Access-Control-Request-Method": "GET",
        },
    )
    assert resp.status_code in (200, 204)
    assert resp.headers.get("access-control-allow-origin") == FRONTEND_ORIGIN


# --------------------------------------------------------------------------- #
# Structured domain-error mapping
# --------------------------------------------------------------------------- #


@pytest.mark.parametrize(
    ("exc", "expected_status"),
    [
        (ConfigValidationError("bad config"), 422),
        (TemplateError("missing placeholder"), 422),
        (UnderDevelopment("not executable yet"), 409),
        (ProviderError("upstream down"), 502),
        (ExecutionError("run failed"), 500),
        (MADError("generic engine error"), 500),
    ],
)
def test_domain_errors_map_to_structured_responses(exc: MADError, expected_status: int):
    """A raised engine error produces the right status + structured envelope."""
    settings = _settings()
    app = create_app(settings)

    @app.get("/boom")
    def boom():  # pragma: no cover - exercised via the client
        raise exc

    with TestClient(app) as test_client:
        resp = test_client.get("/boom")

    assert resp.status_code == expected_status
    body = resp.json()
    assert body["error"] == exc.__class__.__name__
    assert body["detail"] == str(exc)


def test_domain_error_handler_registered_on_bare_app():
    """register_exception_handlers works on a plain app without create_app."""
    app = FastAPI()
    register_exception_handlers(app)

    @app.get("/boom")
    def boom():  # pragma: no cover - exercised via the client
        raise UnderDevelopment("gated value")

    with TestClient(app) as test_client:
        resp = test_client.get("/boom")

    assert resp.status_code == 409
    assert resp.json()["error"] == "UnderDevelopment"


# --------------------------------------------------------------------------- #
# Validation-error mapping
# --------------------------------------------------------------------------- #


def test_request_validation_error_structured():
    """A bad request body yields the 422 structured envelope with field errors."""
    settings = _settings()
    app = create_app(settings)

    class Payload(BaseModel):
        count: int

    @app.post("/echo")
    def echo(payload: Payload):  # pragma: no cover - exercised via the client
        return {"count": payload.count}

    with TestClient(app) as test_client:
        resp = test_client.post("/echo", json={"count": "not-a-number"})

    assert resp.status_code == 422
    body = resp.json()
    assert body["error"] == "RequestValidationError"
    assert isinstance(body["errors"], list) and body["errors"]
    assert "loc" in body["errors"][0]


# --------------------------------------------------------------------------- #
# DB initialization on startup
# --------------------------------------------------------------------------- #


def test_startup_initializes_schema(tmp_path):
    """Entering the lifespan binds the engine and stamps the schema version.

    A temp-file SQLite DB is used (not ``:memory:``) so the separate connection
    opened by ``get_schema_version`` observes the schema the lifespan created —
    each ``:memory:`` connection is an independent, empty database.
    """
    from app.db import session as db_session

    db_url = f"sqlite:///{tmp_path.as_posix()}/bootstrap.db"
    settings = Settings(database_url=db_url, cors_origins=[FRONTEND_ORIGIN])

    app = create_app(settings)
    with TestClient(app):
        assert db_session.get_schema_version() == db_session.SCHEMA_VERSION


# --------------------------------------------------------------------------- #
# Settings parsing
# --------------------------------------------------------------------------- #


def test_cors_origins_accepts_comma_separated_string():
    settings = Settings(cors_origins="http://a.test, http://b.test")
    assert settings.cors_origins == ["http://a.test", "http://b.test"]


def test_cors_origins_empty_string_disables():
    settings = Settings(cors_origins="")
    assert settings.cors_origins == []
