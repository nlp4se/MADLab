"""Engine / session management and lightweight schema initialization.

SQLite is used as an in-process datastore (Req 14.3). This module owns:

* :func:`create_engine_for` / :func:`get_engine` — build (and cache) a
  SQLAlchemy :class:`~sqlalchemy.engine.Engine` for a given database URL, with a
  connection-level ``PRAGMA foreign_keys=ON`` so the ``ON DELETE SET NULL`` /
  ``ON DELETE CASCADE`` rules in :mod:`app.db.models` are actually enforced
  (SQLite disables FK enforcement by default).
* :func:`get_sessionmaker` / :func:`session_scope` — a configured
  ``sessionmaker`` and a transactional context manager that commits on success
  and rolls back on error.
* :func:`init_db` — create all tables (``create_all``) and stamp the schema
  version marker. This is the "lightweight migration": idempotent table
  creation plus a recorded :data:`SCHEMA_VERSION` in the ``schema_meta`` table.

The default on-disk location is ``mad.db`` in the backend working directory;
pass an explicit URL (e.g. ``"sqlite:///:memory:"``) for tests. Nothing here
imports FastAPI — the web layer calls :func:`init_db` on startup, and the CLI
and tests reuse the exact same functions (Req 12.2, 12.4).
"""

from __future__ import annotations

from contextlib import contextmanager
from typing import Iterator

from sqlalchemy import Engine, create_engine, event, inspect, select, text
from sqlalchemy.orm import Session, sessionmaker

from app.db.base import Base
from app.db.models import SchemaMeta

# Persistence schema version. Bumped when the table layout changes; recorded in
# the ``schema_meta`` table by :func:`init_db`.
#   1 - initial layout.
#   2 - ``providers.family`` (nullable) added (task 11.9).
#   3 - ``executions.started_at`` / ``finished_at`` (nullable) added (task 11.18).
SCHEMA_VERSION = "3"
_SCHEMA_VERSION_KEY = "schema_version"

# Columns added after the initial layout. ``create_all`` never alters existing
# tables, so :func:`init_db` adds any missing ones with an idempotent
# ``ALTER TABLE ... ADD COLUMN`` (all are nullable, so existing rows stay valid).
# Entries: (table, column, SQL column type).
_ADDED_COLUMNS: tuple[tuple[str, str, str], ...] = (
    ("providers", "family", "VARCHAR(32)"),
    ("executions", "started_at", "DATETIME"),
    ("executions", "finished_at", "DATETIME"),
)

# Default database URL (relative on-disk SQLite file in the CWD).
DEFAULT_DATABASE_URL = "sqlite:///mad.db"


def _enable_sqlite_fk_pragma(engine: Engine) -> None:
    """Attach a listener enabling ``PRAGMA foreign_keys=ON`` for SQLite.

    SQLite ships with foreign-key enforcement off, so without this the
    ``ON DELETE SET NULL`` / ``CASCADE`` behaviour defined on the models would
    be silently ignored. The listener is a no-op for non-SQLite backends.
    """
    if engine.dialect.name != "sqlite":
        return

    @event.listens_for(engine, "connect")
    def _set_sqlite_pragma(dbapi_connection, _connection_record):  # noqa: ANN001
        cursor = dbapi_connection.cursor()
        cursor.execute("PRAGMA foreign_keys=ON")
        cursor.close()


def create_engine_for(database_url: str = DEFAULT_DATABASE_URL, *, echo: bool = False) -> Engine:
    """Create a new :class:`Engine` for ``database_url`` with SQLite FK enforcement.

    For SQLite we set ``check_same_thread=False`` so the engine may be used from
    background execution workers / threads (Req 10.5).
    """
    connect_args: dict = {}
    if database_url.startswith("sqlite"):
        connect_args["check_same_thread"] = False

    engine = create_engine(database_url, echo=echo, future=True, connect_args=connect_args)
    _enable_sqlite_fk_pragma(engine)
    return engine


# Process-wide default engine / sessionmaker, created lazily on first use.
_engine: Engine | None = None
_SessionLocal: sessionmaker[Session] | None = None


def get_engine() -> Engine:
    """Return the process-wide default engine, creating it on first call."""
    global _engine
    if _engine is None:
        _engine = create_engine_for()
    return _engine


