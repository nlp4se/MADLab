"""SQLAlchemy declarative base and shared column helpers.

This module defines the single :class:`Base` all ORM models inherit from, plus
small reusable building blocks:

* :data:`JSONDict` / :data:`JSONList` — SQLAlchemy ``JSON`` typed columns that
  carry Python dict/list payloads (the design stores several fields as JSON:
  provider ``models``, config ``artifact``, execution ``config_snapshot``,
  ``input_ref``, ``metrics``, per-instance ``resolved_input``/``transcript``…).
* :data:`TimestampMixin` — adds ``created_at`` / ``updated_at`` columns with
  server-side defaults and on-update refresh, satisfying the "created/updated"
  timestamps required for providers, configurations and executions (Req 5.6).

The module is deliberately free of any FastAPI / web imports: the engine layer
(``mad/``) must never import the web/db layer, and the db layer in turn only
depends on SQLAlchemy and the stdlib so it stays reusable from the CLI and
tests (Req 12.2, 12.4).
"""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

from sqlalchemy import DateTime, func
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column


class Base(DeclarativeBase):
    """Declarative base for all MAD persistence models."""


# Convenient aliases for the JSON-typed payload columns used across the schema.
# SQLAlchemy's generic ``JSON`` type maps to SQLite's JSON1/text storage and
# transparently (de)serializes Python dicts and lists.
JSONDict = dict[str, Any]
JSONList = list[Any]


def _utcnow() -> datetime:
    """Timezone-aware UTC now (used as a Python-side default fallback)."""
    return datetime.now(timezone.utc)


class TimestampMixin:
    """Mixin adding ``created_at`` and ``updated_at`` audit columns.

    ``created_at`` is set once at insert time; ``updated_at`` is refreshed on
    every ``UPDATE``. Both use the database ``CURRENT_TIMESTAMP`` as the server
    default and a Python-side default so rows created via the ORM are stamped
    even before a flush/commit round-trip.
    """

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        default=_utcnow,
        nullable=False,
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        default=_utcnow,
        onupdate=_utcnow,
        nullable=False,
    )


__all__ = ["Base", "TimestampMixin", "JSONDict", "JSONList"]
