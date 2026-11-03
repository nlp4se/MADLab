"""SQLAlchemy models, session management, and lightweight schema init.

This package is the persistence layer of the backend (Req 14.3). It defines the
ORM models for the five core tables — ``providers``, ``configurations``,
``datasets``, ``executions`` and ``execution_instances`` — plus a ``schema_meta``
marker table, and the engine/session helpers used by the web layer, the CLI and
tests.

The engine layer (``mad/``) must never import this package; dependency flow is
strictly ``app -> mad`` (Req 12.2).
"""

from app.db.base import Base, JSONDict, JSONList, TimestampMixin
from app.db.models import (
    Configuration,
    Dataset,
    Execution,
    ExecutionInstance,
    ExecutionStatus,
    InputMode,
    Provider,
    SchemaMeta,
)
from app.db.session import (
    DEFAULT_DATABASE_URL,
    SCHEMA_VERSION,
    configure,
    create_engine_for,
    get_engine,
    get_schema_version,
    get_sessionmaker,
    init_db,
    session_scope,
)

__all__ = [
    # base
    "Base",
    "TimestampMixin",
    "JSONDict",
    "JSONList",
    # models
    "Provider",
    "Configuration",
    "Dataset",
    "Execution",
    "ExecutionInstance",
    "SchemaMeta",
    "InputMode",
    "ExecutionStatus",
    # session
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