def get_sessionmaker() -> sessionmaker[Session]:
    """Return the process-wide default ``sessionmaker``, creating it on first call."""
    global _SessionLocal
    if _SessionLocal is None:
        _SessionLocal = sessionmaker(
            bind=get_engine(), autoflush=False, expire_on_commit=False, future=True
        )
    return _SessionLocal


def configure(engine: Engine) -> sessionmaker[Session]:
    """Point the process-wide default engine/sessionmaker at ``engine``.

    Useful for the web layer (binding a configured database URL at startup) and
    for tests (binding an in-memory engine). Returns the new sessionmaker.
    """
    global _engine, _SessionLocal
    _engine = engine
    _SessionLocal = sessionmaker(
        bind=engine, autoflush=False, expire_on_commit=False, future=True
    )
    return _SessionLocal


def _add_missing_columns(engine: Engine) -> list[str]:
    """Add any :data:`_ADDED_COLUMNS` missing from existing tables.

    Idempotent: a column already present is skipped, so this is safe on every
    startup and on fresh databases (where ``create_all`` already created it).
    Returns the ``table.column`` names actually added.
    """
    added: list[str] = []
    inspector = inspect(engine)
    tables = set(inspector.get_table_names())
    with engine.begin() as conn:
        for table, column, sql_type in _ADDED_COLUMNS:
            if table not in tables:
                continue
            present = {c["name"] for c in inspector.get_columns(table)}
            if column in present:
                continue
            conn.execute(text(f'ALTER TABLE "{table}" ADD COLUMN "{column}" {sql_type}'))
            added.append(f"{table}.{column}")
    return added


def init_db(engine: Engine | None = None) -> str:
    """Create all tables, add missing columns, and stamp the schema version.

    Idempotent: ``create_all`` only creates missing tables, columns introduced
    after the initial layout are added to existing tables when absent
    (:func:`_add_missing_columns`), and the schema version marker is inserted
    once and raised to :data:`SCHEMA_VERSION` when it records an older version.
    This is the lightweight "migration" the design calls for on startup.
    Returns the schema version recorded in the database.
    """
    engine = engine or get_engine()
    Base.metadata.create_all(engine)
    _add_missing_columns(engine)

    maker = sessionmaker(bind=engine, future=True)
    with maker() as session:
        existing = session.get(SchemaMeta, _SCHEMA_VERSION_KEY)
        if existing is None:
            session.add(SchemaMeta(key=_SCHEMA_VERSION_KEY, value=SCHEMA_VERSION))
            session.commit()
            recorded = SCHEMA_VERSION
        else:
            if _version_lt(existing.value, SCHEMA_VERSION):
                existing.value = SCHEMA_VERSION
                session.commit()
            recorded = existing.value
    return recorded


def _version_lt(recorded: str, current: str) -> bool:
    """Whether a recorded integer schema version is older than ``current``."""
    try:
        return int(recorded) < int(current)
    except (TypeError, ValueError):
        return False


def get_schema_version(engine: Engine | None = None) -> str | None:
    """Return the schema version recorded in the database, or ``None`` if unset."""
    engine = engine or get_engine()
    maker = sessionmaker(bind=engine, future=True)
    with maker() as session:
        row = session.scalar(
            select(SchemaMeta).where(SchemaMeta.key == _SCHEMA_VERSION_KEY)
        )
        return row.value if row is not None else None


@contextmanager
def session_scope(
    session_factory: sessionmaker[Session] | None = None,
) -> Iterator[Session]:
    """Provide a transactional :class:`Session` scope.

    Commits on normal exit, rolls back on exception, and always closes the
    session. Uses the process-wide default sessionmaker unless one is supplied.
    """
    factory = session_factory or get_sessionmaker()
    session = factory()
    try:
        yield session
        session.commit()
    except Exception:
        session.rollback()
        raise
    finally:
        session.close()


__all__ = [
    "SCHEMA_VERSION",
    "DEFAULT_DATABASE_URL",
    "create_engine_for",
    "get_engine",
    "get_sessionmaker",
    "configure",
    "init_db",
    "get_schema_version",
    "session_scope",
]
